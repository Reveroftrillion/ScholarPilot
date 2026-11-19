import json
import pymupdf
from backend.database import one, many
from backend.learning import grade
from backend.main import app
from .conftest import pdf_bytes,restart_test_client

def test_upload_reader_sources(client,book):
    assert book['status']=='ready'
    assert book['pages']==2
    assert client.get(f"/api/books/{book['id']}/pdf").content.startswith(b'%PDF')
    assert client.get(f"/api/books/{book['id']}/cover").headers['content-type']=='image/png'
    assert len(client.get(f"/api/books/{book['id']}/sections").json())==2
    rows=client.post('/api/search',json={'query':'조건부 확률','book_ids':[book['id']]}).json()
    assert rows and rows[0]['page']==1 and rows[0]['book_id']==book['id']
    assert rows[0]['printed_page'] is None

def test_three_books_delete_isolation(client):
    ids=[]
    for i in range(3):
        r=client.post('/api/books',files={'file':(f'{i}.pdf',pdf_bytes(f'Textbook {i}'),'application/pdf')})
        ids.append(r.json()['id'])
    rows=client.post('/api/search',json={'query':'probability'}).json()
    assert set(r['book_id'] for r in rows)==set(ids)
    for bid in ids:
        found=client.post('/api/search',json={'query':'probability','book_ids':[bid]}).json()
        assert {r['book_id'] for r in found}=={bid}
    selected=client.post('/api/search',json={'query':'probability','book_ids':ids[1:]}).json()
    assert {r['book_id'] for r in selected}==set(ids[1:])
    assert client.delete('/api/books/'+ids[0]).status_code==200
    rows=client.post('/api/search',json={'query':'probability'}).json()
    assert {r['book_id'] for r in rows}==set(ids[1:])
    assert client.get('/api/books/'+ids[0]+'/pdf').status_code==404

def test_agent_pause_resume_persistence(client,book):
    request={'book_id':book['id'],'page':1,'message':'Bayes theorem','selection':'Conditional probability'}
    run=client.post('/api/chat',json=request).json()
    assert run['status']=='awaiting_answer',run
    assert [e['tool'] for e in run['events']]==['get_current_page','search_textbook','get_section','get_learning_history','find_prerequisites','explain_concept','generate_quiz','recommend_next_topic']
    assert all(e['status']=='ok' for e in run['events'])
    assert 'answer' not in run['quiz']
    q=one('SELECT payload FROM quizzes WHERE id=?',(run['quiz']['id'],))
    answer=json.loads(q['payload'])['answer']
    response=client.post('/api/chat',json={**request,'session_id':run['session_id'],'quiz_id':run['quiz']['id'],'answer':answer,'message':'답안 제출'}).json()
    assert response['evaluation']['correct']
    assert [e['tool'] for e in response['events']]==['evaluate_answer','update_mastery','get_learning_history','recommend_next_topic']
    dashboard=client.get('/api/dashboard').json()
    assert dashboard['mastery'][0]['status']=='학습 중'
    assert dashboard['accuracy']==100
    client.post('/api/chat',json={**request,'session_id':run['session_id'],'quiz_id':run['quiz']['id'],'answer':answer})
    assert client.get('/api/dashboard').json()['mastery'][0]['total']==1
    client.put(f"/api/books/{book['id']}/position",json={'page':2})
    # New app lifespan / SQLite connection restores all state.
    with restart_test_client(app) as restarted:
        assert restarted.get('/api/books').json()[0]['last_page']==2
        assert restarted.get('/api/dashboard').json()['mastery'][0]['total']==1
        assert len(restarted.get(f"/api/books/{book['id']}/history").json())==3

def test_baseline_has_no_diagnostic(client,book):
    run=client.post('/api/chat',json={'book_id':book['id'],'page':1,'message':'probability','strategy':'baseline'}).json()
    assert run['quiz'] is None
    assert [e['tool'] for e in run['events']]==['search_textbook','get_section','explain_concept']

def test_errors(client,book):
    assert client.post('/api/books',files={'file':('bad.pdf',b'bad')}).status_code==400
    assert client.post('/api/books',files={'file':('bad.pdf',b'%PDF-corrupt')}).status_code==400
    content=client.get(f"/api/books/{book['id']}/pdf").content
    assert client.post('/api/books',files={'file':('duplicate.pdf',content)}).status_code==409
    assert client.put(f"/api/books/{book['id']}/position",json={'page':999}).status_code==422
    assert client.post('/api/chat',json={'book_id':book['id'],'page':999,'message':'test'}).status_code==422
    assert client.post('/api/search',json={'query':'" OR ** NOT /'}).status_code==200
    assert client.post('/api/search',json={'query':'zzzznonexistent'}).json()==[]
    assert client.post('/api/search',json={'query':'probability','book_ids':[]}).json()==[]
    assert client.post('/api/chat',json={'book_id':book['id'],'page':1,'message':'test','session_id':'other'}).status_code==422
    assert client.get('/api/health',headers={'origin':'https://untrusted.example'}).status_code==403
    assert client.get('/api/health',headers={'host':'evil.example'}).status_code==403

def test_blank_pdf(client):
    doc=pymupdf.open();doc.new_page();data=doc.tobytes();doc.close()
    r=client.post('/api/books',files={'file':('scan.pdf',data)})
    assert r.status_code==201
    assert client.get('/api/books').json()[0]['status']=='no_text'
    assert client.post('/api/chat',json={'book_id':r.json()['id'],'page':1,'message':'explain'}).status_code==409

def test_reindex_and_highlights(client,book):
    bid=book['id'];before=many('SELECT id FROM chunks WHERE book_id=?',(bid,))
    assert client.post(f'/api/books/{bid}/reindex').status_code==200
    assert before==many('SELECT id FROM chunks WHERE book_id=?',(bid,))
    assert one('SELECT count(*) AS n FROM chunks_fts')['n']==len(before)
    r=client.post(f'/api/books/{bid}/highlights',json={'page':1,'text':'Conditional probability'})
    assert r.status_code==200
    assert len(client.get(f'/api/books/{bid}/highlights').json())==1
    assert client.delete('/api/highlights/'+r.json()['id']).status_code==200
    assert client.get(f'/api/books/{bid}/highlights').json()==[]

def test_numeric_and_uncertain_grading():
    quiz={'kind':'numeric','answer':'0.25','explanation':'1 / 4 = 0.25','tolerance':.001}
    assert grade(quiz,'0.2505')['correct']
    assert not grade(quiz,'not a number')['correct']
    assert not grade(quiz,'nan')['correct']
    quiz={'kind':'short','answer':'Bayes theorem','accepted':["Bayes' theorem",'베이즈 정리'],'explanation':'test'}
    assert grade(quiz,'베이즈 정리')['correct']
    assert grade(quiz,'다른 표현')['uncertain']

def test_missing_key_and_api_opt_in(client,book,monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings,'ai_mode','live')
    run=client.post('/api/chat',json={'book_id':book['id'],'page':1,'message':'probability'}).json()
    assert run['status']=='error' and run['usage']['api_calls']==0
    assert '비활성화' in run['text']

def test_upload_limit(client,monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings,'max_upload_mb',0)
    assert client.post('/api/books',files={'file':('large.pdf',b'%PDF-')}).status_code==413

def test_here_explain_uses_actual_current_page(client,book):
    run=client.post('/api/chat',json={'book_id':book['id'],'page':2,'message':'여기 설명 ㄱㄱ'}).json()
    assert run['status']=='awaiting_answer',run
    event=next(e for e in run['events'] if e['tool']=='get_current_page')
    assert event['output'] and all(s['page']==2 for s in event['output'])
    assert 'Gradient descent' in run['text']

def test_wrong_answer_triggers_review_and_prerequisites(client,book):
    request={'book_id':book['id'],'page':1,'message':'probability'}
    run=client.post('/api/chat',json=request).json()
    result=client.post('/api/chat',json={**request,'session_id':run['session_id'],'quiz_id':run['quiz']['id'],'answer':'incorrect option'}).json()
    assert not result['evaluation']['correct']
    assert not result['evaluation']['uncertain']
    assert 'find_prerequisites' in [e['tool'] for e in result['events']]
    assert client.get('/api/dashboard').json()['mastery'][0]['status']=='복습 필요'
    assert result['events'][-1]['output']['action']=='review'

def test_overlapping_pdf_blocks_have_unique_chunk_ids(client,monkeypatch):
    original=pymupdf.Page.get_text
    def overlapping(page,*args,**kwargs):
        result=original(page,*args,**kwargs)
        if args and args[0]=='blocks' and result:
            return [result[0],result[0],*result[1:]]
        return result
    monkeypatch.setattr(pymupdf.Page,'get_text',overlapping)
    r=client.post('/api/books',files={'file':('overlap.pdf',pdf_bytes())})
    assert r.status_code==201
    assert client.get('/api/books').json()[0]['status']=='ready'
    assert len(many('SELECT * FROM chunks'))==4
