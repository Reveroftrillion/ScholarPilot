from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from backend.database import db,many,one,data_path
from backend.ingestion import index_book,register_pdf
from .conftest import pdf_bytes

def test_reindex_failure_rolls_back_original_fts_and_restores_trigger(client,book):
    bid=book['id']
    before=many('SELECT id,text FROM chunks WHERE book_id=? ORDER BY id',(bid,))
    with db() as c:
        c.execute("CREATE TRIGGER test_injected_failure BEFORE INSERT ON chunks BEGIN SELECT RAISE(ABORT,'injected'); END")
    index_book(bid)
    assert one('SELECT status FROM books WHERE id=?',(bid,))['status']=='error'
    assert many('SELECT id,text FROM chunks WHERE book_id=? ORDER BY id',(bid,))==before
    assert one('SELECT count(*) AS n FROM chunks_fts WHERE book_id=?',(bid,))['n']==len(before)
    assert one("SELECT name FROM sqlite_master WHERE type='trigger' AND name='chunk_delete'")

def test_duplicate_upload_race_leaves_only_one_file(client):
    content=pdf_bytes('Concurrent unique upload')
    def register(_):
        try:return register_pdf(content,'test.pdf')
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes=list(pool.map(register,range(6)))
    assert len([x for x in outcomes if isinstance(x,str)])==1
    assert len([x for x in outcomes if x==409])==5
    assert len(list((data_path()/'pdfs').glob('*.pdf')))==1

def test_untrusted_filename_cannot_choose_storage_path(client):
    bid=register_pdf(pdf_bytes('Path traversal fixture'),r'..\..\outside.pdf')
    assert one('SELECT filename FROM books WHERE id=?',(bid,))['filename']=='outside.pdf'
    assert (data_path()/'pdfs'/f'{bid}.pdf').exists()
