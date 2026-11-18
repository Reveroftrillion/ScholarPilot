"""Summarize an approved live ledger without issuing any network requests."""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.database import many
from scripts.bayes_evaluation import source_checks

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    folder=a.directory.resolve()
    if not folder.is_relative_to((ROOT/'data/bayes-evaluation-runs').resolve()) or not (folder/'.live-validation').is_file():
        raise SystemExit('Requires marked isolated live evaluation')
    records=json.loads((folder/'model-calls.json').read_text(encoding='utf-8'))
    settings.data_dir=str(folder)
    scenarios={}
    for label,file in [('A','scenario-A.json'),('B-diagnosis','scenario-B-diagnosis.json'),('B-grade','scenario-B-grade.json'),('C','scenario-C.json')]:
        path=folder/file
        if not path.exists():scenarios[label]={'status':'not_executed'};continue
        data=json.loads(path.read_text(encoding='utf-8'));run=data['run']
        scenarios[label]={'status':run['status'],'pdf_page_sent':data['request']['page'],
            'mode':run['mode'],'tool_names':[e['tool'] for e in run['events']],
            'source_checks':source_checks(run),'quiz_created':bool(run['quiz']),
            'evaluation_present':bool(run['evaluation'])}
    audit=[]
    pattern=re.compile(r'\bPTQ\b|post[-\s]training quanti[sz]ation|\bQAT\b|quanti[sz]ation[-\s]aware training',re.I)
    for book in many('SELECT id,title FROM books'):
        chunks=many('SELECT id,page,text FROM chunks WHERE book_id=?',(book['id'],))
        hits=[c for c in chunks if pattern.search(c['text'])]
        audit.append({'book':book['title'],'book_id':book['id'],'matching_pages':sorted({c['page'] for c in hits}),
            'meaning':'Local phrase audit only; not a model response or proof that all other terminology is absent'})
    tokens={k:sum(r['usage'][k] for r in records) if all(r.get('usage',{}).get(k) is not None for r in records) else None for k in ('input_tokens','output_tokens')}
    estimated=sum(r['estimated_usd'] for r in records) if all(r.get('estimated_usd') is not None for r in records) else None
    error_codes=[r.get('error_code') for r in records if r['status']=='error']
    result={'model':records[0]['model_requested'] if records else settings.openai_model,
        'api_requests':len(records),'successful_responses':sum(r['status']=='completed' for r in records),
        'usage':tokens,'estimated_cost_usd':estimated,'reserved_usd':sum(r['reserved_usd'] for r in records),
        'errors':error_codes,'scenarios':scenarios,'two_book_local_source_audit':audit,
        'explanation_quality':None,'generated_math_verified':None,
        'note':'No quality score without a successful model response. Null usage means not reported, not zero.'}
    target=ROOT/'docs/live-validation-results.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('scenarios','two_book_local_source_audit')},ensure_ascii=True,indent=2))

if __name__=='__main__':main()
