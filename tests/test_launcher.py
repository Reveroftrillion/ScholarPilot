from pathlib import Path
from types import SimpleNamespace as NS
import sys
import pytest
import psutil
from scripts import serve
from backend.config import ROOT
from backend.runtime import PROJECT_ID

def test_duplicate_server_is_reused_without_starting_uvicorn(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['serve.py'])
    monkeypatch.setattr(serve,'owner',lambda port:123)
    monkeypatch.setattr(serve,'inspect_server',lambda port:{'project_id':PROJECT_ID,'restart_required':False,'frontend':{'rebuild_required':False},'running_revision':'same'})
    monkeypatch.setattr(serve,'verified_process',lambda pid:None)
    serve.main()
    assert 'already running' in capsys.readouterr().out

def test_foreign_port_owner_is_never_terminated(monkeypatch):
    monkeypatch.setattr(sys,'argv',['serve.py','--restart-owned'])
    monkeypatch.setattr(serve,'owner',lambda port:123)
    monkeypatch.setattr(serve,'inspect_server',lambda port:{'project_id':'foreign'})
    monkeypatch.setattr(serve,'verified_process',lambda pid:None)
    with pytest.raises(SystemExit,match='Refusing restart'):serve.main()

def test_windows_venv_redirector_and_checkout_are_both_verified(monkeypatch):
    process=NS(exe=lambda:str(Path(sys._base_executable)),cwd=lambda:str(ROOT),
               cmdline=lambda:[str(ROOT/'.venv'/'Scripts'/'python.exe'),'-m','uvicorn','backend.main:app'])
    monkeypatch.setattr(psutil,'Process',lambda pid:process)
    assert serve.verified_process(123) is process
    process.cwd=lambda:str(ROOT.parent)
    assert serve.verified_process(123) is None

def test_stale_revision_requires_explicit_owned_restart(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['serve.py'])
    monkeypatch.setattr(serve,'owner',lambda port:123)
    monkeypatch.setattr(serve,'inspect_server',lambda port:{'project_id':PROJECT_ID,'restart_required':True})
    monkeypatch.setattr(serve,'verified_process',lambda pid:NS())
    with pytest.raises(SystemExit):serve.main()
    assert '-RestartOwned' in capsys.readouterr().out

def test_windows_socket_initialization_has_specific_retry_exit(monkeypatch):
    import uvicorn
    monkeypatch.setattr(sys,'argv',['serve.py'])
    monkeypatch.setattr(serve,'owner',lambda port:None)
    monkeypatch.setattr(serve.subprocess,'run',lambda *args,**kwargs:None)
    error=OSError('Windows initialization failed');error.winerror=10014
    def fail(*args,**kwargs):raise error
    monkeypatch.setattr(uvicorn,'run',fail)
    with pytest.raises(SystemExit) as exc:serve.main()
    assert exc.value.code==74
