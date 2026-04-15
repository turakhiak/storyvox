import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Book, Chapter, Character, Screenplay } from "@/lib/api";

// Font families available in the reader toolbar. Keyed by id, value is the
// CSS font-family stack — sticking to system + serif/sans/mono pairs so we
// don't have to ship custom fonts and slow first paint.
export const READER_FONTS: Record<string, { label: string; stack: string }> = {
  serif: { label: "Serif", stack: "ui-serif, Georgia, Cambria, 'Times New Roman', serif" },
  sans:  { label: "Sans",  stack: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif" },
  mono:  { label: "Mono",  stack: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" },
  display: { label: "Display", stack: "'Crimson Pro', Georgia, ui-serif, serif" },
};

export type ReaderFontId = keyof typeof READER_FONTS;

interface LibraryState {
  books: Book[];
  setBooks: (books: Book[]) => void;
  addBook: (book: Book) => void;
  // Replaces the matching book in-place. Used by the refresh-cover link
  // and anywhere else we update a single book without re-fetching the list.
  updateBook: (book: Book) => void;
  removeBook: (id: string) => void;

  // Current book context
  currentBook: Book | null;
  currentChapters: Chapter[];
  currentCharacters: Character[];
  setCurrentBook: (book: Book | null) => void;
  setCurrentChapters: (chapters: Chapter[]) => void;
  setCurrentCharacters: (characters: Character[]) => void;

  // === Reader UI prefs (persisted) ===
  theme: "light" | "dark" | "sepia";
  setTheme: (theme: "light" | "dark" | "sepia") => void;
  readerFontSize: number;            // base text px (14..28)
  setReaderFontSize: (size: number) => void;
  readerFontFamily: ReaderFontId;
  setReaderFontFamily: (id: ReaderFontId) => void;
  readerLineHeight: number;          // 1.4 .. 2.0
  setReaderLineHeight: (h: number) => void;
  ttsSpeed: number;                  // 0.5 .. 2.0 — applied as audio.playbackRate
  setTtsSpeed: (s: number) => void;

  // Processing state (transient — not persisted)
  processingChapterId: string | null;
  processingRound: number;
  processingScores: Record<string, number> | null;
  setProcessing: (chapterId: string | null, round?: number, scores?: Record<string, number> | null) => void;
}

export const useLibraryStore = create<LibraryState>()(
  persist(
    (set) => ({
      books: [],
      setBooks: (books) => set({ books }),
      addBook: (book) => set((s) => ({ books: [book, ...s.books] })),
      updateBook: (book) =>
        set((s) => ({ books: s.books.map((b) => (b.id === book.id ? book : b)) })),
      removeBook: (id) => set((s) => ({ books: s.books.filter((b) => b.id !== id) })),

      currentBook: null,
      currentChapters: [],
      currentCharacters: [],
      setCurrentBook: (book) => set({ currentBook: book }),
      setCurrentChapters: (chapters) => set({ currentChapters: chapters }),
      setCurrentCharacters: (characters) => set({ currentCharacters: characters }),

      theme: "dark",
      setTheme: (theme) => set({ theme }),
      readerFontSize: 18,
      setReaderFontSize: (size) => set({ readerFontSize: size }),
      readerFontFamily: "serif",
      setReaderFontFamily: (id) => set({ readerFontFamily: id }),
      readerLineHeight: 1.7,
      setReaderLineHeight: (h) => set({ readerLineHeight: h }),
      ttsSpeed: 1.0,
      setTtsSpeed: (s) => set({ ttsSpeed: s }),

      processingChapterId: null,
      processingRound: 0,
      processingScores: null,
      setProcessing: (chapterId, round = 0, scores = null) =>
        set({ processingChapterId: chapterId, processingRound: round, processingScores: scores }),
    }),
    {
      // Only persist user UI prefs — never the books list (always re-fetched
      // from the server, would otherwise show stale covers/status).
      name: "storyvox-reader-prefs",
      partialize: (s) => ({
        theme: s.theme,
        readerFontSize: s.readerFontSize,
        readerFontFamily: s.readerFontFamily,
        readerLineHeight: s.readerLineHeight,
        ttsSpeed: s.ttsSpeed,
      }),
    }
  )
);
