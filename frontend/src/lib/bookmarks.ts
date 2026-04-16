// Per-book bookmarks. Stored in localStorage so we don't need a schema
// migration — a reader-side feature that doesn't need to survive across
// devices (yet). If we ever want cross-device sync, we'd move this to the
// server and key by user, but that's out of scope for the MVP.
//
// A bookmark is a (chapterNum, segmentIndex) pair — the segment index is
// -1 when the user bookmarks the top of a chapter (no segment selected,
// e.g. before pressing play). Deep links use `?seg=<index>` to jump back.

export interface Bookmark {
  id: string;
  bookId: string;
  chapterNum: number;
  chapterTitle: string;
  segmentIndex: number;  // -1 = top of chapter (no specific segment)
  snippet: string;       // short text preview for the list UI
  createdAt: string;     // ISO timestamp
}

const KEY = (bookId: string) => `storyvox:bookmarks:${bookId}`;

function read(bookId: string): Bookmark[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY(bookId));
    return raw ? (JSON.parse(raw) as Bookmark[]) : [];
  } catch {
    return [];
  }
}

function write(bookId: string, bms: Bookmark[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY(bookId), JSON.stringify(bms));
  } catch {
    // Silently swallow quota / privacy-mode failures — bookmarks are a
    // nice-to-have, not a correctness requirement.
  }
}

// Sorted by position in the book so the list reads naturally.
export function listBookmarks(bookId: string): Bookmark[] {
  return read(bookId).sort((a, b) => {
    if (a.chapterNum !== b.chapterNum) return a.chapterNum - b.chapterNum;
    return a.segmentIndex - b.segmentIndex;
  });
}

// Add a bookmark, replacing any existing bookmark at the same spot so the
// list doesn't accumulate duplicates if the user taps the button twice.
export function addBookmark(bm: Omit<Bookmark, "id" | "createdAt">): Bookmark {
  const full: Bookmark = {
    ...bm,
    // crypto.randomUUID() is available in all modern browsers & Next.js dev.
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    createdAt: new Date().toISOString(),
  };
  const existing = read(bm.bookId);
  const deduped = existing.filter(
    (b) => !(b.chapterNum === bm.chapterNum && b.segmentIndex === bm.segmentIndex),
  );
  write(bm.bookId, [full, ...deduped]);
  return full;
}

export function removeBookmark(bookId: string, bookmarkId: string): void {
  write(
    bookId,
    read(bookId).filter((b) => b.id !== bookmarkId),
  );
}

// Used by the reader to render a small filled bookmark glyph next to
// segments that are already saved. Quick scan, fine for in-memory.
export function hasBookmarkAt(
  bookId: string,
  chapterNum: number,
  segmentIndex: number,
): boolean {
  return read(bookId).some(
    (b) => b.chapterNum === chapterNum && b.segmentIndex === segmentIndex,
  );
}
