"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, BookOpen, Users, Sparkles, Play, FileText,
  ChevronRight, Loader2, Mic, Brain, Radio, Clock,
  RefreshCw, CheckCircle2, AlertCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getBook, getChapters, getCharacters, detectCharacters,
  getCoverUrl, formatWordCount, formatDuration,
} from "@/lib/api";
import type { Book, Chapter, Character } from "@/lib/api";

type Tab = "chapters" | "characters" | "screenplay";

export default function BookPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("chapters");
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      getBook(id).then(setBook),
      getChapters(id).then(setChapters),
      getCharacters(id).then(setCharacters).catch(() => []),
    ]).catch((e) => setError(e.message));
  }, [id]);

  const handleDetectCharacters = async () => {
    if (!id) return;
    setDetecting(true);
    setError(null);
    try {
      const chars = await detectCharacters(id);
      setCharacters(chars);
      setActiveTab("characters");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDetecting(false);
    }
  };

  if (!book) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
      </div>
    );
  }

  const coverUrl = getCoverUrl(book.cover_url);

  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <nav className="border-b border-ink-200/20 dark:border-ink-800/40 bg-surface-light/80 dark:bg-surface-dark/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-4">
          <button onClick={() => router.push("/")} className="btn-ghost flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" />
            Library
          </button>
          <div className="h-6 w-px bg-ink-200 dark:bg-ink-800" />
          <h1 className="font-display font-semibold text-ink-900 dark:text-ink-100 truncate">
            {book.title}
          </h1>
        </div>
      </nav>

      {error && (
        <div className="max-w-7xl mx-auto px-6 mt-4">
          <div className="bg-stage-red/10 border border-stage-red/20 rounded-xl px-4 py-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-stage-red flex-shrink-0" />
            <span className="text-stage-red text-sm font-ui">{error}</span>
          </div>
        </div>
      )}

      {/* Book hero */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex gap-8 items-start">
          {/* Cover */}
          <div className="hidden md:block w-48 flex-shrink-0">
            <div className="aspect-[2/3] rounded-2xl overflow-hidden shadow-2xl shadow-ink-950/20 dark:shadow-ink-950/50">
              {coverUrl ? (
                <img src={coverUrl} alt={book.title} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-ink-200 to-ink-300 dark:from-ink-800 dark:to-ink-900 flex items-center justify-center">
                  <BookOpen className="w-12 h-12 text-ink-400/40" />
                </div>
              )}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h2 className="font-display text-4xl font-bold text-ink-950 dark:text-ink-50 leading-tight">
              {book.title}
            </h2>
            <p className="font-ui text-lg text-ink-500 dark:text-ink-400 mt-2">
              by {book.author}
            </p>

            {book.description && (
              <p className="font-body text-ink-600 dark:text-ink-400 mt-4 line-clamp-3 max-w-2xl leading-relaxed">
                {book.description}
              </p>
            )}

            {/* Stats */}
            <div className="flex flex-wrap gap-6 mt-6">
              <Stat icon={<FileText className="w-4 h-4" />} label="Chapters" value={book.total_chapters} />
              <Stat icon={<BookOpen className="w-4 h-4" />} label="Words" value={formatWordCount(book.total_words)} />
              <Stat icon={<Clock className="w-4 h-4" />} label="Est. Listen" value={formatDuration(book.total_words)} />
              <Stat icon={<Users className="w-4 h-4" />} label="Characters" value={characters.length || "—"} />
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-3 mt-8">
              <button onClick={handleDetectCharacters} className="btn-primary flex items-center gap-2" disabled={detecting}>
                {detecting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                {detecting ? "Detecting..." : characters.length > 0 ? "Re-detect Characters" : "Detect Characters"}
              </button>
              {chapters.length > 0 && (
                <button
                  onClick={() => router.push(`/book/${id}/read/1`)}
                  className="btn-ghost flex items-center gap-2"
                >
                  <BookOpen className="w-4 h-4" />
                  Start Reading
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex gap-1 border-b border-ink-200/30 dark:border-ink-800/30">
          {(["chapters", "characters", "screenplay"] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-5 py-3 font-ui text-sm font-medium capitalize transition-all duration-200 border-b-2 -mb-px",
                activeTab === tab
                  ? "border-amber-warm text-amber-warm"
                  : "border-transparent text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200"
              )}
            >
              {tab === "chapters" && <FileText className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "characters" && <Users className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "screenplay" && <Radio className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === "chapters" && (
          <ChaptersTab chapters={chapters} bookId={book.id} />
        )}
        {activeTab === "characters" && (
          <CharactersTab characters={characters} onDetect={handleDetectCharacters} detecting={detecting} />
        )}
        {activeTab === "screenplay" && (
          <ScreenplayTab chapters={chapters} bookId={book.id} hasCharacters={characters.length > 0} />
        )}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-2 text-ink-500 dark:text-ink-400">
      <span className="text-ink-400 dark:text-ink-500">{icon}</span>
      <span className="font-ui text-sm">
        <span className="font-semibold text-ink-800 dark:text-ink-200">{value}</span>
        {" "}{label}
      </span>
    </div>
  );
}

function ChaptersTab({ chapters, bookId }: { chapters: Chapter[]; bookId: string }) {
  const router = useRouter();
  return (
    <div className="space-y-2">
      {chapters.map((ch, i) => (
        <button
          key={ch.id}
          onClick={() => router.push(`/book/${bookId}/read/${ch.number}`)}
          className="w-full glass-card px-5 py-4 flex items-center justify-between group hover:shadow-md transition-all duration-200 animate-slide-up"
          style={{ animationDelay: `${i * 30}ms`, animationFillMode: "both" }}
        >
          <div className="flex items-center gap-4">
            <span className="w-8 h-8 rounded-lg bg-ink-100 dark:bg-ink-800 flex items-center justify-center font-mono text-sm text-ink-500 dark:text-ink-400">
              {ch.number}
            </span>
            <div className="text-left">
              <p className="font-ui font-medium text-ink-800 dark:text-ink-200 group-hover:text-amber-warm transition-colors">
                {ch.title || `Chapter ${ch.number}`}
              </p>
              <p className="font-ui text-xs text-ink-400 mt-0.5">
                {formatWordCount(ch.word_count)} · {formatDuration(ch.word_count)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={ch.status} />
            <ChevronRight className="w-4 h-4 text-ink-300 group-hover:text-amber-warm group-hover:translate-x-0.5 transition-all" />
          </div>
        </button>
      ))}
    </div>
  );
}

function CharactersTab({
  characters,
  onDetect,
  detecting,
}: {
  characters: Character[];
  onDetect: () => void;
  detecting: boolean;
}) {
  if (characters.length === 0) {
    return (
      <div className="text-center py-16">
        <Users className="w-12 h-12 text-ink-300 dark:text-ink-600 mx-auto mb-4" />
        <h3 className="font-display text-xl font-semibold text-ink-700 dark:text-ink-300 mb-2">
          No characters detected yet
        </h3>
        <p className="font-ui text-ink-500 dark:text-ink-400 mb-6 max-w-md mx-auto">
          Use AI to scan the book and identify all speaking characters with their traits, speech patterns, and relationships.
        </p>
        <button onClick={onDetect} className="btn-primary" disabled={detecting}>
          {detecting ? <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> : <Brain className="w-4 h-4 inline mr-2" />}
          Detect Characters
        </button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {characters.map((char, i) => (
        <div
          key={char.id}
          className="glass-card p-5 animate-slide-up"
          style={{ animationDelay: `${i * 50}ms`, animationFillMode: "both" }}
        >
          <div className="flex items-start gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center font-display font-bold text-white text-sm flex-shrink-0"
              style={{ backgroundColor: char.color_hex || "#6B9080" }}
            >
              {char.name.charAt(0)}
            </div>
            <div className="min-w-0">
              <h4 className="font-display font-semibold text-ink-900 dark:text-ink-100">
                {char.name}
              </h4>
              <div className="flex flex-wrap gap-1 mt-1">
                <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-400 capitalize">
                  {char.frequency}
                </span>
                {char.gender && (
                  <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-400 capitalize">
                    {char.gender}
                  </span>
                )}
                {char.age_range && (
                  <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-400 capitalize">
                    {char.age_range.replace("_", " ")}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Personality */}
          {char.personality.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {char.personality.map((trait, j) => (
                <span
                  key={j}
                  className="text-xs font-ui px-2 py-0.5 rounded-full border border-ink-200/50 dark:border-ink-700/50 text-ink-600 dark:text-ink-400"
                >
                  {trait}
                </span>
              ))}
            </div>
          )}

          {/* Speech patterns */}
          {char.speech_patterns?.distinctive_traits && (
            <p className="text-xs font-ui text-ink-500 dark:text-ink-400 mt-3 italic">
              &ldquo;{char.speech_patterns.distinctive_traits}&rdquo;
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function ScreenplayTab({
  chapters,
  bookId,
  hasCharacters,
}: {
  chapters: Chapter[];
  bookId: string;
  hasCharacters: boolean;
}) {
  const router = useRouter();

  if (!hasCharacters) {
    return (
      <div className="text-center py-16">
        <Sparkles className="w-12 h-12 text-ink-300 dark:text-ink-600 mx-auto mb-4" />
        <h3 className="font-display text-xl font-semibold text-ink-700 dark:text-ink-300 mb-2">
          Detect characters first
        </h3>
        <p className="font-ui text-ink-500 dark:text-ink-400 max-w-md mx-auto">
          The screenplay pipeline needs a character bible to work. Go to the Characters tab and run detection first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {chapters.map((ch, i) => (
        <button
          key={ch.id}
          onClick={() => router.push(`/book/${bookId}/screenplay/${ch.number}`)}
          className="w-full glass-card px-5 py-4 flex items-center justify-between group hover:shadow-md transition-all duration-200 animate-slide-up"
          style={{ animationDelay: `${i * 30}ms`, animationFillMode: "both" }}
        >
          <div className="flex items-center gap-4">
            <span className="w-8 h-8 rounded-lg bg-amber-warm/10 flex items-center justify-center">
              <Radio className="w-4 h-4 text-amber-warm" />
            </span>
            <div className="text-left">
              <p className="font-ui font-medium text-ink-800 dark:text-ink-200 group-hover:text-amber-warm transition-colors">
                {ch.title || `Chapter ${ch.number}`}
              </p>
              <p className="font-ui text-xs text-ink-400 mt-0.5">
                {ch.status === "screenplay_ready" ? "Screenplay ready" : "Click to generate screenplay"}
              </p>
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-ink-300 group-hover:text-amber-warm group-hover:translate-x-0.5 transition-all" />
        </button>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; label: string }> = {
    parsed: { color: "bg-ink-300 dark:bg-ink-600", label: "Imported" },
    screenplay_ready: { color: "bg-stage-blue", label: "Screenplay" },
    audio_ready: { color: "bg-stage-green", label: "Audio Ready" },
  };
  const c = config[status] || config.parsed;
  return (
    <span className={cn("w-2 h-2 rounded-full", c.color)} title={c.label} />
  );
}
