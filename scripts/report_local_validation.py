"""Summarize saved genuine local runs without inference or user-data changes."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.quality import assess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',required=True,type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    directory=args.directory.resolve()
    if not directory.is_relative_to((root/'data/local-evaluation-runs').resolve()) or not (directory/'.local-evaluation').is_file():
        raise SystemExit('Expected a marked isolated local evaluation directory')
    calls=json.loads((directory/'local-model-calls.json').read_text(encoding='utf-8'))
    scenarios=[]
    def verify(source):
        with sqlite3.connect((directory/'scholarpilot.db').as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT book_id,page,text FROM chunks WHERE id=?',(source['id'],)).fetchone()
        if not row or (row[0],row[1],row[2])!=(source['book_id'],source['page'],source['text']):return False
        path=directory/'pdfs'/f"{row[0]}.pdf"
        if not path.is_file():return False
        with pymupdf.open(path) as doc:
            return 1<=row[1]<=len(doc) and any(row[2] in block[4].strip() for block in doc[row[1]-1].get_text('blocks',sort=True))
    for name in ('A','B','grade','C','D','selection'):
        path=directory/f'scenario-{name}.json'
        if not path.exists():continue
        saved=json.loads(path.read_text(encoding='utf-8'));req=saved['request'];run=saved['run']
        scenarios.append({'scenario':name,'status':run['status'],'provider':run.get('provider'),'elapsed_seconds':run['elapsed'],
                          'usage':run['usage'],'selection_characters':len(req.get('selection','')),
                          'tools':[{'tool':e['tool'],'actor':e.get('actor','unknown'),'status':e['status']} for e in run['events']],
                          'sources':[{'book_id':s['book_id'],'pdf_page':s['page'],'id':s['id']} for s in run['sources']],
                          'citation_count':len(run['sources']),'citations_verified':sum(verify(s) for s in run['sources']),
                          'quiz_saved':bool(run.get('quiz')),'grading_uncertain':(run.get('evaluation') or {}).get('uncertain'),
                          'independent_limited_checks':assess(run['text'],req['message'],[s['id'] for s in run['sources']])})
    metrics=[c.get('metrics',{}) for c in calls]
    samples=[c[k] for c in calls for k in ('memory_before','memory_after') if k in c]
    models=[m for c in calls for m in (c.get('loaded_models') or [])]
    report={'method':'Recorded real Ollama runs. Automated checks are limited; human source entailment and derivation review are still required. Memory values are samples, not process peaks.',
            'model_names':sorted({c['model'] for c in calls}),'actual_local_generation_requests':len(calls),
            'external_paid_requests':0,'input_tokens':sum(m.get('prompt_tokens',0) for m in metrics),
            'output_tokens':sum(m.get('generated_tokens',0) for m in metrics),
            'recorded_generation_call_seconds':round(sum(c.get('elapsed',0) for c in calls),3),
            'unfinished_calls':sum(c['status']=='started' for c in calls),
            'first_recorded_load_seconds':metrics[0].get('load_seconds') if metrics else None,
            'maximum_sampled_model_allocation_bytes':max((m.get('size',0) for m in models),default=None),
            'maximum_sampled_vram_bytes':max((m.get('size_vram',0) for m in models),default=None),
            'minimum_sampled_available_ram_bytes':min((s['available_bytes'] for s in samples),default=None),
            'maximum_sampled_ollama_rss_bytes':max((sum(p['rss_bytes'] for p in s['processes']) for s in samples),default=None),
            'scenarios':scenarios,'missing_scenarios':[n for n in ('A','B','grade','C','D') if not (directory/f'scenario-{n}.json').exists()]}
    (directory/'local-validation-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='scenarios'},ensure_ascii=True))
    for row in scenarios:print(json.dumps({k:row[k] for k in ('scenario','status','elapsed_seconds','usage','grading_uncertain')},ensure_ascii=True))


if __name__=='__main__':main()
