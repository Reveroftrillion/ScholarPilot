"""Read saved real-local evidence; never invoke any model or change user data."""
import argparse,json,sqlite3,statistics
from pathlib import Path
import pymupdf


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];directory=a.directory.resolve()
    if not directory.is_relative_to(root/'data/local-evaluation-runs') or not (directory/'.local-evaluation').is_file():raise SystemExit('Expected a marked isolated QA directory')
    records=json.loads((directory/'local-model-calls.json').read_text(encoding='utf-8'))
    result={'model_names':sorted({r['model'] for r in records}),'local_generation_requests':len(records),'paid_requests':0,
      'input_tokens':sum(r.get('metrics',{}).get('prompt_tokens',0) for r in records),
      'output_tokens':sum(r.get('metrics',{}).get('generated_tokens',0) for r in records),
      'failed_generations':sum(r['status']!='completed' for r in records),
      'minimum_sampled_available_ram_bytes':min(r[k]['available_bytes'] for r in records for k in ('memory_before','memory_after')),
      'maximum_sampled_ollama_rss_bytes':max(sum(v['rss_bytes'] for v in r[k]['processes']) for r in records for k in ('memory_before','memory_after')),
      'maximum_model_allocation_bytes':max(m['size'] for r in records for m in (r.get('loaded_models') or [])),
      'maximum_vram_bytes':max(m['size_vram'] for r in records for m in (r.get('loaded_models') or [])),
      'memory_note':'Request before/after samples, not execution peaks. Other apps and QA processes affect available RAM.',
      'stages':{},'citation_count':0,'citations_verified':0,
      'quality_note':'Execution status and mathematical arithmetic are not model semantic-quality scores. A/C prose failed human review; B confirms calculation practice, not conceptual understanding.'}
    with sqlite3.connect((directory/'scholarpilot.db').as_uri()+'?mode=ro',uri=True) as db:
        for name,file in [('A','scenario-A.json'),('B','scenario-B.json'),('grade','scenario-grade.json'),('C','scenario-C.json'),('browser_selection','browser-selection.json')]:
            path=directory/file
            if not path.exists():continue
            saved=json.loads(path.read_text(encoding='utf-8'));run=saved.get('run') or saved['response']
            result['stages'][name]={k:run[k] for k in ('status','elapsed','usage')}
            for source in run['sources']:
                result['citation_count']+=1
                chunk=db.execute('SELECT book_id,page,text FROM chunks WHERE id=?',(source['id'],)).fetchone()
                if not chunk or tuple(chunk)!=(source['book_id'],source['page'],source['text']):continue
                with pymupdf.open(directory/'pdfs'/f"{source['book_id']}.pdf") as doc:
                    if any(source['text'] in block[4].strip() for block in doc[source['page']-1].get_text('blocks',sort=True)):result['citations_verified']+=1
    for name in ('before','after'):
        path=root/f'data/reliable-evaluation/fts-{name}.json'
        if path.exists():
            search=json.loads(path.read_text(encoding='utf-8'))
            result['search_'+name]={k:search[k] for k in ('cases','anchors_verified','page_hits_at_8','source_count','source_verified','scope_valid')}
            result['search_'+name]['median_ms']=statistics.median(r['elapsed_ms'] for r in search['results'])
    (directory/'reliability-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
