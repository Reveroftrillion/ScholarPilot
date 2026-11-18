import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import settings, ROOT
from .database import db, init_db, one, many, data_path
from .ingestion import register_pdf, index_book
from .retrieval import search
from .agent import Agent, ChatRequest
from .runtime import runtime_status
from .providers import readiness, OpenAIProvider, AIRequestError
from .ollama_provider import OllamaProvider

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title='ScholarPilot', lifespan=lifespan)

@app.middleware('http')
async def local_only(request: Request, call_next):
    # Local application: prevent cross-site mutation / DNS rebinding.
    host = request.url.hostname
    if host not in ('localhost','127.0.0.1','testserver'):
        return JSONResponse({'detail':'로컬 접속만 허용합니다.'},status_code=403)
    origin = request.headers.get('origin')
    if origin and origin not in (str(request.base_url).rstrip('/'),'http://localhost:5173','http://127.0.0.1:5173'):
        return JSONResponse({'detail':'허용되지 않은 요청 출처입니다.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def book_or_404(book_id):
    book = one('SELECT * FROM books WHERE id=?', (book_id,))
    if not book: raise HTTPException(404,'교과서를 찾을 수 없습니다.')
    return book

@app.get('/api/health')
def health():
    state=runtime_status()
    try:
        one('SELECT 1 AS ok')
        database='ok'
    except Exception:
        database='error'
    return {'status':'ok' if database=='ok' else 'degraded','database':database,**state}

@app.get('/api/books/{book_id}/pages/{page}')
def page_context(book_id: str,page: int):
    book=book_or_404(book_id)
    if not 1<=page<=book['pages']:raise HTTPException(422,'페이지 범위를 벗어났습니다.')
    chunks=many('SELECT c.*,b.title FROM chunks c JOIN books b ON b.id=c.book_id WHERE c.book_id=? AND c.page=? ORDER BY c.rowid',(book_id,page))
    return {'book_id':book_id,'page':page,'chunks':chunks,'has_text':bool(chunks)}

@app.get('/api/settings')
def get_settings():
    local=settings.ai_provider=='ollama'
    return {'mode':settings.ai_mode,'provider':settings.ai_provider,'model':settings.ollama_model if local else settings.openai_model,
            'has_key':False if local else bool(settings.openai_api_key),'external_enabled':False if local else settings.allow_external_ai,
            'max_steps':settings.max_agent_steps,'max_upload_mb':settings.max_upload_mb,
            'readiness':readiness()}

class ConnectionCheck(BaseModel):
    approve_paid_call: bool = False

@app.post('/api/ai/check')
def check_ai(payload: ConnectionCheck):
    status=readiness()
    if settings.ai_provider=='ollama':
        return {**status,'api_calls':0,'message':status['message']+' 이 확인은 로컬 모델 목록만 조회하며 텍스트를 생성하지 않습니다.'}
    if not payload.approve_paid_call or not status['ready']:
        return {**status,'api_calls':0}
    try:
        response=OpenAIProvider().respond([{'role':'user','content':'연결 확인입니다. 연결 성공이라고만 답하세요. 교과서 질문이 아닙니다.'}],[])
        return {**status,'network_checked':True,'connected':True,'api_calls':1,
                'message':'설정된 모델의 Responses 호출이 성공했습니다.',
                'usage':response.usage.model_dump() if response.usage else None}
    except AIRequestError as exc:
        return {**status,'network_checked':True,'connected':False,'api_calls':1,'message':str(exc)}
    except Exception:
        return {**status,'network_checked':True,'connected':False,'api_calls':1,
                'message':'연결 실패. 키·모델 권한·결제·네트워크 설정을 확인하세요. 키나 원시 API 오류는 표시하지 않습니다.'}

@app.get('/api/books')
def books():
    return many('SELECT b.*, (SELECT count(*) FROM visits v WHERE v.book_id=b.id) AS visited FROM books b ORDER BY created DESC,rowid DESC')

@app.post('/api/books',status_code=201)
async def upload(file: UploadFile, background: BackgroundTasks):
    if not (file.filename or '').lower().endswith('.pdf'):
        raise HTTPException(400,'PDF 파일만 업로드할 수 있습니다.')
    content = await file.read(settings.max_upload_mb*1024*1024+1)
    await file.close()
    if len(content)>settings.max_upload_mb*1024*1024: raise HTTPException(413,'파일 크기 제한을 초과했습니다.')
    book_id = register_pdf(content,file.filename)
    background.add_task(index_book,book_id)
    return book_or_404(book_id)

class BookPatch(BaseModel):
    title: str = Field(min_length=1,max_length=300)
    author: str = Field(max_length=300)
    category: str = Field(min_length=1,max_length=100)

@app.patch('/api/books/{book_id}')
def edit_book(book_id: str, patch: BookPatch):
    book_or_404(book_id)
    with db() as c:
        c.execute('UPDATE books SET title=?,author=?,category=? WHERE id=?',(patch.title,patch.author,patch.category,book_id))
    return book_or_404(book_id)

@app.delete('/api/books/{book_id}')
def delete_book(book_id: str):
    book = book_or_404(book_id)
    if book['status']=='indexing': raise HTTPException(409,'인덱싱이 끝난 후 삭제하세요.')
    with db() as c: c.execute('DELETE FROM books WHERE id=?',(book_id,))
    for ext in ['pdf','png']:
        (data_path()/'pdfs'/f'{book_id}.{ext}').unlink(missing_ok=True)
    return {'deleted':book_id}

@app.post('/api/books/{book_id}/reindex')
def reindex(book_id: str, background: BackgroundTasks):
    book = book_or_404(book_id)
    if book['status']=='indexing': raise HTTPException(409,'이미 인덱싱 중입니다.')
    with db() as c: c.execute("UPDATE books SET status='indexing',progress=0 WHERE id=?",(book_id,))
    background.add_task(index_book,book_id)
    return {'status':'indexing'}

@app.get('/api/books/{book_id}/pdf')
def pdf(book_id: str):
    book = book_or_404(book_id)
    return FileResponse(data_path()/'pdfs'/f'{book_id}.pdf',media_type='application/pdf',filename=book['filename'],content_disposition_type='inline')

@app.get('/api/books/{book_id}/cover')
def cover(book_id: str):
    book_or_404(book_id)
    path = data_path()/'pdfs'/f'{book_id}.png'
    if not path.exists(): raise HTTPException(404,'표지 준비 중')
    return FileResponse(path,media_type='image/png')

@app.get('/api/books/{book_id}/sections')
def sections(book_id: str):
    book_or_404(book_id)
    return many('SELECT * FROM sections WHERE book_id=? ORDER BY page,id',(book_id,))

class Position(BaseModel): page: int = Field(ge=1)

@app.put('/api/books/{book_id}/position')
def position(book_id: str, payload: Position):
    book = book_or_404(book_id)
    if payload.page>book['pages']: raise HTTPException(422,'페이지 범위를 벗어났습니다.')
    with db() as c:
        c.execute('UPDATE books SET last_page=? WHERE id=?',(payload.page,book_id))
        c.execute('INSERT OR IGNORE INTO visits VALUES(?,?)',(book_id,payload.page))
    return {'page':payload.page}

class Highlight(Position): text: str = Field(min_length=1,max_length=6000)

@app.post('/api/books/{book_id}/highlights')
def add_highlight(book_id: str, payload: Highlight):
    if payload.page>book_or_404(book_id)['pages']: raise HTTPException(422,'페이지 범위를 벗어났습니다.')
    hid = uuid.uuid4().hex
    with db() as c: c.execute('INSERT INTO highlights(id,book_id,page,text) VALUES(?,?,?,?)',(hid,book_id,payload.page,payload.text))
    return {'id':hid}

@app.get('/api/books/{book_id}/highlights')
def highlights(book_id: str):
    book_or_404(book_id)
    return many('SELECT * FROM highlights WHERE book_id=? ORDER BY page,created',(book_id,))

@app.delete('/api/highlights/{highlight_id}')
def delete_highlight(highlight_id: str):
    with db() as c: c.execute('DELETE FROM highlights WHERE id=?',(highlight_id,))
    return {'ok':True}

class SearchRequest(BaseModel):
    query: str = Field(min_length=1,max_length=1000)
    book_ids: list[str] | None = Field(default=None,max_length=50)
    page: int | None = Field(default=None,ge=1)
    current_book_id: str | None = None

@app.post('/api/search')
def search_endpoint(payload: SearchRequest): return search(payload.query,payload.book_ids,payload.page,current_book_id=payload.current_book_id)

@app.post('/api/chat')
def chat(payload: ChatRequest):
    book = book_or_404(payload.book_id)
    if payload.page>book['pages']: raise HTTPException(422,'페이지 범위를 벗어났습니다.')
    if book['status']!='ready': raise HTTPException(409,'텍스트 인덱싱이 완료된 교과서를 선택하세요.')
    if payload.scope=='selected' and not payload.book_ids: raise HTTPException(422,'검색할 교과서를 선택하세요.')
    for bid in payload.book_ids: book_or_404(bid)
    if payload.quiz_id:payload.strategy='agent'
    try: return Agent(payload).run()
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.get('/api/books/{book_id}/history')
def book_history(book_id: str):
    book_or_404(book_id)
    rows = many('SELECT r.* FROM runs r JOIN sessions s ON s.id=r.session_id WHERE s.book_id=? ORDER BY r.created,r.rowid',(book_id,))
    return [{**r,'request':json.loads(r['request']),'response':json.loads(r['response']) if r['response'] else None} for r in rows]

@app.get('/api/dashboard')
def dashboard():
    mastery = many('SELECT m.*,c.name,c.book_id,b.title FROM mastery m JOIN concepts c ON c.id=m.concept_id JOIN books b ON b.id=c.book_id ORDER BY m.updated DESC')
    attempts = many('SELECT a.correct,a.uncertain,a.created,c.name,b.title FROM attempts a JOIN quizzes q ON q.id=a.quiz_id JOIN concepts c ON c.id=q.concept_id JOIN books b ON b.id=c.book_id ORDER BY a.created DESC LIMIT 30')
    graded = [a for a in attempts if not a['uncertain']]
    return {'books':books(),'mastery':mastery,'attempts':attempts,
            'accuracy':round(sum(a['correct'] for a in graded)/len(graded)*100) if graded else None,
            'runs':one('SELECT count(*) AS n FROM runs')['n'],
            'recent':many('SELECT r.id,r.created,r.status,r.mode,b.title FROM runs r JOIN sessions s ON s.id=r.session_id JOIN books b ON b.id=s.book_id ORDER BY r.created DESC LIMIT 12')}

if (ROOT/'frontend'/'dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'frontend'/'dist',html=True),name='frontend')
