"""Local, reproducible lexical proxy evaluation against user's registered PDFs.

This reads the existing books and database; it does not reindex or modify them.
No copyrighted passages are written to the report. The manually chosen terms
are weak relevance proxies, not independent human relevance judgments.
"""
import argparse
import json
import re
import statistics
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymupdf
from backend.config import ROOT
from backend.database import data_path, many
from backend.retrieval import search

CASES = [
    ('Bayes theorem',"Bayes' theorem",[['bayes','bayesian']]),
    ('conditional probability ko','조건부확률이란?', [['conditional probability','conditional probabilities','conditional distribution']]),
    ('gradient descent ko','경사하강법 설명',[['gradient descent','gradient-descent']]),
    ('gradient descent en','Gradient Descent',[['gradient descent','gradient-descent']]),
    ('backpropagation','What is backpropagation?',[['backpropagation','back-propagation','back propagation']]),
    ('quantization','Quantization',[['quantization','quantisation']]),
    ('ptq vs qat','PTQ와 QAT의 차이',[['post-training quantization','post training quantization','ptq'],['quantization-aware training','quantization aware training','qat']]),
    ('attention','Attention mechanism',[['attention']]),
    ('transformer','Transformer',[['transformer']]),
    ('linear regression','Linear Regression',[['linear regression']]),
    ('memory bottleneck','Memory bottleneck',[['memory'],['bottleneck']]),
    ('model optimization','Model optimization',[['model'],['optimization','optimisation','optimize','optimise']]),
]

def contains_group(s,group):
    text=(s['text']+' '+(s.get('section') or '')).casefold()
    return any(re.search(r'(?<!\w)'+re.escape(term.casefold())+r'(?!\w)',text) for term in group)

def duplicate_count(rows):
    seen=[];count=0
    for r in rows:
        text=' '.join(r['text'].casefold().split())
        if any(book==r['book_id'] and page==r['page'] and SequenceMatcher(None,text,other,autojunk=False).ratio()>=.85 for book,page,other in seen):count+=1
        seen.append((r['book_id'],r['page'],text))
    return count

def evaluate():
    books=many("SELECT id,title,pages FROM books WHERE status='ready' ORDER BY id")
    if len(books)<2:raise RuntimeError('두 권 이상의 인덱싱된 교과서가 필요합니다.')
    docs={b['id']:pymupdf.open(data_path()/'pdfs'/f"{b['id']}.pdf") for b in books}
    results=[]
    try:
        for label,query,groups in CASES:
            start=time.perf_counter();rows=search(query,None,limit=8);elapsed=(time.perf_counter()-start)*1000
            per_book={}
            for b in books:
                scoped=search(query,[b['id']],limit=8)
                per_book[b['id']]={'scope_valid':all(r['book_id']==b['id'] for r in scoped),'returned':len(scoped)}
            verified=0
            for r in rows:
                page=docs[r['book_id']][r['page']-1]
                if any(r['text'] in block[4].strip() for block in page.get_text('blocks',sort=True)):verified+=1
            relevance=[any(contains_group(r,g) for g in groups) for r in rows]
            coverage=[any(contains_group(r,g) for r in rows) for g in groups]
            results.append({'case':label,'query':query,'expected_term_groups':groups,
                'returned':len(rows),'top1_proxy_relevant':bool(relevance and relevance[0]),
                'relevant_proxy_count':sum(relevance),'term_groups_found':coverage,
                'all_term_groups_found':all(coverage),'verified_source_count':verified,
                'scope_all_valid':all(r['book_id'] in docs for r in rows),
                'duplicate_count':duplicate_count(rows),'elapsed_ms':round(elapsed,2),
                'per_book':per_book,'sources':[{'book_id':r['book_id'],'pdf_page':r['page'],
                    'printed_page':r['printed_page'],'section':r['section'],'chunk_id':r['id'],
                    'proxy_relevant':relevance[i]} for i,r in enumerate(rows)]})
        empty=search('zzzznonexistentconcept0987654321',None)
    finally:
        for doc in docs.values():doc.close()
    total=sum(r['returned'] for r in results)
    return {'method':'Curated lexical proxy, evaluated against real local PDF text. Not human relevance labels or semantic evaluation.',
        'books':books,'case_count':len(results),'metrics':{
        'top1_proxy_hits':sum(r['top1_proxy_relevant'] for r in results),
        'all_groups_found_at_8':sum(r['all_term_groups_found'] for r in results),
        'proxy_relevant_results':sum(r['relevant_proxy_count'] for r in results),
        'returned_results':total,'source_text_verified':sum(r['verified_source_count'] for r in results),
        'duplicate_results':sum(r['duplicate_count'] for r in results),
        'median_ms':round(statistics.median(r['elapsed_ms'] for r in results),2),
        'max_ms':round(max(r['elapsed_ms'] for r in results),2),
        'all_scope_checks_passed':all(r['scope_all_valid'] and all(v['scope_valid'] for v in r['per_book'].values()) for r in results),
        'no_result_correct':not empty},'cases':results}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output).resolve()
    if out.parent!= (ROOT/'docs').resolve():raise SystemExit('결과는 프로젝트 docs 폴더에만 저장할 수 있습니다.')
    report=evaluate();out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['metrics'],ensure_ascii=True))
    for row in report['cases']:
        print(row['case'],row['returned'],row['top1_proxy_relevant'],row['all_term_groups_found'],row['duplicate_count'],row['elapsed_ms'])

if __name__=='__main__':main()
