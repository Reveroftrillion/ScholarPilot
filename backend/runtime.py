"""Content revisions identify stale code without exposing configuration secrets."""
import hashlib
import json
import os
from datetime import datetime, timezone
from .config import ROOT

PROJECT_ID = hashlib.sha256(str(ROOT.resolve()).casefold().encode()).hexdigest()[:20]

def revision(paths):
    digest = hashlib.sha256()
    for path in sorted(paths,key=lambda path:path.relative_to(ROOT).as_posix()):
        digest.update(str(path.relative_to(ROOT)).replace('\\','/').encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]

def backend_revision():
    return revision((ROOT/'backend').glob('*.py'))

def frontend_revision():
    return revision(p for p in (ROOT/'frontend'/'src').rglob('*') if p.is_file())

START_REVISION = backend_revision()
STARTED_AT = datetime.now(timezone.utc).isoformat()

def runtime_status():
    current = backend_revision()
    build_path = ROOT/'frontend'/'dist'/'build-info.json'
    try:
        build = json.loads(build_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        build = {}
    return {'app':'ScholarPilot','project_id':PROJECT_ID,'pid':os.getpid(),
            'started_at':STARTED_AT,'running_revision':START_REVISION,
            'disk_revision':current,'restart_required':START_REVISION!=current,
            'frontend':{'built':(ROOT/'frontend'/'dist'/'index.html').exists(),
                        'build_revision':build.get('revision'),
                        'source_revision':frontend_revision(),
                        'rebuild_required':build.get('revision')!=frontend_revision()}}
