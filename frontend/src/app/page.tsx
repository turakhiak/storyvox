"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen, Upload, Search, Trash2, Clock, FileText,
  Mic, ChevronRight, Sparkles, Radio, Volume2, RefreshCw, Loader2
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getBooks, uploadBook, deleteBook, refreshBookCover, getCoverUrl,
  formatWordCount, formatDuration, pingServer,
} from "@/lib/api";
import type { Book } from "@/lib/api";
import { useLibraryStore } from "@/store/library";

export default function HomePage() {
  const router = useRouter();
  const { books, setBooks, addBook, updateBook, removeBook } = useLibraryStore();
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track which card is currently re-fetching its cover (id → in-flight)
  const [refreshingCoverId, setRefreshingCoverId] = useState<string | null>(null);

  useEffect(() => {
    // Ping the server on load so Render wakes up before the user tries to do anything
    pingServer().catch(() => {});
    getBooks()
      .then(setBooks)
      .catch((e) => console.error("Failed to load books:", e));
  }, [setBooks]);

  const handleUpload = useCallback(async (file: File) => {
    const name = file.name.toLowerCase();
    if (!name.endsWith(".epub") && !name.endsWith(".pdf")) {
      setError("Only .epub and .pdf files are supported");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const book = await uploadBook(file);
      addBook(book);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [addBook]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    },
    [handleUpload]
  );

  const handleDelete = async (e: React.MouseEvent, bookId: string) => {
    e.stopPropagation();
    if (!confirm("Delete this book and all its data?")) return;
    try {
      await deleteBook(bookId);
      removeBook(bookId);
    } catch (e: any) {
      setError(e.message);
    }
  };

  // Re-fetch a book's cover. Tries the local epub/pdf first, then falls back
  // to OpenLibrary on the server. Cache-busts the <img> by mutating the URL
  // we hand to the store — the new cover_url is a fresh /static/covers/... path.
  const handleRefreshCover = async (e: React.MouseEvent, bookId: string) => {
    e.stopPropagation();
    setRefreshingCoverId(bookId);
    setError(null);
    try {
      const updated = await refreshBookCover(bookId);
      updateBook(updated);
    } catch (err: any) {
      setError(err.message || "Could not refresh cover");
    } finally {
      setRefreshingCoverId(null);
    }
  };

  const filteredBooks = books.filter(
    (b) =>
      b.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.author.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen">
      {/* Hero Header — mobile-first: smaller logo, condensed padding,
          upload button shrinks to icon-only on the narrowest screens. */}
      <header className="relative overflow-hidden border-b border-ink-200/20 dark:border-ink-800/40">
        <div className="absolute inset-0 bg-gradient-to-br from-amber-warm/5 via-transparent to-stage-purple/5" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 sm:gap-4 min-w-0">
              <div className="relative flex-shrink-0">
                <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-2xl bg-gradient-to-br from-amber-warm to-amber-warm/70 flex items-center justify-center shadow-lg shadow-amber-warm/20">
                  <Radio className="w-5 h-5 sm:w-7 sm:h-7 text-ink-950" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 rounded-full bg-stage-green flex items-center justify-center">
                  <Volume2 className="w-2.5 h-2.5 sm:w-3 sm:h-3 text-white" />
                </div>
              </div>
              <div className="min-w-0">
                <h1 className="font-display text-xl sm:text-3xl font-bold tracking-tight text-ink-950 dark:text-ink-50 truncate">
                  StoryVox
                </h1>
                <p className="text-ink-500 dark:text-ink-400 font-ui text-xs sm:text-sm mt-0.5 truncate">
                  Turn books into radio plays
                </p>
              </div>
            </div>

            {/* Upload button — icon-only on mobile so it fits next to the logo. */}
            <label className="btn-primary flex items-center gap-2 cursor-pointer flex-shrink-0 min-h-[44px]" title="Upload book">
              <Upload className="w-4 h-4" />
              <span className="hidden sm:inline">Upload Book</span>
              <input
                type="file"
                accept=".epub,.pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleUpload(file);
                }}
                disabled={uploading}
              />
            </label>
          </div>

          {/* Search */}
          {books.length > 0 && (
            <div className="mt-5 sm:mt-8 max-w-md">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
                <input
                  type="text"
                  placeholder="Search your library..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-11 pr-4 py-3 bg-white/50 dark:bg-white/5 border border-ink-200/30 dark:border-ink-700/30 rounded-xl font-ui text-sm focus:outline-none focus:ring-2 focus:ring-amber-warm/40 placeholder:text-ink-400 min-h-[44px]"
                />
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 mt-4">
          <div className="bg-stage-red/10 border border-stage-red/20 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
            <span className="text-stage-red text-sm font-ui">{error}</span>
            <button onClick={() => setError(null)} className="text-stage-red/60 hover:text-stage-red text-sm flex-shrink-0">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Upload progress */}
      {uploading && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 mt-4">
          <div className="glass-card px-6 py-4 flex items-center gap-4">
            <div className="w-8 h-8 rounded-full border-2 border-amber-warm border-t-transparent animate-spin" />
            <div>
              <p className="font-ui font-medium text-ink-800 dark:text-ink-200">Uploading & parsing book...</p>
              <p className="font-ui text-sm text-ink-500">Extracting chapters, metadata, and cover art</p>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {books.length === 0 && !uploading ? (
          /* Empty state — tighter padding on mobile */
          <div
            className={cn(
              "flex flex-col items-center justify-center py-12 sm:py-24 px-4 rounded-3xl border-2 border-dashed transition-all duration-300",
              dragOver
                ? "border-amber-warm bg-amber-warm/5 scale-[1.01]"
                : "border-ink-200/40 dark:border-ink-700/40"
            )}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-3xl bg-gradient-to-br from-ink-100 to-ink-200 dark:from-ink-800 dark:to-ink-900 flex items-center justify-center mb-5 sm:mb-6">
              <BookOpen className="w-8 h-8 sm:w-10 sm:h-10 text-ink-400 dark:text-ink-500" />
            </div>
            <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink-800 dark:text-ink-200 mb-2 text-center">
              Your library is empty
            </h2>
            <p className="text-ink-500 dark:text-ink-400 font-ui text-center text-sm sm:text-base max-w-md mb-6 sm:mb-8">
              Drop an epub or PDF file here, or click upload to get started.
              StoryVox will extract the chapters, detect characters,
              and help you create a radio play.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 text-xs sm:text-sm text-ink-400 dark:text-ink-500 font-ui">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-warm" />
                <span>AI Screenplay</span>
              </div>
              <div className="flex items-center gap-2">
                <Mic className="w-4 h-4 text-stage-green" />
                <span>Multi-Voice TTS</span>
              </div>
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-stage-purple" />
                <span>Radio Play</span>
              </div>
            </div>
          </div>
        ) : (
          /* Book grid — 2 columns on the smallest screens for density */
          <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6">
            {filteredBooks.map((book, i) => (
              <BookCard
                key={book.id}
                book={book}
                index={i}
                onClick={() => router.push(`/book/${book.id}`)}
                onDelete={(e) => handleDelete(e, book.id)}
                onRefreshCover={(e) => handleRefreshCover(e, book.id)}
                refreshingCover={refreshingCoverId === book.id}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function BookCard({
  book,
  index,
  onClick,
  onDelete,
  onRefreshCover,
  refreshingCover,
}: {
  book: Book;
  index: number;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
  onRefreshCover: (e: React.MouseEvent) => void;
  refreshingCover: boolean;
}) {
  const coverUrl = getCoverUrl(book.cover_url);
  const statusColor =
    book.status === "ready"
      ? "bg-stage-green"
      : book.status === "processing"
      ? "bg-amber-warm animate-pulse-soft"
      : "bg-ink-400";

  return (
    <div
      onClick={onClick}
      className="group glass-card overflow-hidden cursor-pointer hover:shadow-xl hover:shadow-ink-950/10 dark:hover:shadow-ink-950/40 hover:-translate-y-1 transition-all duration-300 animate-slide-up"
      style={{ animationDelay: `${index * 60}ms`, animationFillMode: "both" }}
    >
      {/* Cover */}
      <div className="aspect-[2/3] relative overflow-hidden bg-gradient-to-br from-ink-200 to-ink-300 dark:from-ink-800 dark:to-ink-900">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt={book.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <BookOpen className="w-12 h-12 sm:w-16 sm:h-16 text-ink-400/30 dark:text-ink-600/30" />
          </div>
        )}

        {/* Gradient overlay at bottom */}
        <div className="absolute inset-x-0 bottom-0 h-20 sm:h-24 bg-gradient-to-t from-black/60 to-transparent" />

        {/* Status dot */}
        <div className="absolute top-2 right-2 sm:top-3 sm:right-3">
          <div className={cn("w-2.5 h-2.5 rounded-full", statusColor)} />
        </div>

        {/* Delete button — always-visible on touch devices (no hover), fades on desktop */}
        <button
          onClick={onDelete}
          className="absolute top-2 left-2 sm:top-3 sm:left-3 w-9 h-9 sm:w-8 sm:h-8 rounded-lg bg-black/40 backdrop-blur-sm flex items-center justify-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 hover:bg-stage-red/80 transition-all duration-200"
          aria-label="Delete book"
        >
          <Trash2 className="w-3.5 h-3.5 text-white" />
        </button>

        {/* Quick stats at bottom of cover */}
        <div className="absolute bottom-2 left-2 right-2 sm:bottom-3 sm:left-3 sm:right-3 flex items-center justify-between text-white/80 text-[10px] sm:text-xs font-ui">
          <span className="flex items-center gap-1">
            <FileText className="w-3 h-3" />
            {book.total_chapters}<span className="hidden sm:inline">&nbsp;chapters</span>
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(book.total_words)}
          </span>
        </div>
      </div>

      {/* Info — tighter on mobile */}
      <div className="p-3 sm:p-4">
        <h3 className="font-display font-semibold text-sm sm:text-base text-ink-900 dark:text-ink-100 line-clamp-1 group-hover:text-amber-warm transition-colors">
          {book.title}
        </h3>
        <p className="text-ink-500 dark:text-ink-400 text-xs sm:text-sm font-ui mt-0.5 sm:mt-1 line-clamp-1">
          {book.author}
        </p>
        <div className="flex items-center justify-between mt-2 sm:mt-3 pt-2 sm:pt-3 border-t border-ink-100 dark:border-ink-800/50">
          <span className="text-[10px] sm:text-xs font-ui text-ink-400">
            {formatWordCount(book.total_words)}
          </span>
          <ChevronRight className="w-4 h-4 text-ink-300 dark:text-ink-600 group-hover:text-amber-warm group-hover:translate-x-0.5 transition-all" />
        </div>
        {/* Refresh-cover link.
            Stays subtle (small + muted) so it doesn't compete with Delete.
            Stops propagation so it doesn't navigate into the book. */}
        <button
          onClick={onRefreshCover}
          disabled={refreshingCover}
          className="mt-1.5 sm:mt-2 -mx-1 px-1 py-1 flex items-center gap-1.5 text-[10px] sm:text-[11px] font-ui text-ink-400 hover:text-amber-warm disabled:opacity-50 transition-colors min-h-[32px]"
          title="Re-fetch cover from the book file or OpenLibrary"
        >
          {refreshingCover ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <RefreshCw className="w-3 h-3" />
          )}
          {refreshingCover ? "Refreshing..." : "Refresh cover"}
        </button>
      </div>
    </div>
  );
}
