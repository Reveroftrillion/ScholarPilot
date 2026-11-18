"""Regression: old indexes must not remove short formula denominators from AI context."""
import json
from types import SimpleNamespace

import pymupdf

from backend.agent import Agent, ChatRequest
from backend.database import db, many


def equation_book(client):
    with pymupdf.open() as document:
        page=document.new_page()
        page.insert_text((50,50),'Bayes theorem follows from the product rule of probability.')
        page.insert_text((50,90),'p(A|B)=p(B|A)p(A)')
        page.insert_text((100,130),'p(B)')
        document.new_page().insert_text((50,50),'SECOND_PAGE_ONLY: unrelated gradient descent discussion.')
        content=document.tobytes()
    response=client.post('/api/books',files={'file':('equations.pdf',content,'application/pdf')})
    assert response.status_code==201,response.text
    return client.get('/api/books').json()[0]


class CaptureProvider:
    def __init__(self):self.messages=None

    def respond(self,messages,tools):
        self.messages=messages
        return SimpleNamespace(output=[],output_text='원본 수식과 대조합니다.',usage=None)


def test_short_denominator_reaches_model_without_reindexing(client):
    book=equation_book(client)
    # Simulate the historical short-block filter only in this test's isolated DB.
    # DELETE uses the normal FTS trigger; no user's library is reindexed.
    with db() as connection:
        connection.execute('DELETE FROM chunks WHERE book_id=? AND page=1 AND length(text)<15',(book['id'],))
    indexed=many('SELECT * FROM chunks WHERE book_id=? AND page=1',(book['id'],))
    assert indexed
    assert all(row['text'].strip()!='p(B)' for row in indexed)
    provider=CaptureProvider()
    result=Agent(ChatRequest(book_id=book['id'],page=1,message='이 페이지 수식을 설명해 줘.'),provider).run()
    assert result['status']=='completed'
    supplement=next(message['content'] for message in provider.messages if message.get('content','').startswith('Current PDF page full-text supplement'))
    reference=json.loads(supplement.split(': ',1)[1])
    assert '\np(B)' in reference['text']
    assert 'SECOND_PAGE_ONLY' not in reference['text']
    assert reference['book_id']==book['id'] and reference['page']==1
    assert set(reference['source_ids'])=={row['id'] for row in indexed}
    assert reference['warning'] and not reference['truncated']
    assert many('SELECT * FROM chunks WHERE book_id=? AND page=1',(book['id'],))==indexed


def test_new_upload_indexes_short_formula_denominator(client):
    book=equation_book(client)
    denominators=many('SELECT * FROM chunks WHERE book_id=? AND page=1 AND text=?',(book['id'],'p(B)'))
    assert len(denominators)==1
    indexed=many('SELECT chunk_id FROM chunks_fts WHERE chunk_id=?',(denominators[0]['id'],))
    assert indexed==[{'chunk_id':denominators[0]['id']}]


def test_full_page_reference_uses_requested_page_not_previous_page(client):
    book=equation_book(client)
    agent=Agent(ChatRequest(book_id=book['id'],page=2,message='여기 설명해 줘.'))
    context=agent.execute('get_current_page',{})
    reference=agent.full_page_reference(context)
    assert reference['page']==2
    assert 'SECOND_PAGE_ONLY' in reference['text']
    assert 'p(A|B)' not in reference['text']
