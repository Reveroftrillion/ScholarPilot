"""Single local inference job with observable phases; no queued CPU overload."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid

pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='scholarpilot-local')
lock=threading.Lock();jobs={}


def submit(work):
    with lock:
        if any(j['status']=='running' for j in jobs.values()):raise ValueError('로컬 AI 작업이 실행 중입니다. 현재 작업이 끝난 뒤 요청하세요.')
        for key in list(jobs):
            if time.monotonic()-jobs[key]['created']>3600:del jobs[key]
        jid=uuid.uuid4().hex
        jobs[jid]={'id':jid,'status':'running','phase':'searching','created':time.monotonic()}
    def progress(phase):
        with lock:jobs[jid]['phase']=phase
    def run():
        try:
            result=work(progress)
            with lock:jobs[jid].update(status='done',phase='done',result=result)
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else '학습 작업이 실패했습니다. 서버 상태를 확인하세요.'
            with lock:jobs[jid].update(status='error',phase='error',error=message)
    pool.submit(run)
    return {'id':jid}


def get(jid):
    with lock:
        if jid not in jobs:return None
        return {k:v for k,v in jobs[jid].items() if k!='created'}
