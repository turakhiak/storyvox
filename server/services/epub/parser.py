"""
Epub parsing service — extracts chapters, metadata, and cover art from epub files.
"""
import os
import re
import uuid
from dataclasses import dataclass
from typing import Optional

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


@dataclass
class ParsedChapter:
    number: int
    title: str
    raw_text: str
    word_count: int


@dataclass
class ParsedBook:
    title: str
    author: str
    language: str
    description: Optional[str]
    cover_data: Optional[bytes]
    cover_ext: Optional[str]
    chapters: list[ParsedChapter]
    total_words: int


def clean_html_to_text(html_content: str) -> str:
    """Convert HTML content to clean plain text."""
    soup = BeautifulSoup(html_content, "lxml")

    # Remove script and style elements
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)

    return "\n\n".join(lines)


def extract_chapter_title(html_content: str, fallback_number: int) -> str:
    """Try to extract chapter title from HTML headings."""
    soup = BeautifulSoup(html_content, "lxml")

    # Look for headings
    for tag in ["h1", "h2", "h3"]:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text(strip=True)
            if title and len(title) < 200:
                return title

    return f"Chapter {fallback_number}"


def parse_epub(file_path: str) -> ParsedBook:
    """Parse an epub file and extract all content."""
    book = epub.read_epub(file_path, options={"ignore_ncx": True})

    # Extract metadata
    title = "Untitled"
    author = "Unknown"
    language = "en"
    description = None

    title_meta = book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]

    creator_meta = book.get_metadata("DC", "creator")
    if creator_meta:
        author = creator_meta[0][0]

    lang_meta = book.get_metadata("DC", "language")
    if lang_meta:
        language = lang_meta[0][0]

    desc_meta = book.get_metadata("DC", "description")
    if desc_meta:
        raw_desc = desc_meta[0][0]
        description = BeautifulSoup(raw_desc, "lxml").get_text(strip=True) if raw_desc else None

    # Extract cover image
    cover_data = None
    cover_ext = None

    # Try to find cover image
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_COVER:
            cover_data = item.get_content()
            name = item.get_name().lower()
            cover_ext = "jpg" if "jpg" in name or "jpeg" in name else "png"
            break

    if not cover_data:
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            name = item.get_name().lower()
            if "cover" in name:
                cover_data = item.get_content()
                cover_ext = "jpg" if "jpg" in name or "jpeg" in name else "png"
                break

    # Extract chapters
    chapters: list[ParsedChapter] = []
    chapter_num = 1

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content().decode("utf-8", errors="replace")
        text = clean_html_to_text(content)

        # Skip very short content (likely title pages, copyright, etc.)
        word_count = len(text.split())
        if word_count < 50:
            continue

        title_text = extract_chapter_title(content, chapter_num)

        chapters.append(ParsedChapter(
            number=chapter_num,
            title=title_text,
            raw_text=text,
            word_count=word_count
        ))
        chapter_num += 1

    total_words = sum(ch.word_count for ch in chapters)

    return ParsedBook(
        title=title,
        author=author,
        language=language,
        description=description,
        cover_data=cover_data,
        cover_ext=cover_ext,
        chapters=chapters,
        total_words=total_words
    )


def save_cover(cover_data: bytes, cover_ext: str, upload_dir: str) -> str:
    """Save cover image and return the relative path."""
    covers_dir = os.path.join(upload_dir, "covers")
    os.makedirs(covers_dir, exist_ok=True)

    filename = f"{uuid.uuid4()}.{cover_ext}"
    filepath = os.path.join(covers_dir, filename)

    with open(filepath, "wb") as f:
        f.write(cover_data)

    return f"/static/covers/{filename}"
