"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, ChevronLeft, ChevronRight, Settings,
  Minus, Plus, Loader2, Type, Gauge
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getBook, getChapter, getChapters, updateBookmark } from "@/lib/api";
import type { Book, Chapter } from "@/lib/api";
import { useLibraryStore, READER_FONTS, type ReaderFontId } from "@/store/library";

export default function ReaderPage() {
  const { id, chapter: chapterNum } = useParams<{ id: string; chapter: string }>();
  const router = useRouter();
  const {
    readerFontSize, setReaderFontSize,
    readerFontFamily, setReaderFontFamily,
    readerLineHeight, setReaderLineHeight,
    ttsSpeed, setTtsSpeed,
    theme, setTheme,
  } = useLibraryStore();
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

  // Update the listening bookmark when the user lands on a chapter, so the
  // library "Continue" button knows where they are. Best-effort — failure
  // shouldn't break reading. We bookmark `num - 1` because the bookmark
  // semantically means "last chapter you listened through" — opening ch. 5
  // implies you finished ch. 4.
  useEffect(() => {
    if (!id || !num || num < 2) return;
    updateBookmark(id, num - 1).catch(() => {});
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

  const fontStack = READER_FONTS[readerFontFamily]?.stack || READER_FONTS.serif.stack;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-dark">
        <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
      </div>
    );
  }

  return (
    <div className={cn("min-h-screen transition-colors duration-300", bgClass)}>
      {/* Reader nav — slim on mobile, full title on sm+ */}
      <nav className="sticky top-0 z-40 backdrop-blur-xl bg-inherit/80 border-b border-ink-200/10 dark:border-ink-800/20">
        <div className="max-w-4xl mx-auto px-3 sm:px-6 h-14 flex items-center justify-between gap-2">
          <button
            onClick={() => router.push(`/book/${id}`)}
            className="flex items-center gap-1.5 sm:gap-2 text-sm opacity-60 hover:opacity-100 transition-opacity min-h-[44px] px-2"
            aria-label="Back to book"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="font-ui hidden sm:inline truncate max-w-[200px]">{book?.title}</span>
          </button>

          <span className="font-ui text-xs sm:text-sm opacity-50 truncate">
            {chapter?.title || `Chapter ${num}`}
          </span>

          <button
            onClick={() => setShowSettings(!showSettings)}
            className="w-11 h-11 rounded-lg flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity flex-shrink-0"
            aria-label="Reader settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>

        {/* Settings panel — ereader-style toolbar.
            Wraps cleanly on mobile, stays one row on desktop. */}
        {showSettings && (
          <div className="border-t border-ink-200/10 dark:border-ink-800/20 animate-slide-up">
            <div className="max-w-4xl mx-auto px-3 sm:px-6 py-3 sm:py-4 flex flex-wrap items-center gap-3 sm:gap-6">
              {/* Font size */}
              <div className="flex items-center gap-2 sm:gap-3">
                <Type className="w-4 h-4 opacity-50" aria-label="Font size" />
                <button
                  onClick={() => setReaderFontSize(Math.max(14, readerFontSize - 2))}
                  className="w-9 h-9 rounded-lg bg-ink-100/10 flex items-center justify-center hover:bg-ink-100/20"
                  aria-label="Smaller text"
                >
                  <Minus className="w-3 h-3" />
                </button>
                <span className="font-mono text-sm w-7 text-center">{readerFontSize}</span>
                <button
                  onClick={() => setReaderFontSize(Math.min(28, readerFontSize + 2))}
                  className="w-9 h-9 rounded-lg bg-ink-100/10 flex items-center justify-center hover:bg-ink-100/20"
                  aria-label="Larger text"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>

              {/* Font family */}
              <div className="flex items-center gap-1">
                {(Object.keys(READER_FONTS) as ReaderFontId[]).map((fid) => (
                  <button
                    key={fid}
                    onClick={() => setReaderFontFamily(fid)}
                    className={cn(
                      "px-2.5 sm:px-3 h-9 rounded-lg text-xs transition-colors",
                      readerFontFamily === fid
                        ? "bg-amber-warm/20 text-amber-warm border border-amber-warm/40"
                        : "bg-ink-100/10 hover:bg-ink-100/20 border border-transparent"
                    )}
                    style={{ fontFamily: READER_FONTS[fid].stack }}
                    title={READER_FONTS[fid].label}
                  >
                    Aa
                  </button>
                ))}
              </div>

              {/* Line height */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider opacity-50">Spacing</span>
                <select
                  value={readerLineHeight}
                  onChange={(e) => setReaderLineHeight(parseFloat(e.target.value))}
                  className="bg-ink-100/10 hover:bg-ink-100/20 border border-ink-200/10 rounded-lg px-2 h-9 text-xs font-mono cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-warm/40"
                >
                  <option value={1.4}>1.4</option>
                  <option value={1.5}>1.5</option>
                  <option value={1.7}>1.7</option>
                  <option value={1.9}>1.9</option>
                  <option value={2.0}>2.0</option>
                </select>
              </div>

              {/* TTS speed — applied to <audio>.playbackRate everywhere
                  audio plays (Audio Player tab + Screenplay tab) so changing
                  it here actually carries through to listening. */}
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 opacity-50" aria-label="TTS speed" />
                <select
                  value={ttsSpeed}
                  onChange={(e) => setTtsSpeed(parseFloat(e.target.value))}
                  className="bg-ink-100/10 hover:bg-ink-100/20 border border-ink-200/10 rounded-lg px-2 h-9 text-xs font-mono cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-warm/40"
                  title="Audio playback speed (used in Audio Player)"
                >
                  <option value={0.75}>0.75×</option>
                  <option value={1.0}>1.0×</option>
                  <option value={1.25}>1.25×</option>
                  <option value={1.5}>1.5×</option>
                  <option value={1.75}>1.75×</option>
                  <option value={2.0}>2.0×</option>
                </select>
              </div>

              {/* Theme */}
              <div className="flex items-center gap-2 ml-auto">
                {(["dark", "light", "sepia"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t)}
                    aria-label={`${t} theme`}
                    className={cn(
                      "w-9 h-9 rounded-lg border-2 transition-all",
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
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {/* Chapter header */}
        <div className="mb-8 sm:mb-12 text-center">
          <span className="font-ui text-xs uppercase tracking-[0.2em] opacity-40">
            Chapter {num}
          </span>
          <h1 className="font-display text-2xl sm:text-3xl font-bold mt-2">
            {chapter?.title || `Chapter ${num}`}
          </h1>
        </div>

        {/* Text — font/size/spacing/family all driven by user prefs. */}
        <div
          className="reader-content mx-auto"
          style={{
            fontSize: `${readerFontSize}px`,
            fontFamily: fontStack,
            lineHeight: readerLineHeight,
          }}
        >
          {chapter?.raw_text?.split("\n\n").map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </div>

        {/* Chapter navigation — bigger touch targets on mobile */}
        <div className="flex items-center justify-between mt-12 sm:mt-16 pt-6 sm:pt-8 border-t border-ink-200/10">
          <button
            onClick={() => goToChapter(num - 1)}
            disabled={num <= 1}
            className={cn(
              "flex items-center gap-2 font-ui text-sm transition-opacity min-h-[44px] px-3",
              num <= 1 ? "opacity-20 cursor-not-allowed" : "opacity-60 hover:opacity-100"
            )}
          >
            <ChevronLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Previous</span>
            <span className="sm:hidden">Prev</span>
          </button>

          <span className="font-mono text-xs opacity-30">
            {num} / {totalChapters}
          </span>

          <button
            onClick={() => goToChapter(num + 1)}
            disabled={num >= totalChapters}
            className={cn(
              "flex items-center gap-2 font-ui text-sm transition-opacity min-h-[44px] px-3",
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
