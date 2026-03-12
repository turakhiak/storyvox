"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, ChevronLeft, ChevronRight, Settings, Moon, Sun,
  Minus, Plus, BookOpen, Loader2, Type
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getBook, getChapter, getChapters } from "@/lib/api";
import type { Book, Chapter } from "@/lib/api";
import { useLibraryStore } from "@/store/library";

export default function ReaderPage() {
  const { id, chapter: chapterNum } = useParams<{ id: string; chapter: string }>();
  const router = useRouter();
  const { readerFontSize, setReaderFontSize, theme, setTheme } = useLibraryStore();
  const [book, setBook] = useState<Book | null>(null);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [totalChapters, setTotalChapters] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);

  const num = parseInt(chapterNum, 10);

  useEffect(() => {
    if (!id || !num) return;
    setLoading(true);
    Promise.all([
      getBook(id).then(setBook),
      getChapter(id, num).then(setChapter),
      getChapters(id).then((chs) => setTotalChapters(chs.length)),
    ])
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id, num]);

  const goToChapter = (n: number) => {
    if (n >= 1 && n <= totalChapters) {
      router.push(`/book/${id}/read/${n}`);
    }
  };

  // Keyboard nav
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goToChapter(num - 1);
      if (e.key === "ArrowRight") goToChapter(num + 1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [num, totalChapters]);

  const bgClass =
    theme === "sepia"
      ? "bg-[#F5E6C8] text-[#5C4033]"
      : theme === "light"
      ? "bg-white text-ink-900"
      : "bg-surface-dark text-ink-200";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-dark">
        <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
      </div>
    );
  }

  return (
    <div className={cn("min-h-screen transition-colors duration-300", bgClass)}>
      {/* Reader nav */}
      <nav className="sticky top-0 z-40 backdrop-blur-xl bg-inherit/80 border-b border-ink-200/10 dark:border-ink-800/20">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => router.push(`/book/${id}`)}
            className="flex items-center gap-2 text-sm opacity-60 hover:opacity-100 transition-opacity"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-ui hidden sm:inline">{book?.title}</span>
          </button>

          <span className="font-ui text-sm opacity-50">
            {chapter?.title || `Chapter ${num}`}
          </span>

          <button
            onClick={() => setShowSettings(!showSettings)}
            className="w-8 h-8 rounded-lg flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>

        {/* Settings panel */}
        {showSettings && (
          <div className="border-t border-ink-200/10 dark:border-ink-800/20 animate-slide-up">
            <div className="max-w-4xl mx-auto px-6 py-4 flex flex-wrap items-center gap-6">
              {/* Font size */}
              <div className="flex items-center gap-3">
                <Type className="w-4 h-4 opacity-50" />
                <button
                  onClick={() => setReaderFontSize(Math.max(14, readerFontSize - 2))}
                  className="w-8 h-8 rounded-lg bg-ink-100/10 flex items-center justify-center hover:bg-ink-100/20"
                >
                  <Minus className="w-3 h-3" />
                </button>
                <span className="font-mono text-sm w-8 text-center">{readerFontSize}</span>
                <button
                  onClick={() => setReaderFontSize(Math.min(28, readerFontSize + 2))}
                  className="w-8 h-8 rounded-lg bg-ink-100/10 flex items-center justify-center hover:bg-ink-100/20"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>

              {/* Theme */}
              <div className="flex items-center gap-2">
                {(["dark", "light", "sepia"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t)}
                    className={cn(
                      "w-8 h-8 rounded-lg border-2 transition-all",
                      t === "dark" && "bg-[#0D0B09] border-ink-700",
                      t === "light" && "bg-white border-ink-300",
                      t === "sepia" && "bg-[#F5E6C8] border-[#C4A775]",
                      theme === t && "ring-2 ring-amber-warm ring-offset-2 ring-offset-transparent"
                    )}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Chapter content */}
      <main className="max-w-4xl mx-auto px-6 py-12">
        {/* Chapter header */}
        <div className="mb-12 text-center">
          <span className="font-ui text-xs uppercase tracking-[0.2em] opacity-40">
            Chapter {num}
          </span>
          <h1 className="font-display text-3xl font-bold mt-2">
            {chapter?.title || `Chapter ${num}`}
          </h1>
        </div>

        {/* Text */}
        <div
          className="reader-content mx-auto"
          style={{ fontSize: `${readerFontSize}px` }}
        >
          {chapter?.raw_text?.split("\n\n").map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </div>

        {/* Chapter navigation */}
        <div className="flex items-center justify-between mt-16 pt-8 border-t border-ink-200/10">
          <button
            onClick={() => goToChapter(num - 1)}
            disabled={num <= 1}
            className={cn(
              "flex items-center gap-2 font-ui text-sm transition-opacity",
              num <= 1 ? "opacity-20 cursor-not-allowed" : "opacity-60 hover:opacity-100"
            )}
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>

          <span className="font-mono text-xs opacity-30">
            {num} / {totalChapters}
          </span>

          <button
            onClick={() => goToChapter(num + 1)}
            disabled={num >= totalChapters}
            className={cn(
              "flex items-center gap-2 font-ui text-sm transition-opacity",
              num >= totalChapters ? "opacity-20 cursor-not-allowed" : "opacity-60 hover:opacity-100"
            )}
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </main>
    </div>
  );
}
