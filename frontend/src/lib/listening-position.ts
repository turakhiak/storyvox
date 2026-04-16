// Per-book "where did I stop listening" state. We already have a
// book-level chapter bookmark (listen_bookmark) that tells the library
// "Continue" button which chapter to jump to, but that's only chapter-
// precision — if you paused halfway through a chapter it rewinds you
// to the start. This module fills in the sub-chapter precision.
//
// Kept in localStorage, keyed per book. A single position per book:
// opening a different chapter and playing overwrites it, which is the
// expected UX ("resume = last spot I actually listened to, period").
//
// We store segmentIndex only, not currentTime — gTTS segments are
// short (seconds), restarting the current segment when resuming is
// fine and avoids the complexity of preserving audio-element state
// across component unmounts.

export interface ListeningPosition {
  bookId: string;
  chapterNum: number;
  segmentIndex: number;
  updatedAt: string;
}

const KEY = (bookId: string) => `storyvox:listening:${bookId}`;

export function getListeningPosition(bookId: string): ListeningPosition | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY(bookId));
    return raw ? (JSON.parse(raw) as ListeningPosition) : null;
  } catch {
    return null;
  }
}

export function saveListeningPosition(
  bookId: string,
  chapterNum: number,
  segmentIndex: number,
): void {
  if (typeof window === "undefined") return;
  try {
    const pos: ListeningPosition = {
      bookId,
      chapterNum,
      segmentIndex,
      updatedAt: new Date().toISOString(),
    };
    window.localStorage.setItem(KEY(bookId), JSON.stringify(pos));
  } catch {
    // Silently swallow — quota, private mode, etc. Losing resume is
    // annoying but not broken; better than crashing the reader.
  }
}

export function clearListeningPosition(bookId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY(bookId));
  } catch {}
}
