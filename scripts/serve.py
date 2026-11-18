"""Single-project local launcher. Never kills a port owner without verifying identity."""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT
from backend.runtime import PROJECT_ID

def inspect_server(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=3) as response:
            return json.load(response)
    except Exception:
        return None

def owner(port):
    import psutil
    for connection in psutil.net_connections(kind='tcp'):
        if connection.status=='LISTEN' and connection.laddr.port==port:
            return connection.pid

def verified_process(pid):
    import psutil
    try:
        process=psutil.Process(pid)
        command=process.cmdline()
        expected=(ROOT/'.venv'/'Scripts'/'python.exe').resolve()
        # Windows venv uses a redirector: process.exe() can be the base Python
        # while argv[0] is the checkout's venv executable. Verify both plus cwd.
        executables={expected,Path(getattr(sys,'_base_executable',sys.executable)).resolve()}
        return process if (Path(process.exe()).resolve() in executables and command and
            Path(command[0]).resolve()==expected and
            Path(process.cwd()).resolve()==ROOT.resolve() and
            ('backend.main:app' in command or any(Path(arg).name=='serve.py' for arg in command))) else None
    except (psutil.Error,OSError):
        return None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--restart-owned',action='store_true')
    args=parser.parse_args()
    pid=owner(args.port)
    if pid:
        health=inspect_server(args.port)
        same=health and health.get('project_id')==PROJECT_ID
        process=verified_process(pid)
        if not args.restart_owned:
            if same and not health.get('restart_required') and not health.get('frontend',{}).get('rebuild_required'):
                print(f'ScholarPilot already running: http://127.0.0.1:{args.port} (PID {pid}, revision {health.get("running_revision")})')
                return
            print(f'Port {args.port} is in use (PID {pid}). No process was stopped.')
            if process:
                print('Verified this project. To load current code: .\\scripts\\start.ps1 -RestartOwned')
            else:
                print('Owner could not be verified as this project. Select another port: -Port 8001')
            raise SystemExit(1)
        if not process:
            raise SystemExit('Refusing restart: port owner is not a verified ScholarPilot process in this checkout.')
        process.terminate()
        process.wait(timeout=15)
        for _ in range(30):
            if not owner(args.port):break
            time.sleep(.1)
    frontend=ROOT/'frontend'
    if not (frontend/'dist'/'index.html').exists() or not (frontend/'dist'/'build-info.json').exists():
        needs_build=True
    else:
        from backend.runtime import frontend_revision
        needs_build=json.loads((frontend/'dist'/'build-info.json').read_text())['revision']!=frontend_revision()
    if needs_build:
        print('Building current frontend source...',flush=True)
        subprocess.run(['npm.cmd' if sys.platform=='win32' else 'npm','run','build'],cwd=frontend,check=True)
    print(f'ScholarPilot: http://127.0.0.1:{args.port} (Ctrl+C to stop)',flush=True)
    import uvicorn
    try:
        uvicorn.run('backend.main:app',host='127.0.0.1',port=args.port)
    except OSError as exc:
        if getattr(exc,'winerror',None)==10014:
            print('Windows socket initialization failed (10014). Launcher may retry; no other process was stopped.',file=sys.stderr)
            raise SystemExit(74)
        raise

if __name__=='__main__':main()
