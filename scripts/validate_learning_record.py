"""Validate a manually captured model evaluation record without invoking a model."""
import argparse, json
from pathlib import Path

RUBRIC=['grounding','symbols','derivation','assumptions','example','prerequisites','citations','korean_clarity','uncertainty']
def validate(record):
    required=['case_id','mode','model','request_context','retrieved_sources','agent_tools','response',
              'elapsed_seconds','usage','cost_estimate','evaluation']
    missing=[k for k in required if k not in record]
    if missing: raise ValueError('Missing fields: '+', '.join(missing))
    if record['mode'] not in ('offline_fixture','live'): raise ValueError('Unknown mode')
    if not isinstance(record['retrieved_sources'],list) or not isinstance(record['agent_tools'],list): raise ValueError('Sources and tools must be arrays')
    if not isinstance(record['elapsed_seconds'],(int,float)) or record['elapsed_seconds']<0: raise ValueError('Invalid elapsed time')
    if not all(k in record['usage'] for k in ('input_tokens','output_tokens')): raise ValueError('Token fields required; use null when unavailable')
    if not all(k in record['cost_estimate'] for k in ('amount','currency','input_rate_per_million','output_rate_per_million','pricing_date')): raise ValueError('Cost assumptions required; use null when unknown')
    scores=record['evaluation'].get('scores',{})
    if set(scores)!=set(RUBRIC) or any(v not in (None,0,1,2) for v in scores.values()): raise ValueError('All nine scores must be null or 0, 1, 2')
    if any(v is not None for v in scores.values()) and not record['evaluation'].get('reviewer'): raise ValueError('Scored records require an identified reviewer')
    return True
def main():
    p=argparse.ArgumentParser();p.add_argument('record',type=Path);a=p.parse_args()
    validate(json.loads(a.record.read_text(encoding='utf-8')));print('Valid record structure; scores and factual accuracy are not verified.')
if __name__=='__main__':main()
