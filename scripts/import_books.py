"""Explicit local import; never sends a PDF over the network."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.database import init_db, one
from backend.ingestion import register_pdf, index_book
from fastapi import HTTPException

def main():
    init_db()
    directory = Path(sys.argv[1]) if len(sys.argv)>1 else Path('Books')
    for file in directory.glob('*.pdf'):
        try:
            bid = register_pdf(file.read_bytes(),file.name)
            index_book(bid)
            b = one('SELECT title,pages,status FROM books WHERE id=?',(bid,))
            print(b)
        except HTTPException as e:
            print(f'{file.name}: {e.detail}')

if __name__=='__main__': main()
