"""Offline provider contract tests: real orchestration/tools/storage, zero external calls."""
import json
from types import SimpleNamespace as NS
from backend.agent import Agent, ChatRequest
from backend.database import one
from backend.learning import evaluate,save_quiz
from backend import learning

def response(calls=(),text=''):
    return NS(output=[NS(type='function_call',name=n,arguments=json.dumps(a),call_id=f'call-{i}') for i,(n,a) in enumerate(calls)],
              output_text=text,usage=NS(input_tokens=10,output_tokens=5))

class Explainer:
    def __init__(self):self.inputs=[]
    def respond(self,messages,tools):
        self.inputs.append(list(messages))
        context=next(m['content'] for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
        assert 'Gradient descent' in context
        if len(self.inputs)==1:return response([('search_textbook',{'query':'derivatives'})])
        return response(text='## AI 설명\n경사하강법은 기울기를 따라 값을 갱신합니다. $x_{t+1}=x_t-\\eta g_t$')

def test_page_selection_and_followup_are_model_context(client,book):
    provider=Explainer()
    req=ChatRequest(book_id=book['id'],page=2,message='여기 설명',selection='Gradient descent')
    run=Agent(req,provider).run()
    assert run['status']=='completed'
    assert run['sources'] and run['usage']['api_calls']==2
    followup=Agent(ChatRequest(book_id=book['id'],page=2,message='아직 이해가 안 돼',session_id=run['session_id']),Explainer()).run()
    assert followup['status']=='completed'
    # Serialized history is text, not recursive run/event JSON.
    req2=ChatRequest(book_id=book['id'],page=2,message='다시 설명',session_id=run['session_id'])
    next_provider=Explainer();Agent(req2,next_provider).run()
    prior_assistant=[m['content'] for m in next_provider.inputs[0] if isinstance(m,dict) and m.get('role')=='assistant']
    assert prior_assistant and all('"events"' not in text for text in prior_assistant)

class QuizMaker:
    def __init__(self):self.count=0
    def respond(self,messages,tools):
        self.count+=1
        if self.count==1:
            data=next(m['content'] for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
            source=json.loads(data.split(': ',1)[1])[0]
            return response([('explain_concept',{'text':'조건부확률은 조건을 제한한 확률입니다.','source_ids':[source['id']]})])
        if self.count==2:
            source_id=next(json.loads(m['output'])['source_ids'][0] for m in messages if isinstance(m,dict) and m.get('type')=='function_call_output')
            return response([('generate_quiz',{'concept':'Conditional probability','kind':'short','question':'조건부확률을 자신의 말로 설명하세요.','answer':'조건이 주어졌을 때의 확률','explanation':'전체 표본 공간을 조건에 맞게 제한합니다.','source_ids':[source_id]})])
        assert tools==[], 'Quiz must suspend additional tool actions'
        return response(text='조건을 고정해 생각해 보세요. 아래 문제에 답하면 다음 설명을 이어갑니다.')

def test_live_quiz_pause_and_semantic_grading(client,book):
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='이해가 안 돼. 문제를 내줘'),QuizMaker()).run()
    assert run['status']=='awaiting_answer' and run['quiz']
    assert run['usage']['api_calls']==3
    assert 'answer' not in run['quiz']
    class Grader:
        def __init__(self):self.count=0
        def respond(self,messages,tools):
            self.count+=1
            if self.count==1:
                assert any('Private grading rubric' in m.get('content','') for m in messages if isinstance(m,dict))
                return response([('evaluate_answer',{'correct':True,'confidence':.96,'explanation':'조건에 해당하는 경우로 표본 공간을 제한한다는 뜻이므로 정답입니다.','cause':''})])
            if self.count==2:return response([('recommend_next_topic',{})])
            return response(text='정답입니다. 다음에는 곱의 법칙을 살펴보세요.')
    answer=Agent(ChatRequest(book_id=book['id'],page=1,message='답안',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer='조건을 만족하는 경우만 놓고 보는 확률'),Grader()).run()
    assert answer['evaluation']['correct'] and not answer['evaluation']['uncertain']
    assert answer['evaluation']['grading']=='AI 의미 평가 (오판 가능)'
    assert one('SELECT total FROM mastery')['total']==1
    assert one('SELECT state FROM sessions WHERE id=?',(run['session_id'],))['state']=='ready'
    assert answer['quiz'] is None

def test_numeric_truth_cannot_be_overridden(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='quiz'))
    quiz=save_quiz(agent.session_id,book['id'],{'concept':'numeric','kind':'numeric','question':'1 / 4?','answer':'0.25','explanation':'1 / 4 = 0.25','tolerance':.001})
    graded=evaluate(quiz['id'],agent.session_id,'2',{'correct':True,'confidence':1,'explanation':'test'})
    assert not graded['correct']

def test_health_and_free_ai_check(client):
    h=client.get('/api/health').json()
    assert h['app']=='ScholarPilot' and h['project_id'] and h['running_revision']
    state=client.post('/api/ai/check',json={}).json()
    assert not state['ready'] and state['api_calls']==0 and not state['network_checked']
    assert state['reasons']

def test_page_endpoint(client,book):
    data=client.get(f"/api/books/{book['id']}/pages/2").json()
    assert data['has_text'] and all(s['page']==2 for s in data['chunks'])
    assert client.get(f"/api/books/{book['id']}/pages/999").status_code==422

def test_no_paid_connection_call_without_explicit_approval(client,monkeypatch):
    from backend.config import settings
    import backend.main
    monkeypatch.setattr(settings,'ai_mode','live')
    monkeypatch.setattr(settings,'allow_external_ai',True)
    monkeypatch.setattr(settings,'openai_api_key','offline-test-not-a-real-key')
    def forbidden():raise AssertionError('No API call is authorized')
    monkeypatch.setattr(backend.main,'OpenAIProvider',forbidden)
    result=client.post('/api/ai/check',json={}).json()
    assert result['ready'] and result['api_calls']==0

def test_tool_quiz_types_and_low_confidence_semantics(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='quiz'))
    sources=agent.execute('get_current_page',{})
    numeric=agent.execute('generate_quiz',{'concept':'numeric','kind':'numeric','question':'1/4를 소수로 나타내세요.','answer':'0.25','explanation':'분자를 분모로 나눕니다.','tolerance':.001,'source_ids':[sources[0]['id']]})
    graded=evaluate(numeric['id'],agent.session_id,'0.2505')
    assert graded['correct']
    quiz=save_quiz(agent.session_id,book['id'],{'concept':'short','kind':'short','question':'개념 설명','answer':'expected','explanation':'rubric'})
    graded=evaluate(quiz['id'],agent.session_id,'different expression',{'correct':False,'confidence':.6,'explanation':'판단 어려움'})
    assert graded['uncertain']
