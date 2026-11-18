"""Read-only, real-PDF retrieval benchmark. No model or paid calls."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
from backend.database import data_path, many
from backend.retrieval import search

ROOT = Path(__file__).resolve().parents[1]
def main():
    cases = json.loads((ROOT/'docs/learning-cases.json').read_text(encoding='utf-8'))
    books = many('SELECT id,title FROM books WHERE status=?', ('ready',))
    ids = {key: next(b['id'] for b in books if needle in b['title']) for key,needle in [('bishop','Deep Learning_ Foundations'),('systems','Machine Learning Systems')]}
    docs = {k: pymupdf.open(data_path()/'pdfs'/f'{v}.pdf') for k,v in ids.items()}
    results=[]
    try:
        for case in cases:
            page = docs[case['book']][case['pdf_page']-1]
            text = ' '.join(page.get_text().casefold().split())
            anchor_ok = all(a.casefold() in text for a in case['evidence_anchors'])
            start=time.perf_counter()
            rows=search(case['question'],[ids[case['book']]],limit=8)
            results.append({'id':case['id'], 'anchor_verified':anchor_ok,
                'expected_page_at_8':any(r['page']==case['pdf_page'] and r['book_id']==ids[case['book']] for r in rows),
                'scope_valid':all(r['book_id']==ids[case['book']] for r in rows),
                'elapsed_ms':round((time.perf_counter()-start)*1000,2),
                'results':[{'book_id':r['book_id'],'pdf_page':r['page'],'printed_page':r['printed_page'],'chunk_id':r['id'],
                    'source_verified':any(r['text'] in block[4].strip() for block in docs[case['book']][r['page']-1].get_text('blocks',sort=True))} for r in rows]})
    finally:
        for doc in docs.values():doc.close()
    report={'method':'Manually specified PDF page, anchor checked in local PDF; exact page recall@8 is a strict proxy, not a human relevance judgment or answer-quality score.',
      'cases':len(cases),'anchors_verified':sum(r['anchor_verified'] for r in results),'page_hits_at_8':sum(r['expected_page_at_8'] for r in results),
      'scope_valid':all(r['scope_valid'] for r in results),'source_verified':sum(s['source_verified'] for r in results for s in r['results']),
      'source_count':sum(len(r['results']) for r in results),'results':results}
    (ROOT/'docs/learning-retrieval-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    if not all(r['anchor_verified'] and r['scope_valid'] and all(s['source_verified'] for s in r['results']) for r in results):sys.exit(1)
if __name__=='__main__':main()
