import json
from types import SimpleNamespace as NS
import pytest
from backend.agent import Agent,ChatRequest
from backend.database import one
from backend.math_verification import verify,parse
from backend.ollama_provider import evidence_ids
from backend.learning import grade


class ReliableFixture:
    local=True;compact_workflow=True;reliable_workflow=True
    def __init__(self,unsafe=False):self.calls=[];self.unsafe=unsafe;self.context=[]
    def respond(self,messages,tools):
        self.context=messages;name=tools[0]['name'];self.calls.append(name);ids=evidence_ids(messages)
        text='조건부확률은 조건을 만족하는 경우에 범위를 좁혀 다른 사건이 얼마나 자주 일어나는지 생각하는 방법입니다. 두 사건이 함께 나타나는 상황과 기준이 되는 조건을 구분하고 원문의 설명을 함께 대조해 보세요.'
        if self.unsafe:text+=' p(A|B)=p(B|A)p(A)'
        args={'explain_concept':{'text':text,'source_ids':ids[:1]},
              'find_prerequisites':{'concept':'conditional probability','candidates':['joint probability']},
              'generate_quiz':{'concept':'conditional probability','kind':'choice','question':'조건을 바꾸면 확률은?',
                  'choices':['달라질 수 있음','언제나 1'],'answer':'달라질 수 있음','explanation':'AI 제안 기준','source_ids':ids[:1]},
              'evaluate_answer':{'correct':False,'confidence':1,'explanation':text,'cause':'개념 혼동'}}[name]
        return NS(output=[NS(type='function_call',name=name,arguments=json.dumps(args),call_id='fixture'+str(len(self.calls)))],usage=None,output_text='')


def test_numeric_and_symbolic_verification_have_explicit_scope():
    assert verify({'expression':'joint/condition','bindings':{'joint':'0.2','condition':'0.5'}})['exact']=='2/5'
    identity=verify({'expression':'(x*x-y*y)/(x-y)','comparison':'x+y'})
    assert identity['status']=='verified_identity' and identity['conditions']==['x - y != 0']
    assert verify({'expression':'x+y','comparison':'x-y'})['status']=='failed'
    assert verify({'expression':'x+y'})['status']=='unverified'
    assert verify({'expression':'1/0'})['status']=='failed'


@pytest.mark.parametrize('text',['__import__("os")','x.__class__','[x for x in y]','2**1000','(x+y)**4*(x+y)**4*(x+y)**4','0**0','sin(x)','1e999'])
def test_math_parser_rejects_code_and_resource_exhaustion(text):
    assert verify({'expression':text})['status']=='failed'


def test_basic_confusion_does_not_start_quiz_and_never_sends_full_page(client,book):
    provider=ReliableFixture()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='아직 조건부확률을 모르겠어'),provider).run()
    assert result['status']=='needs_review',result
    assert provider.calls==['explain_concept'] and result['quiz'] is None
    assert not any(isinstance(m,dict) and 'full-text supplement' in m.get('content','') for m in provider.context)
    follow=ReliableFixture()
    Agent(ChatRequest(book_id=book['id'],page=1,message='앞서 질문을 다시 설명',session_id=result['session_id']),follow).run()
    prior=next(m['content'] for m in follow.context if isinstance(m,dict) and m.get('content','').startswith('Previous learner context'))
    assert result['text'].split('\n')[0] not in prior


def test_unsafe_math_is_quarantined_not_published_as_explanation(client,book):
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='수식과 개념을 설명'),ReliableFixture(unsafe=True)).run()
    assert result['status']=='needs_review'
    assert 'p(A|B)' not in result['text'] and 'p(A|B)' in result['draft']
    assert json.loads(one('SELECT response FROM runs')['response'])['status']=='needs_review'


def test_math_only_and_invalid_calculation_do_not_waste_model_calls(client,book):
    provider=ReliableFixture()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='수식 유도'),provider).run()
    assert not provider.calls and result['status']=='needs_review'
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='계산 설명',math_input={'expression':'1/0'}),provider).run()
    assert not provider.calls and result['math_review']['status']=='failed'


def test_independent_numeric_quiz_grading_is_private_fast_and_idempotent(client,book):
    provider=ReliableFixture()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='조건부확률 확인',learning_mode='deep',math_input={
        'formula':'사용자가 확인한 식','source_confirmed':True,'expression':'joint/condition','bindings':{'joint':'0.2','condition':'0.5'}}),provider).run()
    assert run['status']=='awaiting_answer',run
    assert provider.calls==['find_prerequisites','explain_concept']
    assert run['quiz']['verification']['status']=='verified_calculation'
    for key in ('value','exact','latex'):assert key not in run['math_review']
    for key in ('answer','explanation','_verification'):assert key not in run['quiz']
    grader=ReliableFixture()
    req=ChatRequest(book_id=book['id'],page=1,message='답안',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer='1')
    result=Agent(req,grader).run()
    assert not grader.calls and not result['evaluation']['correct'] and not result['evaluation']['uncertain']
    assert one('SELECT status FROM mastery')['status']=='복습 필요'
    assert Agent(req,grader).run()['evaluation']['already_submitted']
    assert one('SELECT count(*) n FROM attempts')['n']==1


def test_model_key_and_confidence_cannot_certify_mastery_manual_review_is_audited(client,book):
    provider=ReliableFixture()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='개념 진단',learning_mode='deep'),provider).run()
    assert run['quiz']['verification']['status']=='unverified'
    req=ChatRequest(book_id=book['id'],page=1,message='답안',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer='언제나 1')
    result=Agent(req,ReliableFixture()).run()
    assert result['evaluation']['uncertain'] and not result['evaluation']['key_verified']
    assert one('SELECT total FROM mastery')['total']==0
    aid=result['evaluation']['attempt_id'];original=one('SELECT * FROM attempts')
    assert client.post(f'/api/attempts/{aid}/review',json={'correct':False,'confirmed_key':'확인한 정답','confirm_key':False}).status_code==422
    response=client.post(f'/api/attempts/{aid}/review',json={'correct':False,'confirmed_key':'확인한 정답','confirm_key':True})
    assert response.status_code==200 and response.json()['type']=='user_self_review'
    assert one('SELECT * FROM attempts')==original
    assert one('SELECT status FROM mastery')['status']=='복습 필요'
    assert client.get('/api/dashboard').json()['accuracy']==0
    assert client.get(f'/api/attempts/{aid}/review').json()['review']


def test_trusted_source_synonyms_are_deterministic_but_model_aliases_are_not():
    payload={'kind':'short','answer':'conditional probability','accepted':['always one'],'explanation':'原文',
             '_verification':{'status':'verified_source_recall','aliases':['조건부확률','conditional probability']}}
    assert grade(payload,'조건부 확률',True)['correct']
    assert not grade(payload,'always one',True)['correct']
    untrusted=dict(payload);untrusted.pop('_verification')
    assert grade(untrusted,'conditional probability',True)['uncertain']


def test_unverified_math_cannot_be_certified_by_literal_pdf_cloze():
    from backend.quiz_validation import source_key
    assert source_key({'answer':'p(A|B)','question':'____ = numerator'},[{'id':'source','text':'p(A|B) = numerator'}])['status']=='unverified'


def test_three_calculation_practices_do_not_claim_conceptual_understanding(client,book):
    for numerator,answer in [('0.2','0.4'),('0.3','0.6'),('0.4','0.8')]:
        provider=ReliableFixture()
        run=Agent(ChatRequest(book_id=book['id'],page=1,message='숫자 예제',learning_mode='deep',
            math_input={'formula':'ratio','source_confirmed':True,'expression':'x/y','bindings':{'x':numerator,'y':'0.5'}}),provider).run()
        assert not provider.calls
        result=Agent(ChatRequest(book_id=book['id'],page=1,message='답안',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer=answer),provider).run()
        assert result['evaluation']['correct']
    assert one('SELECT status FROM mastery')['status']=='연습 완료'


def test_pdf_math_preview_returns_actual_image_and_unconfirmed_metadata(client,book):
    result=client.get(f"/api/books/{book['id']}/pages/1/math-preview")
    assert result.status_code==200 and result.json()['status']=='unconfirmed_extraction'
    image=client.get(result.json()['image_url'])
    assert image.content.startswith(b'\x89PNG')
    assert client.get(f"/api/books/{book['id']}/pages/999/math-image").status_code==422


def test_jobs_report_real_generation_phase_and_reject_concurrent_inference(client,book,monkeypatch):
    import threading,time
    from backend.config import settings
    import backend.agent
    started=threading.Event();release=threading.Event()
    class Slow(ReliableFixture):
        def respond(self,messages,tools):
            started.set();release.wait(3)
            return super().respond(messages,tools)
    monkeypatch.setattr(settings,'ai_provider','ollama');monkeypatch.setattr(settings,'ai_mode','live')
    monkeypatch.setattr(backend.agent,'OllamaProvider',Slow)
    payload={'book_id':book['id'],'page':1,'message':'조건부확률 설명'}
    try:
        job=client.post('/api/chat/jobs',json=payload)
        assert job.status_code==202 and started.wait(3)
        url='/api/chat/jobs/'+job.json()['id']
        assert client.get(url).json()['phase']=='generating'
        assert client.post('/api/chat/jobs',json=payload).status_code==409
    finally:release.set()
    for _ in range(100):
        state=client.get(url).json()
        if state['status']!='running':break
        time.sleep(.01)
    assert state['status']=='done' and state['result']['status']=='needs_review'
