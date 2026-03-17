"""
Chapter filtering — skip front matter and back matter for character detection & screenplay generation.

Front matter: title page, copyright, dedication, table of contents, praise, etc.
Back matter: acknowledgements, about the author, reading group guide, also by, excerpt from next book, etc.

Strategy:
  1. Exact title match against a known set (case-insensitive, stripped)
  2. Substring/prefix match for patterns like "Praise for ...", "Excerpt from ...", "Also by ..."
  3. Word count heuristic: very short chapters (< 300 words) that appear at the start or end
  4. Position heuristic: back-matter tends to cluster at the end of the book
"""
import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.database import Chapter

logger = logging.getLogger(__name__)

# --- Exact title matches (lowercased) ---
_SKIP_TITLES_EXACT = {
    # Front matter
    "contents", "table of contents", "toc",
    "title page", "half title", "half-title",
    "cover", "cover page", "front cover",
    "copyright", "copyright page", "copyright notice",
    "dedication", "dedications",
    "epigraph",
    "praise", "endorsements", "blurb", "blurbs",
    "series page", "books in this series",
    "foreword", "preface",
    "author's note", "author note", "a note from the author",
    "note to the reader", "note to reader",
    "map", "maps", "list of characters", "dramatis personae",
    "cast of characters",
    # Back matter
    "acknowledgements", "acknowledgments", "acknowledgement", "acknowledgment",
    "about the author", "about the authors", "about the writer",
    "about the translator", "about the illustrator",
    "also by", "other books by", "books by the author", "other works",
    "bibliography", "references", "sources", "works cited",
    "glossary", "index", "appendix", "appendices",
    "reading group guide", "book club guide", "discussion questions",
    "reader's guide", "readers guide", "reading guide",
    "q&a", "q & a", "interview with the author", "a conversation with",
    "excerpt", "sneak peek", "preview", "bonus chapter",
    "teaser", "coming soon", "next in the series",
    "newsletter", "connect with", "follow the author",
    "colophon", "publisher's note", "editor's note",
    "permissions", "credits", "photo credits", "image credits",
    "afterword", "postscript",
}

# --- Prefix/substring patterns (lowercased) ---
# If a chapter title STARTS WITH any of these, skip it
_SKIP_TITLE_PREFIXES = [
    "praise for",
    "also by",
    "other books by",
    "books by",
    "excerpt from",
    "a preview of",
    "an excerpt from",
    "sneak peek of",
    "preview of",
    "about the",
    "copyright ©",
    "copyright (c)",
    "from the author of",
    "don't miss",
    "look for",
    "coming soon",
    "connect with",
    "follow ",
    "newsletter",
    "reading group",
    "book club",
    "discussion questions",
    "bonus ",
]

# --- Substring patterns (if title CONTAINS any of these) ---
_SKIP_TITLE_SUBSTRINGS = [
    "acknowledgment",
    "acknowledgement",
    "about the author",
    "reading group",
    "discussion question",
    "book club guide",
    "also available",
    "newsletter signup",
    "next in series",
]

# Regex for roman numeral-only titles that are unlikely to be real chapter names
_ROMAN_ONLY = re.compile(r"^[IVXLCDM]+\.?$", re.IGNORECASE)


def is_non_story_chapter(chapter: "Chapter", total_chapters: int) -> bool:
    """
    Returns True if this chapter is likely front-matter or back-matter
    (not actual story content) and should be skipped for character detection
    and screenplay generation.
    """
    title = (chapter.title or "").strip()
    title_lower = title.lower()

    # 1. Exact title match
    if title_lower in _SKIP_TITLES_EXACT:
        return True

    # 2. Prefix match
    for prefix in _SKIP_TITLE_PREFIXES:
        if title_lower.startswith(prefix):
            return True

    # 3. Substring match
    for sub in _SKIP_TITLE_SUBSTRINGS:
        if sub in title_lower:
            return True

    # 4. Very short "chapters" (< 300 words) — likely not real story content
    #    Exception: short chapters that look like numbered story chapters
    if chapter.word_count < 300:
        # If the title is a number or "Chapter N", it might be a legitimate short chapter
        is_numbered = bool(re.match(r"^(chapter\s+)?\d+\.?$", title_lower))
        is_roman = bool(_ROMAN_ONLY.match(title_lower))
        if not is_numbered and not is_roman:
            return True

    # 5. Very short chapters at the very end of the book (likely appendix/credits)
    #    Last 3 chapters that are under 500 words
    if chapter.number > total_chapters - 3 and chapter.word_count < 500:
        # Check if it doesn't look like a numbered story chapter
        is_numbered = bool(re.match(r"^(chapter\s+)?\d+\.?$", title_lower))
        is_roman = bool(_ROMAN_ONLY.match(title_lower))
        if not is_numbered and not is_roman and not title_lower.startswith("epilogue"):
            return True

    return False


def filter_story_chapters(chapters: list["Chapter"], total_chapters: int) -> list["Chapter"]:
    """
    Filter a list of chapters to only include actual story content.
    Returns the filtered list, preserving order.
    """
    story = [ch for ch in chapters if not is_non_story_chapter(ch, total_chapters)]

    skipped = len(chapters) - len(story)
    if skipped > 0:
        skipped_titles = [
            f"  #{ch.number}: '{ch.title}' ({ch.word_count}w)"
            for ch in chapters
            if is_non_story_chapter(ch, total_chapters)
        ]
        logger.info(
            f"Chapter filter: {len(story)} story chapters kept, "
            f"{skipped} non-story skipped:\n" + "\n".join(skipped_titles[:15])
        )

    return story
