import hashlib
import re
import sqlite3
import uuid
from pathlib import Path
import pymupdf
from fastapi import HTTPException
from .database import db, data_path, one

def register_pdf(content: bytes, filename: str):
    if not content.startswith(b'%PDF-'):
        raise HTTPException(400, '유효한 PDF 파일이 아닙니다.')
    digest = hashlib.sha256(content).hexdigest()
    if one('SELECT id FROM books WHERE hash=?', (digest,)):
        raise HTTPException(409, '이미 등록된 PDF입니다.')
    try:
        doc = pymupdf.open(stream=content, filetype='pdf')
        if doc.needs_pass or not len(doc):
            raise ValueError('encrypted or empty')
        meta, pages = doc.metadata or {}, len(doc)
        doc.close()
    except Exception:
        raise HTTPException(400, '손상되었거나 암호로 보호된 PDF입니다.')
    book_id = uuid.uuid4().hex
    safe_name = Path(filename.replace('\\', '/')).name
    path = data_path() / 'pdfs' / f'{book_id}.pdf'
    path.write_bytes(content)
    try:
        with db() as c:
            c.execute('INSERT INTO books(id,title,author,filename,hash,pages) VALUES(?,?,?,?,?,?)',
                      (book_id, meta.get('title') or Path(safe_name).stem, meta.get('author') or '저자 미상', safe_name, digest, pages))
    except sqlite3.IntegrityError:
        path.unlink(missing_ok=True)
        raise HTTPException(409, '이미 등록된 PDF입니다.')
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return book_id

def index_book(book_id):
    book = one('SELECT * FROM books WHERE id=?', (book_id,))
    if not book:
        return
    try:
        with db() as c:
            c.execute("UPDATE books SET status='indexing',progress=0,error=NULL WHERE id=?", (book_id,))
        sections, chunks = [], []
        with pymupdf.open(data_path() / 'pdfs' / f'{book_id}.pdf') as doc:
            toc = doc.get_toc()
            for level, title, page in toc:
                if 1 <= page <= len(doc):
                    sections.append((book_id, title, page, level, 0))
            if not sections:
                for i, page in enumerate(doc):
                    lines = page.get_text().strip().splitlines()
                    if lines and re.match(r'^(\d+[.\s]|chapter|part|제\s*\d)', lines[0], re.I):
                        sections.append((book_id, lines[0][:160], i+1, 1, 1))
            for i, page in enumerate(doc):
                candidates = [s for s in sections if s[2] <= i+1]
                section = max(candidates, key=lambda s: (s[2], s[3]))[1] if candidates else ''
                label = page.get_label() or None
                for block_index, block in enumerate(page.get_text('blocks', sort=True)):
                    text = block[4].strip()
                    # Short blocks can be a fraction denominator or a one-letter
                    # mathematical index. Never discard nonempty formula text.
                    if not text:
                        continue
                    warning = '추출 문자 손상 의심: 원본 수식을 확인하세요.' if '\ufffd' in text or '\x00' in text else None
                    for offset in range(0, len(text), 1400):
                        part = text[offset:offset+1600]
                        cid = hashlib.sha256(f'{book_id}:{i}:{block_index}:{offset}'.encode()).hexdigest()[:32]
                        chunks.append((cid, book_id, i+1, label, section, part, warning))
                if i % 20 == 0:
                    with db() as c:
                        c.execute('UPDATE books SET progress=? WHERE id=?', (round((i+1)/len(doc)*95), book_id))
            doc[0].get_pixmap(matrix=pymupdf.Matrix(.45,.45)).save(str(data_path() / 'pdfs' / f'{book_id}.png'))
        with db() as c:
            # FTS5's UNINDEXED chunk_id makes the per-row delete trigger scan
            # the entire index repeatedly. Replace this book atomically with
            # one FTS delete; SQLite serializes writers until trigger restore.
            c.execute('BEGIN IMMEDIATE')
            c.execute('DROP TRIGGER IF EXISTS chunk_delete')
            c.execute('DELETE FROM chunks_fts WHERE book_id=?',(book_id,))
            c.execute('DELETE FROM sections WHERE book_id=?', (book_id,))
            c.execute('DELETE FROM chunks WHERE book_id=?', (book_id,))
            c.executemany('INSERT INTO sections(book_id,title,page,level,inferred) VALUES(?,?,?,?,?)', sections)
            c.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)', chunks)
            c.executemany('INSERT INTO chunks_fts(text,chunk_id,book_id) VALUES(?,?,?)', [(r[5],r[0],r[1]) for r in chunks])
            c.execute('''CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
                         DELETE FROM chunks_fts WHERE chunk_id=old.id; END''')
            c.execute('UPDATE books SET status=?,progress=100,error=? WHERE id=?',
                      ('ready' if chunks else 'no_text', None if chunks else '텍스트가 없는 PDF입니다. OCR은 아직 지원하지 않습니다.', book_id))
    except Exception:
        with db() as c:
            c.execute("UPDATE books SET status='error',error='PDF 분석 실패. 파일을 확인하고 재인덱싱하세요.' WHERE id=?", (book_id,))
