import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import settings

def data_path():
    p = Path(settings.data_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    (p / 'pdfs').mkdir(exist_ok=True)
    return p

@contextmanager
def db():
    con = sqlite3.connect(data_path() / 'scholarpilot.db', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS books (
          id TEXT PRIMARY KEY, title TEXT, author TEXT, category TEXT DEFAULT '미분류',
          filename TEXT, hash TEXT UNIQUE, pages INTEGER, last_page INTEGER DEFAULT 1,
          status TEXT DEFAULT 'indexing', progress INTEGER DEFAULT 0, error TEXT,
          created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS sections (
          id INTEGER PRIMARY KEY, book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
          title TEXT, page INTEGER, level INTEGER, inferred INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY, book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
          page INTEGER, printed_page TEXT, section TEXT, text TEXT, warning TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, chunk_id UNINDEXED, book_id UNINDEXED, tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
          DELETE FROM chunks_fts WHERE chunk_id=old.id; END;
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
          state TEXT DEFAULT 'ready', created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
          request TEXT, response TEXT, status TEXT, mode TEXT, usage TEXT,
          elapsed REAL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
          tool TEXT, input TEXT, output TEXT, status TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS concepts (
          id TEXT PRIMARY KEY, book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
          name TEXT, UNIQUE(book_id,name));
        CREATE TABLE IF NOT EXISTS relations (
          source TEXT REFERENCES concepts(id) ON DELETE CASCADE,
          target TEXT REFERENCES concepts(id) ON DELETE CASCADE, evidence TEXT,
          PRIMARY KEY(source,target));
        CREATE TABLE IF NOT EXISTS quizzes (
          id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
          concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
          payload TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attempts (
          id TEXT PRIMARY KEY, quiz_id TEXT REFERENCES quizzes(id) ON DELETE CASCADE UNIQUE,
          answer TEXT, correct INTEGER, uncertain INTEGER, feedback TEXT,
          created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS mastery (
          concept_id TEXT PRIMARY KEY REFERENCES concepts(id) ON DELETE CASCADE,
          correct INTEGER DEFAULT 0, total INTEGER DEFAULT 0, streak INTEGER DEFAULT 0,
          status TEXT DEFAULT '학습 중', updated TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS visits (
          book_id TEXT REFERENCES books(id) ON DELETE CASCADE, page INTEGER,
          PRIMARY KEY(book_id,page));
        CREATE TABLE IF NOT EXISTS highlights (
          id TEXT PRIMARY KEY, book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
          page INTEGER, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        c.execute("UPDATE books SET status='error',error='인덱싱 중 종료되었습니다. 재인덱싱을 실행하세요.' WHERE status='indexing'")

def one(sql, args=()):
    with db() as c:
        row = c.execute(sql, args).fetchone()
        return dict(row) if row else None

def many(sql, args=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
