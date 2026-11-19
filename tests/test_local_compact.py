import json
from types import SimpleNamespace as NS
import httpx
import pytest
from backend.agent import Agent,ChatRequest,tool_schemas
from backend.config import settings
from backend.database import one
from backend.ollama_provider import OllamaProvider,evidence_ids
from backend.quality import assess,arithmetic


class OfflineTaskFixture:
    """Unit-test model substitute; never used by the actual evaluation server."""
    local=True
    compact_workflow=True
    def __init__(self):self.calls=[]
    def respond(self,messages,tools):
        assert len(tools)==1
        name=tools[0]['name'];self.calls.append(name)
        sources=evidence_ids(messages)
        explanation='조건부확률은 조건을 만족하는 경우로 표본 공간을 제한해서 계산합니다. 결합확률은 두 사건이 동시에 일어날 확률입니다. 조건이 달라지면 분모가 달라지므로 언제나 1이 되지는 않습니다.'
        args={'find_prerequisites':{'concept':'conditional probability','candidates':['joint probability']},
              'explain_concept':{'text':explanation,'source_ids':sources[:1]},
              'generate_quiz':{'concept':'conditional probability','kind':'short','question':'조건부확률의 분모는 어떤 경우를 세나요?',
                               'answer':'private fixture answer','explanation':'private fixture rubric','source_ids':sources[:1]},
              'evaluate_answer':{'correct':False,'confidence':.99,'explanation':explanation,'cause':'조건부확률을 상수 1로 혼동'}}[name]
        return NS(output=[NS(type='function_call',name=name,arguments=json.dumps(args),call_id='fixture-'+str(len(self.calls)))],usage=NS(input_tokens=100,output_tokens=30),output_text='')


def test_ordinary_local_question_uses_one_generation_and_distinguishes_actors(client,book):
    provider=OfflineTaskFixture()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='조건부확률을 쉽게 설명해 줘'),provider).run()
    assert result['status']=='completed',result['text']
    assert provider.calls==['explain_concept'] and result['usage']['api_calls']==1
    assert [(e['tool'],e['actor']) for e in result['events']]==[('get_current_page','server'),('search_textbook','server'),('explain_concept','model')]
    assert result['sources'] and '#source-' in result['text']
    assert result['quality']['status']=='limited_checks_passed'


def test_current_page_with_all_books_retains_other_book_evidence(client,book):
    from tests.conftest import pdf_bytes
    from backend.database import many
    second=client.post('/api/books',files={'file':('other.pdf',pdf_bytes('Other probability','Conditional probability is based on joint probability for another example.'),'application/pdf')})
    assert second.status_code==201
    class Capture(OfflineTaskFixture):
        def respond(self,messages,tools):
            self.ids=evidence_ids(messages)
            self.page=any(m.get('content','').startswith('Current PDF page full-text supplement') for m in messages if isinstance(m,dict))
            return super().respond(messages,tools)
    provider=Capture()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='이 페이지의 조건부확률을 두 교과서에서 비교해 줘',scope='all'),provider).run()
    assert run['status']=='completed',run['text']
    assert provider.page
    book_ids={row['book_id'] for row in many('SELECT id,book_id FROM chunks') if row['id'] in provider.ids}
    assert len(book_ids)==2


def test_legacy_answer_is_rechecked_before_becoming_followup_evidence(client,book):
    from backend.database import db
    first=Agent(ChatRequest(book_id=book['id'],page=1,message='조건부확률 설명'),OfflineTaskFixture()).run()
    legacy=dict(first,status='completed')
    legacy.pop('quality',None)
    legacy['text']='조건부확률 $p(Y|X)$는 $p(X|Y)p(Y)$로 표현됩니다.'
    with db() as c:c.execute('UPDATE runs SET response=? WHERE id=?',(json.dumps(legacy),first['id']))
    class Capture(OfflineTaskFixture):
        def respond(self,messages,tools):
            self.history=next(m['content'] for m in messages if isinstance(m,dict) and m.get('content','').startswith('Previous conversation DATA'))
            return super().respond(messages,tools)
    provider=Capture()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='이전 개념을 쉽게 설명',session_id=first['session_id']),provider).run()
    assert result['status']=='completed'
    history=json.loads(provider.history.split(': ',1)[1])
    assert history[-1]['previous_answer_needs_review']
    assert legacy['text'] not in provider.history


def test_local_diagnosis_grading_and_duplicate_protect_private_rubric_and_history(client,book):
    tutor=OfflineTaskFixture()
    diagnosis=Agent(ChatRequest(book_id=book['id'],page=1,message='아직 조건부확률을 모르겠어. 확인 문제를 내 줘'),tutor).run()
    assert diagnosis['status']=='awaiting_answer',diagnosis['text']
    assert tutor.calls==['find_prerequisites','explain_concept','generate_quiz']
    assert 'private fixture answer' not in json.dumps(diagnosis)
    assert 'private fixture rubric' not in json.dumps(diagnosis)
    grader=OfflineTaskFixture()
    request=ChatRequest(book_id=book['id'],page=1,session_id=diagnosis['session_id'],quiz_id=diagnosis['quiz']['id'],answer='always one',message='채점해 줘')
    result=Agent(request,grader).run()
    assert result['status']=='completed',result['text']
    assert grader.calls==['evaluate_answer']
    assert not result['evaluation']['correct'] and not result['evaluation']['uncertain']
    assert one('SELECT status FROM mastery')['status']=='복습 필요'
    assert one('SELECT state FROM sessions')['state']=='ready'
    assert {e['tool'] for e in result['events']} >= {'find_prerequisites','recommend_next_topic','update_mastery'}
    repeated=Agent(request,grader).run()
    assert grader.calls==['evaluate_answer'] and repeated['usage']['api_calls']==0
    assert repeated['evaluation']['already_submitted'] and one('SELECT count(*) n FROM attempts')['n']==1
    assert client.get(f"/api/books/{book['id']}/history").json()[-1]['response']['evaluation']['attempt_id']==result['evaluation']['attempt_id']


def test_wrong_page_selection_is_rejected_before_model_call(client,book):
    provider=OfflineTaskFixture()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='쉽게 설명',selection='Gradient descent uses derivatives for optimization.'),provider).run()
    assert result['status']=='error' and not provider.calls
    assert '현재 책·페이지' in result['text']


def test_missing_derivation_and_numbers_are_not_recorded_as_quality_success(client,book):
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='수식 유도와 숫자 예제를 보여줘'),OfflineTaskFixture()).run()
    assert result['status']=='needs_review'
    assert len(result['quality']['issues'])==2
    saved=json.loads(one('SELECT response FROM runs')['response'])
    assert saved['status']=='needs_review' and saved['quality']['issues']


@pytest.mark.parametrize('expression',['__import__("os")','9**999','1/0','[1]','open(".env")'])
def test_independent_arithmetic_never_executes_model_code(expression):
    with pytest.raises((ValueError,ArithmeticError,SyntaxError)):arithmetic(expression)


def test_quality_detects_wrong_numbers_and_bayes_direction_without_claiming_general_proof():
    bad=assess(r'$0.8 * 0.2 / 0.4 = 0.9$; $p(A|B)=\frac{p(B|A)p(A)}{p(A)}$','数字',[])
    assert bad['status']=='needs_review' and len(bad['issues'])==2
    good=assess(r'$p(A,B)=p(A|B)p(B)=p(B|A)p(A)$; $p(A|B)=\frac{p(B|A)p(A)}{p(B)}$; $p(B)>0$; $0.8 * 0.2 / 0.4 = 0.4$','수식 유도와 숫자 예제',[])
    assert good['status']=='limited_checks_passed' and not good['issues']
    assert any(c.get('computed')==pytest.approx(.4) for c in good['math_checks'])
    assert '모든' in good['limits']


def test_correct_arithmetic_using_joint_as_likelihood_is_still_rejected():
    text='p(X=1,Y=2)=0.2, p(Y=2)=0.5, p(X=1)=0.4\np(Y|X=1)=(0.2 * 0.5)/0.4 = 0.25'
    result=assess(text,'',[])
    assert result['status']=='needs_review'
    assert result['math_checks'][0]['computed']==.5
    assert result['math_checks'][0]['claimed']==.25


def test_circular_bayes_derivation_and_missing_condition_are_flagged():
    text=r'$p(X,Y)=p(Y|X)p(X)$; $p(Y|X)=\frac{p(X|Y)p(Y)}{p(X)}$'
    result=assess(text,'베이즈 수식 유도',[])
    assert any('중간 단계' in issue for issue in result['issues'])
    assert any('적용 조건' in issue for issue in result['issues'])


def test_pdf_fraction_bar_preserves_actual_numerator_and_denominator():
    import pymupdf
    from backend.pdf_math import fraction_hints,readable_page
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((30,102.5),'p(Y|X) =',fontsize=10)
        page.insert_text((100,95),'p(X|Y)p(Y)',fontsize=10)
        page.insert_text((112,110),'p(X)',fontsize=10)
        page.draw_line((99,100),(151,100),width=.4)
        # Filled diagrams have width=None in real Bishop PDF 131. Optional
        # fraction hints must never prevent ordinary pages from being read.
        page.draw_rect(pymupdf.Rect(200,200,250,250),color=None,fill=(.9,.9,.9))
        hints=fraction_hints(page)
        text,_=readable_page(page)
    assert len(hints)==1
    assert hints[0]['numerator']=='p(X|Y)p(Y)' and hints[0]['denominator']=='p(X)'
    assert r'p(Y|X)=\frac{p(X|Y)p(Y)}{p(X)}' in text


def test_missing_fraction_denominator_is_rejected_even_without_latex():
    assert assess('따라서 p(Y|X) = p(X|Y)p(Y)가 성립합니다.','',[])['status']=='needs_review'
    assert assess('조건부확률 $ p(Y|X) $는 $ p(X|Y)p(Y) $로 표현됩니다.','',[])['status']=='needs_review'
    assert assess('p(Y|X) = p(X|Y)p(Y)/p(X)','',[])['status']=='limited_checks_passed'


def test_unsupported_book_title_is_detected_independently_of_valid_citation_ids():
    from backend.quality import unsupported_book_mentions
    title='Deep Learning_ Foundations and Concepts (2024) - Author'
    assert unsupported_book_mentions('Deep Learning_ Foundations and Concepts에서는 PTQ가 제시됩니다.',[title])==[title]
    assert not unsupported_book_mentions('현재 교과서의 근거만 설명합니다.',[title])


def test_uncertain_grading_recommends_review_instead_of_progress(client,book):
    provider=OfflineTaskFixture()
    diagnosis=Agent(ChatRequest(book_id=book['id'],page=1,message='확인 문제를 내 줘'),provider).run()
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='채점',session_id=diagnosis['session_id']),provider)
    agent.evaluation={'uncertain':True,'next_action':'수동 검토 필요'}
    assert agent.dispatch('recommend_next_topic',{})=={'action':'needs_review','topics':[],'message':'수동 검토 필요'}


def test_bad_model_quiz_and_grading_math_cannot_change_learning_records(client,book):
    provider=OfflineTaskFixture()
    diagnosis=Agent(ChatRequest(book_id=book['id'],page=1,message='확인 문제를 내 줘'),provider).run()
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='채점',session_id=diagnosis['session_id'],quiz_id=diagnosis['quiz']['id'],answer='wrong'),provider)
    agent.local_quality=True
    with pytest.raises(ValueError,match='이해도를 변경하지'):
        agent.dispatch('evaluate_answer',{'correct':False,'confidence':.99,'explanation':'p(Y|X)=p(X|Y)p(Y)'})
    assert one('SELECT count(*) n FROM attempts')['n']==0
    assert one('SELECT total FROM mastery')['total']==0
    fresh=Agent(ChatRequest(book_id=book['id'],page=1,message='quiz'),provider)
    fresh.local_quality=True
    rows=fresh.dispatch('get_current_page',{})
    with pytest.raises(ValueError,match='문제를 저장하지'):
        fresh.dispatch('generate_quiz',{'concept':'Bayes','kind':'short','question':'p(Y|X)=p(X|Y)p(Y)를 설명하세요.',
            'answer':'bad','explanation':'conditional probability','source_ids':[rows[0]['id']]})


def test_truncated_generation_retains_actual_usage_and_rejects_output(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'done_reason':'length','eval_count':1000,'prompt_eval_count':123,'message':{'content':'unfinished'}}))) as client:
        provider=OllamaProvider(client)
        with pytest.raises(ValueError,match='출력 한도'):provider.respond([],tool_schemas())
    assert provider.last_usage.input_tokens==123 and provider.last_usage.output_tokens==1000
    assert provider.metrics[-1]['status']=='rejected'
