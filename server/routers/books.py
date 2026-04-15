"""
Books API — upload epub, list library, get book details.
"""
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models.database import get_db, Book, Chapter, Screenplay, ScreenplaySegment
from models.schemas import BookResponse, ChapterListResponse
from services.epub.parser import parse_epub, save_cover
from services.pdf.parser import parse_pdf
from config import settings

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api/books", tags=["books"])


@router.post("", response_model=BookResponse)
async def upload_book(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an .epub or .pdf file and parse it into the library."""
    filename = (file.filename or "").lower()
    if filename.endswith(".epub"):
        fmt = "epub"
    elif filename.endswith(".pdf"):
        fmt = "pdf"
    else:
        raise HTTPException(400, "Only .epub and .pdf files are supported")

    # Save uploaded file — we keep the old "epubs" directory name so existing
    # installs don't need a migration; the path column stays `epub_path`.
    file_id = str(uuid.uuid4())
    epub_dir = os.path.join(settings.upload_dir, "epubs")
    os.makedirs(epub_dir, exist_ok=True)
    epub_path = os.path.join(epub_dir, f"{file_id}.{fmt}")

    with open(epub_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse the file using the right parser for its format
    try:
        parsed = parse_pdf(epub_path) if fmt == "pdf" else parse_epub(epub_path)
    except Exception as e:
        try: os.remove(epub_path)
        except OSError: pass
        raise HTTPException(400, f"Failed to parse {fmt}: {str(e)}")

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
    import time
    t0 = time.time()
    book = db.query(Book).filter(Book.id == book_id).first()
    elapsed = round((time.time() - t0) * 1000, 1)
    logger.info(f"GET /api/books/{book_id} — db query took {elapsed}ms, found={'yes' if book else 'no'}")
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


@router.post("/{book_id}/refresh-cover", response_model=BookResponse)
async def refresh_cover(book_id: str, db: Session = Depends(get_db)):
    """
    Re-fetch the book's cover image.

    Strategy:
      1. If the original epub/pdf is still on disk, re-parse and re-extract
         the embedded cover. This is the highest-fidelity option.
      2. Otherwise (e.g. pre-persistent-disk book, file lost), query the
         OpenLibrary cover API by title + author and download that.
      3. If both fail, return the book unchanged with an explanatory log.

    Persistent on disk, so subsequent deploys don't wipe the refreshed cover
    (as long as the Render disk stays attached).
    """
    import logging
    log = logging.getLogger(__name__)

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    new_cover_url: str | None = None

    # Strategy 1 — re-parse the source file if we still have it
    if book.epub_path and os.path.exists(book.epub_path):
        try:
            fmt = "pdf" if book.epub_path.lower().endswith(".pdf") else "epub"
            parsed = parse_pdf(book.epub_path) if fmt == "pdf" else parse_epub(book.epub_path)
            if parsed.cover_data:
                new_cover_url = save_cover(parsed.cover_data, parsed.cover_ext, settings.upload_dir)
                log.info(f"refresh_cover: re-extracted from local {fmt} for book {book_id}")
        except Exception as e:
            log.warning(f"refresh_cover: local re-parse failed for {book_id}: {e}")

    # Strategy 2 — OpenLibrary fallback (no auth, no key needed)
    if not new_cover_url:
        try:
            import httpx
            # Search by title + author to find the most relevant edition
            params = {"title": book.title, "limit": 1}
            if book.author and book.author.lower() != "unknown":
                params["author"] = book.author

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get("https://openlibrary.org/search.json", params=params)
                r.raise_for_status()
                data = r.json()
                docs = data.get("docs", [])
                cover_id = docs[0].get("cover_i") if docs else None

                if cover_id:
                    # Large cover — Open Library's "-L.jpg" variant
                    img_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                    img_r = await client.get(img_url)
                    img_r.raise_for_status()
                    if img_r.content and len(img_r.content) > 1024:  # skip placeholder 1x1 images
                        new_cover_url = save_cover(img_r.content, "jpg", settings.upload_dir)
                        log.info(f"refresh_cover: fetched OpenLibrary cover_id={cover_id} for book {book_id}")
        except Exception as e:
            log.warning(f"refresh_cover: OpenLibrary lookup failed for {book_id}: {e}")

    if not new_cover_url:
        raise HTTPException(
            404,
            "Could not refresh cover — original file is missing and OpenLibrary has no match for this title/author.",
        )

    # Delete old cover file if we know where it is (best-effort)
    if book.cover_url and book.cover_url.startswith("/static/covers/"):
        old_path = os.path.join(settings.upload_dir, "covers", os.path.basename(book.cover_url))
        try:
            if os.path.exists(old_path):
                os.remove(old_path)
        except OSError:
            pass

    book.cover_url = new_cover_url
    db.commit()
    db.refresh(book)
    return book


@router.delete("/{book_id}")
async def delete_book(book_id: str, db: Session = Depends(get_db)):
    """Delete a book and ALL associated data — epub, cover, audio, screenplays, characters."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    files_deleted = 0
    files_missing = 0

    def _rm(path: str):
        nonlocal files_deleted, files_missing
        if not path:
            return
        # audio_url values are URL paths like /static/audio/filename.mp3
        # convert to filesystem path
        if path.startswith("/static/audio/"):
            path = os.path.join(settings.upload_dir, "audio", os.path.basename(path))
        elif path.startswith("/static/covers/"):
            path = os.path.join(settings.upload_dir, "covers", os.path.basename(path))
        try:
            if os.path.exists(path):
                os.remove(path)
                files_deleted += 1
            else:
                files_missing += 1
        except Exception as e:
            logger.warning(f"Could not delete file {path}: {e}")

    # Delete epub
    _rm(book.epub_path)

    # Delete cover image
    if book.cover_url:
        _rm(book.cover_url)

    # Delete all audio files for every segment of every screenplay of every chapter
    chapters = db.query(Chapter).filter(Chapter.book_id == book_id).all()
    for chapter in chapters:
        screenplays = db.query(Screenplay).filter(Screenplay.chapter_id == chapter.id).all()
        for screenplay in screenplays:
            segments = db.query(ScreenplaySegment).filter(ScreenplaySegment.screenplay_id == screenplay.id).all()
            for seg in segments:
                if seg.audio_url:
                    _rm(seg.audio_url)

    logger.info(f"Book {book_id} delete: removed {files_deleted} files ({files_missing} already missing)")

    # DB delete cascades: book → chapters → screenplays → segments/revision_rounds + characters
    db.delete(book)
    db.commit()

    return {"status": "deleted", "files_removed": files_deleted}
