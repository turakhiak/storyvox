"""
Books API — upload epub, list library, get book details.
"""
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models.database import get_db, Book, Chapter
from models.schemas import BookResponse, ChapterListResponse
from services.epub.parser import parse_epub, save_cover
from config import settings

router = APIRouter(prefix="/api/books", tags=["books"])


@router.post("", response_model=BookResponse)
async def upload_book(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an epub file and parse it into the library."""
    if not file.filename or not file.filename.lower().endswith(".epub"):
        raise HTTPException(400, "Only .epub files are supported")

    # Save uploaded file
    file_id = str(uuid.uuid4())
    epub_dir = os.path.join(settings.upload_dir, "epubs")
    os.makedirs(epub_dir, exist_ok=True)
    epub_path = os.path.join(epub_dir, f"{file_id}.epub")

    with open(epub_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse the epub
    try:
        parsed = parse_epub(epub_path)
    except Exception as e:
        os.remove(epub_path)
        raise HTTPException(400, f"Failed to parse epub: {str(e)}")

    # Save cover image
    cover_url = None
    if parsed.cover_data:
        cover_url = save_cover(parsed.cover_data, parsed.cover_ext, settings.upload_dir)

    # Create book record
    book = Book(
        title=parsed.title,
        author=parsed.author,
        language=parsed.language,
        description=parsed.description,
        cover_url=cover_url,
        epub_path=epub_path,
        total_chapters=len(parsed.chapters),
        total_words=parsed.total_words,
        status="imported",
    )
    db.add(book)
    db.flush()

    # Create chapter records
    for ch in parsed.chapters:
        chapter = Chapter(
            book_id=book.id,
            number=ch.number,
            title=ch.title,
            raw_text=ch.raw_text,
            word_count=ch.word_count,
            status="parsed",
        )
        db.add(chapter)

    db.commit()
    db.refresh(book)

    return book


@router.get("", response_model=list[BookResponse])
async def list_books(db: Session = Depends(get_db)):
    """List all books in the library."""
    books = db.query(Book).order_by(Book.created_at.desc()).all()
    return books


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(book_id: str, db: Session = Depends(get_db)):
    """Get a single book's details."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")
    return book


@router.get("/{book_id}/chapters", response_model=list[ChapterListResponse])
async def list_chapters(book_id: str, db: Session = Depends(get_db)):
    """List all chapters of a book."""
    chapters = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.number)
        .all()
    )
    return chapters


@router.get("/{book_id}/chapters/{chapter_num}")
async def get_chapter(book_id: str, chapter_num: int, db: Session = Depends(get_db)):
    """Get a single chapter with full text."""
    chapter = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id, Chapter.number == chapter_num)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    return {
        "id": chapter.id,
        "book_id": chapter.book_id,
        "number": chapter.number,
        "title": chapter.title,
        "raw_text": chapter.raw_text,
        "word_count": chapter.word_count,
        "status": chapter.status,
    }


@router.patch("/{book_id}/bookmark")
async def update_bookmark(book_id: str, chapter_num: int = Query(...), db: Session = Depends(get_db)):
    """Update the listening bookmark (last chapter the user listened to)."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")
    book.listen_bookmark = chapter_num
    db.commit()
    return {"book_id": book_id, "listen_bookmark": chapter_num}


@router.delete("/{book_id}")
async def delete_book(book_id: str, db: Session = Depends(get_db)):
    """Delete a book and all associated data."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    # Clean up files
    if book.epub_path and os.path.exists(book.epub_path):
        os.remove(book.epub_path)

    db.delete(book)
    db.commit()

    return {"status": "deleted"}
