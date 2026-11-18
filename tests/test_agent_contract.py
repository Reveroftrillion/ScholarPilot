import json
from types import SimpleNamespace as NS
from backend.agent import Agent,ChatRequest
from backend.providers import OpenAIProvider
from backend.config import settings
from backend.database import one

class FakeResponses:
    def __init__(self):self.calls=[]
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if len(self.calls)==1:
            return NS(output=[NS(type='function_call',name='search_textbook',arguments='{"query":"probability"}',call_id='c1')],usage=NS(input_tokens=10,output_tokens=5),output_text='')
        outputs=[i for i in kwargs['input'] if isinstance(i,dict) and i.get('type')=='function_call_output']
        assert outputs and outputs[0]['call_id']=='c1'
        evidence=json.loads(outputs[0]['output'])
        assert evidence[0]['page']==1
        return NS(output=[],output_text='검색된 확률 원문에 기반한 테스트 응답',usage=NS(input_tokens=12,output_tokens=8))

def test_responses_real_dispatch_and_feedback(client,book):
    fake=FakeResponses()
    provider=OpenAIProvider(client=NS(responses=fake))
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='probability'),provider).run()
    assert run['status']=='completed'
    assert [e['tool'] for e in run['events']]==['get_current_page','search_textbook']
    assert run['usage']=={'api_calls':2,'input_tokens':22,'output_tokens':13}
    assert fake.calls[0]['store'] is False
    assert 'tools' in fake.calls[0]
    assert one('SELECT count(*) AS n FROM events')['n']==2

def test_tool_boundaries_and_repetition(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='probability'))
    assert agent.execute('get_section',{'chunk_id':'fake'})['error']
    assert agent.execute('explain_concept',{'text':'invented','source_ids':['fake']})['error']
    assert agent.execute('evaluate_answer',{})['error']
    agent.execute('search_textbook',{'query':'probability'})
    try:agent.execute('search_textbook',{'query':'probability'})
    except ValueError:pass
    else:assert False,'Repeated tool must stop'
    try:agent.execute('shell',{'command':'whoami'})
    except ValueError:pass
    else:assert False,'Unknown tool must stop'

def test_step_limit(client,book,monkeypatch):
    monkeypatch.setattr(settings,'max_agent_steps',1)
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='probability')).run()
    assert run['status']=='error'
    assert len(run['events'])==1

def test_provider_failure_redacted(client,book):
    class Failing:
        def respond(self,*args):raise RuntimeError('secret-key-do-not-log')
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='probability'),Failing()).run()
    assert run['status']=='error'
    assert 'secret-key' not in json.dumps(run)
