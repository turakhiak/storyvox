import { create } from "zustand";
import type { Book, Chapter, Character, Screenplay } from "@/lib/api";

interface LibraryState {
  books: Book[];
  setBooks: (books: Book[]) => void;
  addBook: (book: Book) => void;
  removeBook: (id: string) => void;

  // Current book context
  currentBook: Book | null;
  currentChapters: Chapter[];
  currentCharacters: Character[];
  setCurrentBook: (book: Book | null) => void;
  setCurrentChapters: (chapters: Chapter[]) => void;
  setCurrentCharacters: (characters: Character[]) => void;

  // UI state
  theme: "light" | "dark" | "sepia";
  setTheme: (theme: "light" | "dark" | "sepia") => void;
  readerFontSize: number;
  setReaderFontSize: (size: number) => void;

  // Processing state
  processingChapterId: string | null;
  processingRound: number;
  processingScores: Record<string, number> | null;
  setProcessing: (chapterId: string | null, round?: number, scores?: Record<string, number> | null) => void;
}

export const useLibraryStore = create<LibraryState>((set) => ({
  books: [],
  setBooks: (books) => set({ books }),
  addBook: (book) => set((s) => ({ books: [book, ...s.books] })),
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

  processingChapterId: null,
  processingRound: 0,
  processingScores: null,
  setProcessing: (chapterId, round = 0, scores = null) =>
    set({ processingChapterId: chapterId, processingRound: round, processingScores: scores }),
}));
