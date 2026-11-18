"""Use only our own temporary listener to test foreign-port protection."""
import json
import socket
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
    listener.bind(('127.0.0.1',0));listener.listen(2)
    port=listener.getsockname()[1]
    outcomes=[]
    for extra in ([],['--restart-owned']):
        p=subprocess.run([str(root/'.venv'/'Scripts'/'python.exe'),str(root/'scripts'/'serve.py'),'--port',str(port),*extra],cwd=root,capture_output=True,text=True,timeout=15)
        alive=listener.fileno()!=-1
        outcomes.append({'restart_owned':bool(extra),'exit_code':p.returncode,'listener_alive':alive,
                         'rejected':p.returncode!=0})
    result={'port_conflict':outcomes,'foreign_listener_not_stopped':all(o['listener_alive'] and o['rejected'] for o in outcomes)}
    (root/'docs'/'port-conflict.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    if not result['foreign_listener_not_stopped']:raise SystemExit(1)
