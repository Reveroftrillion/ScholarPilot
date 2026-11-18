"""Benchmark actual PDF ingestion on a NEW isolated workspace. Never edits user DB."""
import json
import shutil
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.database import db,init_db,many,one
from backend.ingestion import register_pdf,index_book
from backend.retrieval import search
from tests.conftest import pdf_bytes

def measure(fn):
    start=time.perf_counter();result=fn();return result,round(time.perf_counter()-start,3)

def main():
    source_root=Path(settings.data_dir).resolve()
    source_books=many("SELECT id,title,pages,status,last_page FROM books ORDER BY id")
    if len(source_books)<2 or any(b['status']!='ready' for b in source_books):
        raise SystemExit('두 권의 ready 교과서가 필요합니다.')
    available=shutil.disk_usage(ROOT).free
    if available<350*1024*1024:raise SystemExit('격리 성능 테스트에 필요한 여유 공간 350MB가 부족합니다.')
    run_id=uuid.uuid4().hex
    target=ROOT/'data'/'benchmarks'/run_id
    settings.data_dir=str(target)
    init_db();results=[];ids=[]
    for b in source_books:
        content=(source_root/'pdfs'/f"{b['id']}.pdf").read_bytes()
        bid,upload=measure(lambda:register_pdf(content,b['title']+'.pdf'))
        _,index=measure(lambda:index_book(bid))
        status=one('SELECT status,progress,pages FROM books WHERE id=?',(bid,))
        results.append({'title':b['title'],'pages':status['pages'],'status':status['status'],
                        'upload_seconds':upload,'index_seconds':index})
        ids.append(bid)
    counts_before={bid:one('SELECT count(*) AS n FROM chunks WHERE book_id=?',(bid,))['n'] for bid in ids}
    extra=register_pdf(pdf_bytes('Benchmark independent fixture'),'fixture.pdf')
    _,extra_index=measure(lambda:index_book(extra))
    counts_after_add={bid:one('SELECT count(*) AS n FROM chunks WHERE book_id=?',(bid,))['n'] for bid in ids}
    _,reindex=measure(lambda:index_book(ids[0]))
    counts_after_reindex={bid:one('SELECT count(*) AS n FROM chunks WHERE book_id=?',(bid,))['n'] for bid in ids}
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        hits=list(pool.map(lambda _:len(search('gradient descent',ids)),range(32)))
    concurrent_seconds=round(time.perf_counter()-start,3)
    with db() as c:
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys=[tuple(row) for row in c.execute('PRAGMA foreign_key_check').fetchall()]
        chunks=c.execute('SELECT count(*) FROM chunks').fetchone()[0]
        indexed=c.execute('SELECT count(*) FROM chunks_fts').fetchone()[0]
    settings.data_dir=str(source_root)
    unchanged=many('SELECT id,title,pages,status,last_page FROM books ORDER BY id')==source_books
    report={'isolated_data_dir':str(target.relative_to(ROOT)),'books':results,'fixture_index_seconds':extra_index,
            'first_book_reindex_seconds':reindex,'original_book_chunk_counts_stable_after_add':counts_before==counts_after_add,
            'original_book_chunk_counts_stable_after_reindex':counts_before==counts_after_reindex,
            'concurrent_queries':len(hits),'concurrent_queries_with_results':sum(bool(h) for h in hits),
            'concurrent_seconds':concurrent_seconds,'sqlite_integrity':integrity,'foreign_key_errors':len(foreign_keys),
            'chunks':chunks,'fts_rows':indexed,'user_book_metadata_unchanged':unchanged}
    (ROOT/'docs'/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    if not all(b['status']=='ready' for b in results) or integrity!='ok' or foreign_keys or chunks!=indexed or not unchanged:
        raise SystemExit('격리 성능 검사 실패: 보고서를 확인하세요.')

if __name__=='__main__':main()
