"""Read-only inventory of known test data. Never deletes or changes files."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]/'data'
purposes={'benchmarks':'indexing and concurrent-search benchmarks',
          'evaluation-runs':'synthetic RAG/agent evaluation databases',
          'browser-qa-runs':'isolated PDF copies and browser QA databases',
          'bayes-evaluation-runs':'isolated Bishop PDF, model-call traces and human evaluation records',
          'local-evaluation-runs':'actual local Ollama learning validation; copied PDFs and model traces',
          'models':'downloaded local model weights, retained for offline inference',
          'tools':'official Ollama archive and extracted CPU runtime'}
result=[]
for name,purpose in purposes.items():
    folder=root/name
    files=[p for p in folder.rglob('*') if p.is_file() and not p.is_symlink()] if folder.exists() else []
    result.append({'directory':str(folder),'purpose':purpose,'files':len(files),
                   'bytes':sum(p.stat().st_size for p in files),
                   'runs':sum(1 for p in folder.iterdir() if p.is_dir()) if folder.exists() else 0})
print(json.dumps({'mode':'dry-run: inventory only; no deletion', 'directories':result},indent=2))
