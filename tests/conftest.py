import pytest
import pymupdf
import time
import warnings
from contextlib import contextmanager
from fastapi.testclient import TestClient
from backend.config import settings
from backend.main import app
from backend.database import init_db


@contextmanager
def restart_test_client(application):
    """Retry only known Windows loop startup, never requests/assertions."""
    instance=TestClient(application)
    for attempt in range(3):
        try:
            instance.__enter__()
            break
        except OSError as exc:
            if getattr(exc,'winerror',None)!=10014 or attempt==2:raise
            warnings.warn('Windows socketpair restart failed (10014); retrying startup only.')
            time.sleep(.25)
    try:yield instance
    finally:instance.__exit__(None,None,None)

@pytest.fixture(scope='session')
def http_client(tmp_path_factory):
    # Reuse one Windows event loop; each test still receives its own SQLite DB.
    # Repeated Proactor socketpair creation intermittently fails with WinError 10014.
    old_dir=settings.data_dir
    settings.data_dir=str(tmp_path_factory.mktemp('http-session'))
    try:
        client=TestClient(app)
        for attempt in range(3):
            try:
                client.__enter__()
                break
            except OSError as exc:
                if getattr(exc,'winerror',None)!=10014 or attempt==2:raise
                warnings.warn('Windows socketpair initialisation failed (10014); retrying once, without retrying test assertions.')
                time.sleep(.25)
        try:yield client
        finally:client.__exit__(None,None,None)
    finally:
        settings.data_dir=old_dir

@pytest.fixture
def client(tmp_path,monkeypatch,http_client):
    monkeypatch.setattr(settings,'data_dir',str(tmp_path))
    monkeypatch.setattr(settings,'ai_mode','mock')
    monkeypatch.setattr(settings,'ai_provider','openai')
    monkeypatch.setattr(settings,'allow_external_ai',False)
    init_db()
    yield http_client

def pdf_bytes(title='Test Probability',text='Conditional probability requires joint probability. Bayes theorem updates probability using evidence.',blank=False,toc=True):
    doc=pymupdf.open()
    p=doc.new_page()
    if not blank:p.insert_text((50,50),text,fontsize=11)
    doc.new_page().insert_text((50,50),'Gradient descent uses derivatives for optimization. Quantization reduces precision.')
    doc.set_metadata({'title':title,'author':'ScholarPilot tests'})
    if toc:doc.set_toc([[1,'Probability',1],[1,'Optimization',2]])
    data=doc.tobytes()
    doc.close()
    return data

@pytest.fixture
def book(client):
    r=client.post('/api/books',files={'file':('test.pdf',pdf_bytes(),'application/pdf')})
    assert r.status_code==201,r.text
    return client.get('/api/books').json()[0]
