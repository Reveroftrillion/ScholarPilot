"""Verify local source locations without exporting textbook excerpts."""
import json
import sys
from pathlib import Path
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.database import many, data_path
from backend.retrieval import search
from backend.config import ROOT

books=many('SELECT id,title,pages,status FROM books')
results=[]
for query in ['Bayes','conditional probability','Quantization','경사하강법']:
    sources=search(query)
    verified=[]
    for source in sources:
        with pymupdf.open(data_path()/'pdfs'/f'{source["book_id"]}.pdf') as doc:
            blocks=doc[source['page']-1].get_text('blocks',sort=True)
            verified.append(any(source['text'] in b[4].strip() for b in blocks))
    results.append({'query':query,'matches':len(sources),'exact_page_text_verified':all(verified) and bool(verified),'pdf_pages':[s['page'] for s in sources]})
report={'books':books,'chunks':many('SELECT book_id,count(*) AS count FROM chunks GROUP BY book_id'),'retrieval':results}
(ROOT/'docs'/'real-book-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'books':len(books),'checks':results},ensure_ascii=True))
