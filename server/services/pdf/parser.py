"""
PDF parsing service — extracts chapters and metadata from text-based PDF files.

Returns the same `ParsedBook` / `ParsedChapter` shape as the epub parser so the
downstream pipeline (character detection, screenplay, audio, director) works
unchanged.

Chapter detection strategy (in order of preference):
  1. PDF outline / bookmarks — most commercial ebooks have these.
  2. Regex for "Chapter N" / "CHAPTER N" / Roman-numeral headings at page starts.
  3. Last resort: treat the entire PDF as a single chapter.

Cover art is not extracted — PDF-to-image rendering needs system deps (poppler)
or an AGPL library (PyMuPDF). Covers fall back to the placeholder in the UI.

Scanned/image-only PDFs are NOT supported — OCR is out of scope.
"""
import os
import re
from typing import Optional

from pypdf import PdfReader

# Re-use the shared dataclasses from the epub parser — same shape contract
from services.epub.parser import ParsedBook, ParsedChapter


# Matches "Chapter 1", "CHAPTER XII", "Chapter One", etc. at the start of a line.
# Intentionally permissive — the candidate line is cross-checked for length (<= 80 chars).
_CHAPTER_HEADING_RE = re.compile(
    r"^\s*(chapter|part|book)\s+"
    r"([0-9]+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty)"
    r"\b.*$",
    re.IGNORECASE,
)

# Short lines of only digits/roman-numerals (e.g., standalone "I", "II", "1")
_NUMERIC_HEADING_RE = re.compile(r"^\s*([0-9]{1,3}|[IVXLCDM]{1,6})\s*$")


def _clean_page_text(raw: str) -> str:
    """Light normalization — collapse hyphenated line breaks and excess whitespace."""
    if not raw:
        return ""
    # Join words split across line breaks by a trailing hyphen:  "fire-\nplace" -> "fireplace"
    text = re.sub(r"-\n(\w)", r"\1", raw)
    # Collapse runs of blank lines into a single paragraph break
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if ln.strip():
            out.append(ln.strip())
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def _extract_text_pages(reader: PdfReader) -> list[str]:
    """Extract text for every page. Pages that fail to extract become empty strings."""
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(_clean_page_text(page.extract_text() or ""))
        except Exception:
            pages.append("")
    return pages


def _chapters_from_outline(reader: PdfReader, pages: list[str]) -> Optional[list[ParsedChapter]]:
    """
    Use the PDF's outline (TOC bookmarks) as chapter boundaries if present.
    Returns None if there's no usable outline.
    """
    try:
        outline = reader.outline  # pypdf exposes this as a (possibly nested) list
    except Exception:
        return None

    if not outline:
        return None

    # Flatten the possibly-nested outline into (title, page_index) tuples.
    # Only keep top-level entries — nested subsections would over-split chapters.
    entries: list[tuple[str, int]] = []
    for item in outline:
        if isinstance(item, list):
            # Skip nested sub-sections
            continue
        try:
            title = (getattr(item, "title", None) or "").strip()
            page_idx = reader.get_destination_page_number(item)
        except Exception:
            continue
        if title and isinstance(page_idx, int) and 0 <= page_idx < len(pages):
            entries.append((title, page_idx))

    if len(entries) < 2:
        # A single entry (or none) isn't a useful TOC
        return None

    # Drop obvious front-matter like "Cover", "Title Page", "Copyright", "Dedication",
    # "Contents", "Table of Contents", "Acknowledgements", "Also by"
    front_matter_patterns = re.compile(
        r"^(cover|title\s*page|copyright|dedication|contents?|table\s+of\s+contents|"
        r"acknowledg|also\s+by|about\s+the\s+author|foreword|preface)",
        re.IGNORECASE,
    )
    entries = [(t, p) for (t, p) in entries if not front_matter_patterns.match(t)]
    if len(entries) < 2:
        return None

    # Sort by page index just in case the outline is out of order
    entries.sort(key=lambda e: e[1])

    chapters: list[ParsedChapter] = []
    for i, (title, start) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else len(pages)
        body = "\n\n".join(p for p in pages[start:end] if p)
        word_count = len(body.split())
        if word_count < 50:
            # Skip very short TOC entries — probably not real chapters
            continue
        chapters.append(ParsedChapter(
            number=len(chapters) + 1,
            title=title[:200],
            raw_text=body,
            word_count=word_count,
        ))

    return chapters if len(chapters) >= 2 else None


def _chapters_from_regex(pages: list[str]) -> Optional[list[ParsedChapter]]:
    """
    Scan pages for chapter-heading patterns. Each match starts a new chapter.
    Returns None if fewer than 2 headings are found (no reliable split).
    """
    boundaries: list[tuple[int, str]] = []  # (page_index, heading_text)

    for idx, page_text in enumerate(pages):
        if not page_text:
            continue
        # Look at the first handful of non-empty lines — chapter headings appear near the top
        lines = [ln for ln in page_text.splitlines() if ln.strip()][:5]
        for line in lines:
            if len(line) > 80:
                continue
            if _CHAPTER_HEADING_RE.match(line) or _NUMERIC_HEADING_RE.match(line):
                boundaries.append((idx, line.strip()))
                break

    if len(boundaries) < 2:
        return None

    chapters: list[ParsedChapter] = []
    for i, (start, heading) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(pages)
        body = "\n\n".join(p for p in pages[start:end] if p)
        word_count = len(body.split())
        if word_count < 50:
            continue
        chapters.append(ParsedChapter(
            number=len(chapters) + 1,
            title=heading[:200] or f"Chapter {len(chapters) + 1}",
            raw_text=body,
            word_count=word_count,
        ))

    return chapters if len(chapters) >= 2 else None


def _whole_pdf_as_one_chapter(pages: list[str], fallback_title: str) -> list[ParsedChapter]:
    """Last-resort fallback — treat the whole PDF as a single chapter."""
    body = "\n\n".join(p for p in pages if p).strip()
    word_count = len(body.split())
    return [ParsedChapter(
        number=1,
        title=fallback_title or "Chapter 1",
        raw_text=body,
        word_count=word_count,
    )]


def parse_pdf(file_path: str) -> ParsedBook:
    """Parse a text-based PDF and return a ParsedBook matching the epub parser's shape."""
    reader = PdfReader(file_path)

    # ── Metadata ─────────────────────────────────────────────────────────────
    meta = reader.metadata or {}

    def _meta(key: str) -> Optional[str]:
        try:
            value = meta.get(key)
        except Exception:
            return None
        if value is None:
            return None
        try:
            value = str(value).strip()
        except Exception:
            return None
        return value or None

    title = _meta("/Title") or os.path.splitext(os.path.basename(file_path))[0]
    author = _meta("/Author") or "Unknown"
    description = _meta("/Subject")  # PDF has no dedicated description field
    language = "en"

    # ── Page text ────────────────────────────────────────────────────────────
    pages = _extract_text_pages(reader)
    total_extracted_words = sum(len((p or "").split()) for p in pages)
    if total_extracted_words < 100:
        # Almost no extractable text — probably a scanned/image-only PDF
        raise ValueError(
            "This PDF has no extractable text — it may be a scanned or image-only PDF. "
            "OCR is not supported. Please upload a text-based PDF or an epub."
        )

    # ── Chapter detection: outline → regex → whole-pdf fallback ──────────────
    chapters = _chapters_from_outline(reader, pages)
    if not chapters:
        chapters = _chapters_from_regex(pages)
    if not chapters:
        chapters = _whole_pdf_as_one_chapter(pages, title)

    total_words = sum(ch.word_count for ch in chapters)

    return ParsedBook(
        title=title,
        author=author,
        language=language,
        description=description,
        cover_data=None,  # Covers not extracted from PDFs — see module docstring
        cover_ext=None,
        chapters=chapters,
        total_words=total_words,
    )
