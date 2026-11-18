import json
from types import SimpleNamespace as NS
import pytest
from backend.config import Settings,settings
from backend.providers import OpenAIProvider
from backend.agent import Agent,ChatRequest
from backend.database import one
from scripts.bayes_evaluation import BudgetedProvider,OfflineResponsesClient,safe_copy,main

def provider():
    return BudgetedProvider(OpenAIProvider(OfflineResponsesClient()))

def test_sdk_shaped_bayes_workflow(client,book,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'ai_mode','live')
    # Existing synthetic book is 2 pages: use the same workflow protocol directly.
    p=provider()
    p.trace_path=tmp_path/'model-calls.json'
    initial=Agent(ChatRequest(book_id=book['id'],page=1,message='Bayes theorem'),p).run()
    assert initial['status']=='completed'
    assert any(e['tool']=='search_textbook' for e in initial['events'])
    follow=Agent(ChatRequest(book_id=book['id'],page=1,message='이해하지 못했어요',session_id=initial['session_id']),p).run()
    assert follow['status']=='awaiting_answer'
    assert 'answer' not in follow['quiz']
    assert one('SELECT state FROM sessions WHERE id=?',(initial['session_id'],))['state']=='awaiting_answer'
    graded=Agent(ChatRequest(book_id=book['id'],page=1,message='모의 오답',session_id=initial['session_id'],quiz_id=follow['quiz']['id'],answer='항상 1인 확률'),p).run()
    assert graded['status']=='completed' and not graded['evaluation']['correct']
    assert one('SELECT total,status FROM mastery')['total']==1
    assert one('SELECT total,status FROM mastery')['status']=='복습 필요'
    assert any(e['tool']=='recommend_next_topic' for e in graded['events'])
    assert len(p.records)==11
    assert p.records[0]['request']['instructions']
    assert all(r['status']=='completed' for r in p.records)
    assert len(json.loads(p.trace_path.read_text(encoding='utf-8')))==11

def test_budget_blocks_before_transport_and_retains_reservation_on_failure():
    class Fail:
        calls=0
        def respond(self,*args):self.calls+=1;raise RuntimeError('private diagnostic')
    f=Fail();p=BudgetedProvider(f,budget_usd=.00001)
    with pytest.raises(ValueError,match='reservation'):p.respond([],[])
    assert f.calls==0
    p=BudgetedProvider(f,max_calls=1)
    with pytest.raises(ValueError,match='no automatic retry'):p.respond([],[])
    assert p.reserved>0 and 'private diagnostic' not in json.dumps(p.records)
    with pytest.raises(ValueError,match='call limit'):p.respond([],[])
    assert f.calls==1

def test_input_limit_never_sends_large_request():
    p=provider()
    with pytest.raises(ValueError,match='input size'):p.respond([{'role':'user','content':'x'*80000}],[])
    assert not p.records

def test_luna_model_and_reasoning_are_sent_to_sdk():
    args={}
    class Client:
        def __init__(self):self.responses=self
        def create(self,**kwargs):args.update(kwargs);return NS(status='completed')
    OpenAIProvider(Client(),model='gpt-6-luna').respond([],[])
    assert args['model']=='gpt-6-luna'
    assert args['reasoning']=={'effort':'low'}

def test_incomplete_sdk_response_is_not_completed():
    class Client:
        def __init__(self):self.responses=self
        def create(self,**kwargs):return NS(status='incomplete',output_text='partial')
    with pytest.raises(ValueError,match='완료되지'):OpenAIProvider(Client()).respond([],[])

def test_installed_openai_sdk_serializes_responses_without_network():
    import httpx
    from openai import OpenAI
    bodies=[]
    def transport(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'resp-offline','object':'response','created_at':0,
            'status':'completed','model':'gpt-4.1-mini-2025-04-14',
            'output':[{'type':'message','id':'msg-offline','role':'assistant','status':'completed',
                'content':[{'type':'output_text','text':'오프라인 SDK 계약 검증','annotations':[]}]}],
            'usage':{'input_tokens':4,'output_tokens':3,'total_tokens':7}})
    with OpenAI(api_key='offline-not-a-real-key',http_client=httpx.Client(transport=httpx.MockTransport(transport)),max_retries=0) as sdk:
        response=OpenAIProvider(sdk,model='gpt-4.1-mini-2025-04-14').respond([{'role':'user','content':'test'}],[])
    assert response.output_text=='오프라인 SDK 계약 검증'
    assert response.usage.input_tokens==4
    assert bodies[0]['store'] is False and bodies[0]['max_output_tokens']==2400
    assert bodies[0]['parallel_tool_calls'] is False

def test_live_approval_gate_precedes_provider_or_data(monkeypatch):
    import scripts.bayes_evaluation as module
    def forbidden(*a,**kw):raise AssertionError('Must not prepare data or API')
    monkeypatch.setattr(module,'OpenAIProvider',forbidden)
    monkeypatch.setattr(module,'prepare_isolated',forbidden)
    with pytest.raises(SystemExit,match='approval'):main(['--mode','live'])

def test_secrets_and_hidden_reasoning_not_in_evaluation_trace(monkeypatch):
    monkeypatch.setattr(settings,'openai_api_key','test-secret-local')
    trace=safe_copy({'input':[{'type':'reasoning','summary':'hidden'},{'type':'message','text':'test-secret-local'}]})
    assert 'hidden' not in json.dumps(trace) and 'test-secret-local' not in json.dumps(trace)

def test_shell_api_key_cannot_override_dotenv(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','shell-secret-must-not-win')
    config=Settings()
    assert config.openai_api_key!='shell-secret-must-not-win'
    assert 'openai_api_key' not in config.model_dump()
    assert 'shell-secret-must-not-win' not in repr(config)

def test_real_client_construction_is_pinned_and_has_no_retries(monkeypatch):
    import openai
    args={}
    def construct(**kwargs):args.update(kwargs);return NS()
    monkeypatch.setattr(settings,'allow_external_ai',True)
    monkeypatch.setattr(settings,'ai_provider','openai')
    monkeypatch.setattr(settings,'openai_api_key','offline-local-key')
    monkeypatch.setattr(openai,'OpenAI',construct)
    OpenAIProvider()
    assert args['base_url']=='https://api.openai.com/v1'
    assert args['max_retries']==0 and args['timeout']==45

def test_credit_error_is_safe_and_persisted_before_transport(tmp_path):
    from backend.providers import AIRequestError
    path=tmp_path/'calls.json'
    class CreditError(Exception):
        status_code=429
        code='credit_balance_exhausted'
    class Client:
        def __init__(self):self.responses=self;self.calls=0
        def create(self,**kwargs):
            self.calls+=1
            saved=json.loads(path.read_text(encoding='utf-8'))
            assert len(saved)==1 and saved[0]['status']=='started'
            raise CreditError('private SDK details and credential must not be retained')
    client=Client();p=BudgetedProvider(OpenAIProvider(client));p.trace_path=path
    with pytest.raises(ValueError,match='크레딧'):p.respond([],[])
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert client.calls==1 and saved[0]['http_status']==429
    assert saved[0]['error_code']=='credit_balance_exhausted'
    assert saved[0]['usage']=={'input_tokens':None,'output_tokens':None}
    assert saved[0]['estimated_usd'] is None
    assert 'private SDK' not in path.read_text(encoding='utf-8')

def test_failed_real_path_does_not_create_learning_attempt(client,book,monkeypatch):
    from backend.providers import AIRequestError
    import backend.agent
    monkeypatch.setattr(settings,'ai_mode','live')
    class Refused:
        calls=0
        def respond(self,*args):self.calls+=1;raise AIRequestError('credit_balance_exhausted',429)
    provider=Refused();monkeypatch.setattr(backend.agent,'OpenAIProvider',lambda:provider)
    run=client.post('/api/chat',json={'book_id':book['id'],'page':1,'message':'Bayes theorem'}).json()
    assert run['status']=='error' and '크레딧' in run['text']
    assert provider.calls==1
    assert one('SELECT count(*) AS n FROM attempts')['n']==0
    assert one('SELECT count(*) AS n FROM quizzes')['n']==0
    assert one('SELECT count(*) AS n FROM mastery')['n']==0
