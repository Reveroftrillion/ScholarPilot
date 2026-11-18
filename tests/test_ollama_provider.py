import json
from types import SimpleNamespace as NS
import httpx
import pytest
from backend.config import settings
from backend.ollama_provider import OllamaProvider,local_url,local_model,compact_data
from backend.agent import Agent,ChatRequest,tool_schemas
from backend.database import one

@pytest.fixture(autouse=True)
def native_protocol_for_legacy_contract(monkeypatch):
    # Legacy native adapter contracts remain explicitly covered. Production
    # defaults to schema-constrained JSON; those tests opt into it below.
    monkeypatch.setattr(settings,'ollama_tool_format','native')

def test_native_tool_adapter_preserves_names_and_source_outputs():
    captured=[]
    def transport(req):
        assert req.url.host=='127.0.0.1' and 'authorization' not in req.headers
        captured.append(json.loads(req.content))
        return httpx.Response(200,json={'done':True,'done_reason':'stop','message':{'content':'','tool_calls':[{'function':{'name':'search_textbook','arguments':{'query':'Bayes'}}}]},'prompt_eval_count':10,'eval_count':4})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        p=OllamaProvider(client)
        first=p.respond([{'role':'user','content':'질문'}],tool_schemas())
        call=first.output[0]
        native=p.messages([call,{'type':'function_call_output','call_id':call.call_id,'output':'[{"id":"source-real"}]'}])
    assert first.usage.input_tokens==10 and json.loads(call.arguments)=={'query':'Bayes'}
    assert native[-1]['role']=='tool' and native[-1]['tool_name']=='search_textbook'
    assert json.loads(native[-1]['content'])==[{'id':'source-real'}]
    assert captured[0]['think'] is False
    assert captured[0]['tools'][0]['function']['parameters']['additionalProperties'] is False

@pytest.mark.parametrize('url',['https://ollama.com','http://example.com:11434','http://127.0.0.1:11434/remote','http://user:pass@localhost:11434'])
def test_external_and_credential_urls_are_rejected(monkeypatch,url):
    monkeypatch.setattr(settings,'ollama_base_url',url)
    with pytest.raises(ValueError):local_url()

def test_cloud_model_is_rejected(monkeypatch):
    monkeypatch.setattr(settings,'ollama_model','qwen3:cloud')
    with pytest.raises(ValueError):local_model()

@pytest.mark.parametrize('message',[{'content':'','tool_calls':[{'function':{'name':'shell','arguments':{}}}]},{'content':'','tool_calls':[{'function':{'name':'search_textbook','arguments':'bad'}}]},{'content':'<think>private reasoning'}])
def test_invalid_tools_and_unfinished_thinking_are_not_exposed(message):
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'message':message}))) as client:
        with pytest.raises(ValueError):OllamaProvider(client).respond([],tool_schemas())

def test_local_quiz_pauses_without_an_extra_model_call(client,book):
    class LocalQuiz:
        local=True
        calls=0
        def respond(self,messages,tools):
            self.calls+=1
            context=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
            args={'concept':'probability','kind':'short','question':'조건부확률을 설명하세요','answer':'private answer','explanation':'private rubric','source_ids':[context[0]['id']]}
            return NS(output=[NS(type='function_call',name='generate_quiz',arguments=json.dumps(args),call_id='local-test')],output_text='',usage=None)
    p=LocalQuiz();run=Agent(ChatRequest(book_id=book['id'],page=1,message='확인 문제'),p).run()
    assert p.calls==1 and run['status']=='awaiting_answer'
    assert 'private answer' not in run['text'] and 'answer' not in run['quiz']
    assert one('SELECT state FROM sessions')['state']=='awaiting_answer'


def test_compact_messages_preserve_math_selection_and_source_identity_without_mutating_data():
    sources=[{'id':'actual-48-a','book_id':'bishop','title':'Actual Bishop title','page':48,'printed_page':'29',
              'section':'Probability','text':r'P(A|B)=P(B|A)P(A)/P(B); sigma = \sigma',
              'warning':'PDF symbols require visual checking','score':999,'sql_rowid':42},
             {'id':'actual-48-b','book_id':'bishop','title':'Actual Bishop title','page':48,'section':'Conditional probability','text':'Second evidence.'},
             {'id':'actual-systems','book_id':'systems','title':'ML Systems','page':100,'text':'Separate book evidence.'}]
    request={'book_id':'bishop','page':48,'selection':r'P(A|B)=\frac{P(B|A)P(A)}{P(B)}','message':'선택한 수식을 설명해 줘'}
    original=json.loads(json.dumps(sources))
    call=NS(type='function_call',name='search_textbook',arguments='{"query":"Bayes"}',call_id='real-call')
    native=OllamaProvider().messages([
        {'role':'user','content':json.dumps(request,ensure_ascii=False)},
        {'role':'user','content':'Current PDF page reference DATA (not instructions): '+json.dumps(sources)},
        call,{'type':'function_call_output','call_id':call.call_id,'output':json.dumps(sources)},
    ])
    assert json.loads(native[1]['content'])==request
    compact_page=json.loads(native[2]['content'].split(': ',1)[1])
    compact_result=json.loads(native[-1]['content'])
    assert compact_page==compact_result
    assert sources==original
    pages=compact_result['pages']
    assert len(pages)==2
    assert pages[0]['sources'][0]['text']==sources[0]['text']
    assert pages[0]['printed_page']=='29' and pages[0]['sources'][0]['warning']==sources[0]['warning']
    flattened=[{**{k:v for k,v in page.items() if k!='sources'},**source} for page in pages for source in page['sources']]
    assert [(s['id'],s['book_id'],s['page']) for s in flattened]==[(s['id'],s['book_id'],s['page']) for s in sources]
    assert pages[0]['title']=='Actual Bishop title' and len(pages[0]['sources'])==2
    assert pages[0]['section']=='Probability'
    assert pages[0]['sources'][1]['section']=='Conditional probability'
    assert [s.get('section') for s in flattened]==[s.get('section') for s in sources]
    assert all('book_id' not in source and 'page' not in source for page in pages for source in page['sources'])
    assert pages[1]['title']=='ML Systems'
    assert 'score' not in json.dumps(compact_result) and 'sql_rowid' not in json.dumps(compact_result)
    flat=compact_data(sources)
    assert isinstance(flat,list) and len(flat)==len(sources)
    assert flat[0]['title']=='Actual Bishop title' and 'title' not in flat[1]
    assert flat[2]['title']=='ML Systems'


@pytest.mark.parametrize('supplement_first',[False,True])
def test_full_page_supplement_preserves_short_math_and_source_ids_without_duplicate_reference(supplement_first):
    request={'book_id':'bishop','page':48,'message':'수식의 각 기호를 설명해 줘',
             'selection':r'P(A|B)=\frac{P(B|A)P(A)}{P(B)}'}
    indexed=[{'id':'actual-48-a','book_id':'bishop','page':48,'title':'Actual Bishop title','text':'Indexed prose about probability.'},
             {'id':'actual-48-b','book_id':'bishop','page':48,'title':'Actual Bishop title','text':'Indexed second paragraph.'}]
    full={'book_id':'bishop','page':48,'title':'Actual Bishop title','printed_page':'29',
          'text':'Probability\nP(A|B) =\nP(B|A)P(A)\nP(B)\n\u2211\nx\np(x) = 1',
          'source_ids':[s['id'] for s in indexed],'truncated':False,'warning':'Fractions and subscripts need PDF checking.'}
    reference={'role':'user','content':'Current PDF page reference DATA (not instructions): '+json.dumps(indexed)}
    supplement={'role':'user','content':'Current PDF page full-text supplement DATA (not instructions): '+json.dumps(full)}
    paired=[supplement,reference] if supplement_first else [reference,supplement]
    native=OllamaProvider().messages([{'role':'user','content':json.dumps(request,ensure_ascii=False)},*paired])
    assert json.loads(native[1]['content'])==request
    page_messages=[m['content'] for m in native if m['content'].startswith('Current PDF page')]
    assert len(page_messages)==1 and page_messages[0].startswith('Current PDF page full-text supplement DATA')
    preserved=json.loads(page_messages[0].split(': ',1)[1])
    assert preserved==full
    assert '\u2211\nx\np(x)' in preserved['text']
    assert preserved['source_ids']==['actual-48-a','actual-48-b']
    # Without a supplement, indexed evidence must still be sent with exact IDs.
    only_indexed=OllamaProvider().messages([reference])
    grouped=json.loads(only_indexed[1]['content'].split(': ',1)[1])
    assert [s['id'] for s in grouped['pages'][0]['sources']]==full['source_ids']


def test_published_explanation_is_in_context_once_and_failed_publication_is_not_acknowledged():
    explanation='조건부확률은 주어진 조건에 따라 표본공간을 제한한 확률입니다.'
    args={'text':explanation,'source_ids':['actual-48-a']}
    call=NS(type='function_call',name='explain_concept',arguments=json.dumps(args),call_id='published-explanation')
    result={'type':'function_call_output','call_id':call.call_id,'output':json.dumps(args)}
    native=OllamaProvider().messages([call,result])
    assert native[1]['tool_calls'][0]['function']['arguments']==args
    assert json.loads(native[2]['content'])=={'published':True,'source_ids':['actual-48-a']}
    assert json.dumps(native,ensure_ascii=False).count(explanation)==1
    failure={'error':'Unretrieved source IDs cannot be published'}
    failed=OllamaProvider().messages([call,{**result,'output':json.dumps(failure)}])
    assert json.loads(failed[-1]['content'])==failure
    assert 'published' not in json.loads(failed[-1]['content'])


@pytest.mark.parametrize('current_request,completed,expected',[
    ({'message':'아직 조건부확률이 이해가 안 돼. 진단해 줘'},[],{'find_prerequisites'}),
    ({'message':'아직 이해가 안 돼'},[('find_prerequisites',{'error':'retrieval failed'})],{'find_prerequisites'}),
    ({'message':'아직 이해가 안 돼'},[('find_prerequisites',[])],{'explain_concept'}),
    ({'message':'아직 이해가 안 돼'},[('find_prerequisites',[]),('explain_concept',{'error':'invalid source'})],{'explain_concept'}),
    ({'message':'아직 이해가 안 돼'},[('find_prerequisites',[]),('explain_concept',{'source_ids':['real-source']})],{'generate_quiz'}),
    ({'message':'두 책을 비교해 줘','scope':'all'},[],{'search_across_books'}),
    ({'message':'선택한 책을 비교해 줘','scope':'selected'},[],{'search_across_books'}),
    ({'message':'두 책을 비교해 줘','scope':'all'},[('search_across_books',[])],{'explain_concept'}),
    ({'message':'답안을 평가해 줘','quiz_id':'actual-quiz'},[],{'evaluate_answer'}),
    ({'message':'답안을 평가해 줘','quiz_id':'actual-quiz'},[('evaluate_answer',{'correct':False})],{'find_prerequisites'}),
    ({'message':'답안을 평가해 줘','quiz_id':'actual-quiz'},[('evaluate_answer',{'correct':False}),('find_prerequisites',[])],{'explain_concept'}),
    ({'message':'답안을 평가해 줘','quiz_id':'actual-quiz'},[('evaluate_answer',{'correct':False}),('find_prerequisites',[]),('explain_concept',{'text':'feedback'})],{'recommend_next_topic'}),
])
def test_stage_menu_advances_only_after_successful_tool_results(current_request,completed,expected):
    captured=[]
    def transport(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200,json={'message':{'content':'한국어 응답'},'done_reason':'stop'})
    # Include a prior request to ensure the current turn, rather than the old
    # topic, determines the next tool menu.
    messages=[{'role':'user','content':json.dumps({'book_id':'old-book','message':'아직 이해가 안 돼'})},
              {'role':'user','content':json.dumps({'book_id':'bishop',**current_request},ensure_ascii=False)}]
    for i,(name,result) in enumerate(completed):
        call_id=f'actual-stage-{i}'
        messages.extend([NS(type='function_call',name=name,arguments='{}',call_id=call_id),
                         {'type':'function_call_output','call_id':call_id,'output':json.dumps(result)}])
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        OllamaProvider(client).respond(messages,tool_schemas())
    assert {t['function']['name'] for t in captured[0]['tools']}==expected


def test_local_published_explanation_ends_without_redundant_synthesis(client,book):
    class LocalExplanation:
        local=True
        calls=0
        def respond(self,messages,tools):
            self.calls+=1
            assert self.calls==1,'A published local explanation must not trigger another generation'
            context=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
            args={'text':'조건부확률은 조건이 주어진 후의 확률입니다. $P(A|B)=P(A,B)/P(B)$.','source_ids':[context[0]['id']]}
            return NS(output=[NS(type='function_call',name='explain_concept',arguments=json.dumps(args),call_id='local-explanation')],output_text='',usage=None)
    provider=LocalExplanation()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='이 페이지의 조건부확률을 설명해 줘'),provider).run()
    assert run['status']=='completed' and provider.calls==1 and run['usage']['api_calls']==1
    assert 'P(A|B)' in run['text']
    assert [(e['tool'],e['status']) for e in run['events']]==[('get_current_page','ok'),('explain_concept','ok')]


def test_local_diagnosis_does_not_stop_after_prerequisite_explanation(client,book):
    class LocalDiagnosis:
        local=True
        calls=0
        def respond(self,messages,tools):
            self.calls+=1
            assert self.calls<=3,'No final generation is needed after a persisted local quiz'
            context=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
            source=context[0]['id']
            name,args=[
                ('find_prerequisites',{'concept':'conditional probability','candidates':['joint probability']}),
                ('explain_concept',{'text':'선수 개념인 결합확률부터 확인합니다.','source_ids':[source]}),
                ('generate_quiz',{'concept':'conditional probability','kind':'short','question':'조건부확률은 무엇인가요?',
                                  'answer':'private conditional answer','explanation':'private conditional rubric','source_ids':[source]})
            ][self.calls-1]
            return NS(output=[NS(type='function_call',name=name,arguments=json.dumps(args),call_id=f'local-diagnosis-{self.calls}')],output_text='',usage=None)
    provider=LocalDiagnosis()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='아직 조건부확률이 이해가 안 돼. 진단해 줘'),provider).run()
    assert run['status']=='awaiting_answer' and provider.calls==3
    assert [e['tool'] for e in run['events']]==['get_current_page','find_prerequisites','explain_concept','generate_quiz']
    assert all(e['status']=='ok' for e in run['events'])
    assert '선수 개념' in run['text'] and run['quiz']['question']=='조건부확률은 무엇인가요?'
    assert 'private conditional answer' not in json.dumps(run,ensure_ascii=False)
    assert 'private conditional rubric' not in json.dumps(run,ensure_ascii=False)


def test_local_grading_stops_after_recommendation_and_restores_recorded_mastery(client,book,monkeypatch):
    monkeypatch.setattr(settings,'ai_mode','live')
    monkeypatch.setattr(settings,'ai_provider','ollama')
    class SeedQuiz:
        local=True
        def respond(self,messages,tools):
            context=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page reference'))
            args={'concept':'conditional probability','kind':'short','question':'조건부확률이 무엇인지 설명하세요.',
                  'answer':'B라는 조건 아래에서 A가 일어날 확률','explanation':'조건 B가 주어진 표본공간을 사용합니다.',
                  'source_ids':[context[0]['id']]}
            return NS(output=[NS(type='function_call',name='generate_quiz',arguments=json.dumps(args),call_id='seed-quiz')],output_text='',usage=None)
    diagnosis=Agent(ChatRequest(book_id=book['id'],page=1,message='조건부확률 진단 문제'),SeedQuiz()).run()
    assert diagnosis['status']=='awaiting_answer' and 'answer' not in diagnosis['quiz']
    class LocalGrader:
        local=True
        calls=0
        def respond(self,messages,tools):
            self.calls+=1
            assert self.calls<=4,'A recommendation already completes the grading flow; no synthesis request is needed'
            context=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page reference'))
            name,args=[
                ('evaluate_answer',{'correct':False,'confidence':.98,'explanation':'조건부확률이 항상 1이라는 주장은 틀립니다.','cause':'조건과 확률 1의 사건을 혼동했습니다.'}),
                ('find_prerequisites',{'concept':'conditional probability','candidates':['joint probability']}),
                ('explain_concept',{'text':'결합확률과 조건부확률을 구분하세요. 조건 B가 주어진 범위에서 A의 비율을 구합니다.','source_ids':[context[0]['id']]}),
                ('recommend_next_topic',{})
            ][self.calls-1]
            return NS(output=[NS(type='function_call',name=name,arguments=json.dumps(args),call_id=f'local-grade-{self.calls}')],output_text='',usage=None)
    grader=LocalGrader()
    wrong_answer='조건과 상관없이 언제나 1입니다.'
    request=ChatRequest(book_id=book['id'],page=1,message='답안을 채점하고 복습을 추천해 주세요.',
                        session_id=diagnosis['session_id'],quiz_id=diagnosis['quiz']['id'],answer=wrong_answer)
    graded=Agent(request,grader).run()
    assert graded['status']=='completed' and graded['quiz'] is None
    assert grader.calls==graded['usage']['api_calls']==4
    assert graded['evaluation']['correct'] is False and graded['evaluation']['uncertain'] is False
    assert graded['evaluation']['grading']=='AI 의미 평가 (오판 가능)'
    assert [e['tool'] for e in graded['events']]==['get_current_page','evaluate_answer','find_prerequisites','explain_concept','recommend_next_topic','update_mastery']
    assert all(e['status']=='ok' for e in graded['events'])
    recommendation=next(e['output'] for e in graded['events'] if e['tool']=='recommend_next_topic')
    assert recommendation['action']=='review' and recommendation['message'] in graded['text']
    assert '조건 B가 주어진 범위' in graded['text'] and '**다음 학습**' in graded['text']
    attempt=one('SELECT * FROM attempts WHERE quiz_id=?',(diagnosis['quiz']['id'],))
    assert attempt['answer']==wrong_answer and attempt['correct']==0 and attempt['uncertain']==0
    assert one('SELECT COUNT(*) AS n FROM attempts')['n']==1
    assert one('SELECT state FROM sessions WHERE id=?',(diagnosis['session_id'],))['state']=='ready'
    mastery=one('SELECT * FROM mastery WHERE concept_id=?',(graded['evaluation']['concept_id'],))
    assert mastery['status']=='복습 필요' and mastery['correct']==0 and mastery['total']==1
    stored=json.loads(one('SELECT response FROM runs WHERE id=?',(graded['id'],))['response'])
    assert stored==graded
    restored=client.get(f"/api/books/{book['id']}/history").json()
    assert restored[-1]['response']==graded
    dashboard=client.get('/api/dashboard').json()
    assert any(row['concept_id']==graded['evaluation']['concept_id'] and row['status']=='복습 필요' for row in dashboard['mastery'])
    assert grader.calls==4


def test_json_action_wire_schema_and_parser_keep_model_generated_search(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    captured=[]
    action={'tool':'search_textbook','arguments':{'query':'conditional probability Bayes'}}
    def transport(req):
        assert req.url.host=='127.0.0.1' and 'authorization' not in req.headers
        captured.append(json.loads(req.content))
        return httpx.Response(200,json={'message':{'content':json.dumps(action)},'done_reason':'stop','prompt_eval_count':123,'eval_count':17})
    request={'book_id':'bishop','page':48,'message':'이 페이지의 베이즈 정리를 한국어로 설명해 줘','selection':r'P(A|B)=P(B|A)P(A)/P(B)'}
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider=OllamaProvider(client)
        response=provider.respond([{'role':'user','content':json.dumps(request,ensure_ascii=False)}],tool_schemas())
    body=captured[0]
    assert 'tools' not in body and body['truncate'] is False and body['shift'] is False
    assert body['think'] is False and body['stream'] is False
    choices=body['format']['oneOf']
    assert {branch['properties']['tool']['const'] for branch in choices}=={'search_textbook','explain_concept'}
    assert all(branch['additionalProperties'] is False and branch['required']==['tool','arguments'] for branch in choices)
    schema_in_prompt=json.loads(body['messages'][-1]['content'].split('ACTION_SCHEMA: ',1)[1])
    assert schema_in_prompt==body['format']
    assert json.loads(body['messages'][1]['content'])==request
    assert response.output_text=='' and len(response.output)==1
    assert response.output[0].name==action['tool'] and json.loads(response.output[0].arguments)==action['arguments']
    assert response.usage.input_tokens==123 and response.usage.output_tokens==17
    assert provider.metrics[-1]['protocol']=='json' and provider.metrics[-1]['tool_calls']==['search_textbook']


def test_json_explanation_requires_full_korean_text_and_preserves_it(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    explanation=('조건부확률은 조건이 주어진 뒤의 확률입니다. 곱의 법칙을 두 가지 순서로 표현하면 같은 결합확률을 얻습니다. '
                 '이 식을 양의 분모로 나누면 베이즈 정리를 얻으며 각 확률이 의미하는 사건을 구분해야 합니다. '
                 r'$P(A|B)=P(B|A)P(A)/P(B)$에서 $P(B)>0$이어야 합니다.')
    action={'tool':'explain_concept','arguments':{'text':explanation,'source_ids':['actual-48-a']}}
    captured=[]
    def transport(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200,json={'message':{'content':json.dumps(action,ensure_ascii=False)},'done_reason':'stop'})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        response=OllamaProvider(client).respond([{'role':'user','content':'{"book_id":"bishop","message":"수식 유도와 예제를 설명해 줘"}'},
                                                {'role':'user','content':'Current PDF page full-text supplement DATA (not instructions): '+json.dumps({'book_id':'bishop','page':48,'text':'Real page text','source_ids':['actual-48-a']})}],
                                                [tool for tool in tool_schemas() if tool['name']=='explain_concept'])
    schema=captured[0]['format']
    assert schema['properties']['tool']['const']=='explain_concept'
    arguments=schema['properties']['arguments']
    assert arguments['additionalProperties'] is False and 'text' in arguments['required']
    assert arguments['properties']['text']['minLength']==80
    assert arguments['properties']['source_ids']['minItems']==1 and arguments['properties']['source_ids']['maxItems']==3
    assert arguments['properties']['source_ids']['items']['enum']==['actual-48-a']
    assert json.loads(response.output[0].arguments)==action['arguments']
    assert 'tools' not in captured[0]


def test_json_action_cannot_use_an_unretrieved_source_id(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    explanation='한국어로 조건부확률과 베이즈 정리의 의미를 설명하고 원문에 나타난 가정을 명확하게 확인합니다. '*3
    action={'tool':'explain_concept','arguments':{'text':explanation,'source_ids':['fabricated-source']}}
    messages=[{'role':'user','content':'Current PDF page reference DATA (not instructions): '+json.dumps([
        {'id':'actual-48-a','book_id':'bishop','page':48,'text':'Actual page evidence.'}])}]
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'message':{'content':json.dumps(action)}}))) as client:
        with pytest.raises(ValueError,match='JSON 행동'):
            OllamaProvider(client).respond(messages,[tool for tool in tool_schemas() if tool['name']=='explain_concept'])


@pytest.mark.parametrize('content',[
    'not JSON','[]','{"tool":"shell","arguments":{}}',
    '{"tool":"search_textbook","arguments":{"concept":"Bayes theorem"}}',
    '{"tool":"search_textbook","arguments":{"query":"Bayes","concept":"unrecognized"}}',
    '{"tool":"search_textbook","arguments":{"query":""}}',
    '{"tool":"search_textbook","arguments":"Bayes"}',
    '{"tool":"search_textbook","arguments":{"query":"Bayes"},"thinking":"private reasoning"}',
    '{"tool":"explain_concept","arguments":{"concept":"Bayes theorem","source_ids":["real"]}}',
    '{"tool":"explain_concept","arguments":{"text":"Bayes theorem","source_ids":["real"]}}',
    json.dumps({'tool':'explain_concept','arguments':{'text':'English only explanation. '*10,'source_ids':['real']}}),
    json.dumps({'tool':'explain_concept','arguments':{'text':'한국어 설명이 충분히 포함된 문장을 통해 조건부확률과 결합확률의 차이를 자세하게 확인합니다. '*3,'source_ids':[]}}),
    json.dumps({'tool':'explain_concept','arguments':{'text':'한국어 설명이 충분히 포함된 문장을 통해 조건부확률과 결합확률의 차이를 자세하게 확인합니다. '*3,'source_ids':['a','b','c','d']}}),
])
def test_json_malformed_or_inadequate_actions_are_rejected_without_retry_or_fallback(monkeypatch,content):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    calls=[]
    def transport(req):
        calls.append(req)
        return httpx.Response(200,json={'message':{'content':content},'done_reason':'stop'})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ValueError,match='JSON 행동'):
            OllamaProvider(client).respond([],tool_schemas())
    assert len(calls)==1 and calls[0].url.host=='127.0.0.1'
    assert 'tools' not in json.loads(calls[0].content)


def test_json_protocol_rejects_native_call_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    message={'content':'','tool_calls':[{'function':{'name':'search_textbook','arguments':{'query':'Bayes'}}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'message':message}))) as client:
        with pytest.raises(ValueError,match='자동 전환하지 않습니다'):
            OllamaProvider(client).respond([],tool_schemas())


def test_json_history_uses_action_and_grouped_tool_result_without_native_tool_tags(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    evidence=[{'id':'bishop-real','book_id':'bishop','title':'Bishop','page':48,'section':'Probability','text':r'P(A|B) = P(B|A)P(A)/P(B)'},
              {'id':'systems-real','book_id':'systems','title':'ML Systems','page':48,'text':'Different book, same PDF page number.'}]
    action={'tool':'search_across_books','arguments':{'query':'conditional probability'}}
    call=NS(type='function_call',name=action['tool'],arguments=json.dumps(action['arguments']),call_id='actual-cross-book')
    native=OllamaProvider().messages([call,{'type':'function_call_output','call_id':call.call_id,'output':json.dumps(evidence)}])
    assert all(message['role']!='tool' and 'tool_calls' not in message for message in native)
    assert native[1]['role']=='assistant' and json.loads(native[1]['content'])==action
    result=json.loads(native[2]['content'])
    assert native[2]['role']=='user' and result['type']=='TOOL_RESULT' and result['tool']==action['tool']
    pages=result['result']['pages']
    assert [(p['book_id'],p['page']) for p in pages]==[('bishop',48),('systems',48)]
    assert [p['sources'][0]['id'] for p in pages]==['bishop-real','systems-real']
    assert pages[0]['sources'][0]['text']==evidence[0]['text']


def test_json_final_response_with_no_offered_tools_has_explicit_answer_schema(monkeypatch):
    monkeypatch.setattr(settings,'ollama_tool_format','json')
    answer='이미 확인한 교과서 원문을 다시 살펴보세요.'
    captured=[]
    def transport(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200,json={'message':{'content':json.dumps({'answer':answer})}})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        response=OllamaProvider(client).respond([],[])
    assert captured[0]['format']['required']==['answer'] and 'tools' not in captured[0]
    assert response.output==[] and response.output_text==answer


def test_local_same_tool_argument_failures_stop_after_two_requests(client,book):
    class InvalidArguments:
        local=True
        calls=0
        def respond(self,messages,tools):
            self.calls+=1
            assert self.calls<=2
            args={'concept':f'unsupported-{self.calls}','source_ids':[]}
            return NS(output=[NS(type='function_call',name='explain_concept',arguments=json.dumps(args),call_id=f'invalid-{self.calls}')],output_text='',usage=None)
    provider=InvalidArguments()
    run=Agent(ChatRequest(book_id=book['id'],page=1,message='베이즈 정리를 설명해 줘'),provider).run()
    assert run['status']=='error' and provider.calls==2 and run['usage']['api_calls']==2
    assert '두 번' in run['text']
    failures=[event for event in run['events'] if event['tool']=='explain_concept']
    assert len(failures)==2 and all(event['status']=='error' for event in failures)
