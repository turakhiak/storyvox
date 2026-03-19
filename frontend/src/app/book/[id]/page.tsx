"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, BookOpen, Users, Sparkles, Play, FileText, Square,
  ChevronRight, Loader2, Mic, Brain, Radio, Clock,
  RefreshCw, CheckCircle2, AlertCircle, Volume2, Headphones, Pencil
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getBook, getChapters, getCharacters, detectCharacters,
  updateCharacterVoice, getVoices, getBatchStatus, batchGenerate,
  stopBatch, resetBatch, updateBookmark, getScreenplay, getRevisions,
  getCoverUrl, formatWordCount, formatDuration,
} from "@/lib/api";
import type { Book, Chapter, Character, Voice, BatchStatus, ChapterStatus, Screenplay, RevisionRound, ScreenplaySegment } from "@/lib/api";

type Tab = "chapters" | "characters" | "voices" | "production" | "screenplay" | "audio";

const CRITERIA_LABELS: Record<string, string> = {
  dialogue_authenticity: "Dialogue",
  pacing_rhythm: "Pacing",
  character_voice_consistency: "Voice",
  emotional_arc: "Emotion",
  faithfulness: "Faithfulness",
};

const EMOTION_COLORS: Record<string, string> = {
  neutral: "text-ink-500",
  happy: "text-yellow-500",
  sad: "text-blue-400",
  angry: "text-red-500",
  fearful: "text-purple-400",
  tense: "text-orange-500",
  tender: "text-pink-400",
  sarcastic: "text-emerald-400",
  whisper: "text-ink-400",
  ominous: "text-violet-500",
  excited: "text-amber-400",
};

export default function BookPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("chapters");
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shows a "server is waking up" hint after 12s — matches the first retry delay
  const [warming, setWarming] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setWarming(true), 12_000);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      getBook(id).then(setBook),
      getChapters(id).then(setChapters),
      getCharacters(id).then(setCharacters).catch(() => []),
      getVoices().then(setVoices).catch(() => []),
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

  // Show loading/error state before book data arrives
  if (!book) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">
        {error ? (
          <>
            <AlertCircle className="w-8 h-8 text-stage-red" />
            <p className="text-stage-red font-ui text-sm text-center max-w-sm px-6">{error}</p>
            <button onClick={() => router.push("/")} className="btn-ghost text-sm flex items-center gap-2">
              <ArrowLeft className="w-4 h-4" /> Back to Library
            </button>
          </>
        ) : (
          <>
            <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
            {warming && (
              <p className="text-ink-500 font-ui text-sm text-center max-w-xs px-6">
                Server is starting up — this can take up to 60 seconds on first load…
              </p>
            )}
          </>
        )}
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
        <div className="flex gap-1 border-b border-ink-200/30 dark:border-ink-800/30 overflow-x-auto">
          {(["chapters", "characters", "voices", "production", "screenplay", "audio"] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-5 py-3 font-ui text-sm font-medium whitespace-nowrap capitalize transition-all duration-200 border-b-2 -mb-px",
                activeTab === tab
                  ? "border-amber-warm text-amber-warm"
                  : "border-transparent text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200"
              )}
            >
              {tab === "chapters" && <FileText className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "characters" && <Users className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "voices" && <Volume2 className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "production" && <Radio className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "screenplay" && <Pencil className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "audio" && <Headphones className="w-4 h-4 inline mr-2 -mt-0.5" />}
              {tab === "voices" ? "Voice Casting" : tab === "production" ? "Production" : tab === "screenplay" ? "Screenplay" : tab === "audio" ? "Audio Player" : tab}
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
        {activeTab === "voices" && (
          <VoiceCastingTab
            bookId={book.id}
            characters={characters}
            voices={voices}
            onCharactersUpdated={setCharacters}
            onDetect={handleDetectCharacters}
            detecting={detecting}
          />
        )}
        {activeTab === "production" && (
          <ProductionTab
            bookId={book.id}
            book={book}
            chapters={chapters}
            hasCharacters={characters.length > 0}
            onBookUpdate={setBook}
          />
        )}
        {activeTab === "screenplay" && (
          <ScreenplayViewTab
            bookId={book.id}
            chapters={chapters}
            characters={characters}
          />
        )}
        {activeTab === "audio" && (
          <AudioPlayerTab
            bookId={book.id}
            chapters={chapters}
            characters={characters}
          />
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

function ProductionTab({
  bookId,
  book,
  chapters,
  hasCharacters,
  onBookUpdate,
}: {
  bookId: string;
  book: Book;
  chapters: Chapter[];
  hasCharacters: boolean;
  onBookUpdate: (b: Book) => void;
}) {
  const router = useRouter();
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch batch status on mount and poll while processing
  const fetchStatus = async () => {
    try {
      const status = await getBatchStatus(bookId);
      setBatchStatus(status);
      return status;
    } catch (e: any) {
      // Not critical — batch API may not have been called yet
      return null;
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [bookId]);

  // Poll every 4s while batch is processing
  useEffect(() => {
    if (book.batch_status !== "processing") return;
    setPolling(true);
    const interval = setInterval(async () => {
      const status = await fetchStatus();
      if (status && status.batch_status !== "processing") {
        setPolling(false);
        clearInterval(interval);
        // Refresh book data
        getBook(bookId).then(onBookUpdate);
      }
    }, 4000);
    return () => { clearInterval(interval); setPolling(false); };
  }, [book.batch_status, bookId]);

  const handleBatchGenerate = async (startFrom?: number) => {
    setLoading(true);
    setError(null);
    try {
      const updated = await batchGenerate(bookId, {
        startFrom,
        audio: true,
      });
      onBookUpdate(updated);
      await fetchStatus();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      await stopBatch(bookId);
      // Refresh
      const updated = await getBook(bookId);
      onBookUpdate(updated);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    setError(null);
    try {
      await resetBatch(bookId);
      const updated = await getBook(bookId);
      onBookUpdate(updated);
      await fetchStatus();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleBookmarkUpdate = async (chapterNum: number) => {
    try {
      await updateBookmark(bookId, chapterNum);
      onBookUpdate({ ...book, listen_bookmark: chapterNum });
    } catch (e: any) {
      setError(e.message);
    }
  };

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

  const bookmark = book.listen_bookmark || 0;
  const isProcessing = book.batch_status === "processing";
  const progress = book.batch_progress;

  // Determine which chapters are ready vs pending
  const chapterStatuses = batchStatus?.chapters || [];
  const readyCount = chapterStatuses.filter((c) => c.screenplay_status === "complete").length;
  const audioReadyCount = chapterStatuses.filter((c) => c.audio_status === "complete").length;

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-stage-red/10 border border-stage-red/20 rounded-xl px-4 py-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-stage-red flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="text-stage-red text-sm font-ui block">{error}</span>
            {(error.includes("quota") || error.includes("rate") || error.includes("429")) && (
              <span className="text-stage-red/70 text-xs font-ui mt-1 block">
                Tip: Groq has a 100k token/day free limit. If hit, wait until midnight UTC (~5:30 AM IST) or the app will auto-use Gemini/Ollama as fallback.
              </span>
            )}
            {error.includes("already processing") && (
              <div className="mt-2">
                <span className="text-stage-red/70 text-xs font-ui block mb-2">
                  The server may have restarted and left a stale lock. Click Reset to clear it, then try generating again.
                </span>
                <button
                  onClick={handleReset}
                  disabled={loading}
                  className="btn-ghost text-stage-red border-stage-red/40 text-xs flex items-center gap-1.5 py-1 px-3"
                >
                  {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  Reset stuck batch
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Show failed chapters summary if batch just finished with failures */}
      {!isProcessing && batchStatus && batchStatus.chapters.some(c => c.screenplay_status === "failed") && !error && (
        <div className="bg-amber-warm/10 border border-amber-warm/30 rounded-xl px-4 py-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-amber-warm flex-shrink-0 mt-0.5" />
          <div>
            <span className="text-amber-warm text-sm font-ui font-medium">
              {batchStatus.chapters.filter(c => c.screenplay_status === "failed").length} chapter(s) failed to generate.
            </span>
            <span className="text-amber-warm/80 text-xs font-ui block mt-0.5">
              This usually means all LLM providers hit their limits. Click Retry next to each failed chapter, or wait for Groq to reset at midnight UTC.
            </span>
          </div>
        </div>
      )}

      {/* Production controls */}
      <div className="glass-card p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h3 className="font-display text-lg font-semibold text-ink-900 dark:text-ink-100 flex items-center gap-2">
              <Radio className="w-5 h-5 text-amber-warm" />
              Production Pipeline
            </h3>
            <p className="font-ui text-sm text-ink-500 dark:text-ink-400 mt-1">
              Generates screenplay + audio for 5 chapters at a time. Picks up from your listening bookmark.
            </p>

            {/* Stats row */}
            <div className="flex flex-wrap gap-4 mt-4 font-ui text-sm">
              <span className="text-ink-500 dark:text-ink-400">
                Bookmark: <span className="font-semibold text-ink-800 dark:text-ink-200">Ch. {bookmark || "—"}</span>
              </span>
              <span className="text-ink-500 dark:text-ink-400">
                Screenplays: <span className="font-semibold text-stage-blue">{readyCount}</span>/{chapters.length}
              </span>
              <span className="text-ink-500 dark:text-ink-400">
                Audio: <span className="font-semibold text-stage-green">{audioReadyCount}</span>/{chapters.length}
              </span>
            </div>
          </div>

          <div className="flex gap-3 flex-wrap">
            {isProcessing ? (
              <>
                <button
                  onClick={handleReset}
                  disabled={loading}
                  className="btn-ghost text-ink-500 border-ink-300 dark:border-ink-600 flex items-center gap-2 text-sm"
                  title="Force-clear a stuck batch"
                >
                  {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  Force Reset
                </button>
                <button onClick={handleStop} className="btn-ghost text-stage-red border-stage-red/30 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  Stop Batch
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => handleBatchGenerate(bookmark + 1)}
                  className="btn-primary flex items-center gap-2"
                  disabled={loading}
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  {loading ? "Starting..." : `Generate Next 5 (from Ch. ${bookmark + 1})`}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Progress bar during processing */}
        {isProcessing && progress && (
          <div className="mt-5">
            <div className="flex items-center justify-between font-ui text-sm mb-2">
              <span className="text-ink-500 dark:text-ink-400 flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-warm" />
                Processing Chapter {progress.current_chapter}
                {progress.current_index && progress.total_in_batch
                  ? ` (${progress.current_index}/${progress.total_in_batch})`
                  : ""}
              </span>
              <span className="text-ink-400 text-xs">
                {progress.completed?.length || 0} done · {progress.failed?.length || 0} failed
              </span>
            </div>
            <div className="w-full bg-ink-100 dark:bg-ink-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-amber-warm h-full rounded-full transition-all duration-500"
                style={{
                  width: `${((progress.completed?.length || 0) / (progress.total_in_batch || 1)) * 100}%`,
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Bookmark control */}
      <div className="glass-card p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="w-5 h-5 text-amber-warm" />
          <div>
            <p className="font-ui font-medium text-sm text-ink-800 dark:text-ink-200">Listening Bookmark</p>
            <p className="font-ui text-xs text-ink-400">
              {bookmark > 0
                ? `You've listened through Chapter ${bookmark}. Next batch starts at Chapter ${bookmark + 1}.`
                : "No bookmark set. Batch will start from Chapter 1."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <select
            value={bookmark}
            onChange={(e) => handleBookmarkUpdate(parseInt(e.target.value))}
            className="appearance-none bg-surface-light dark:bg-surface-dark border border-ink-200/50 dark:border-ink-700/50 rounded-lg px-3 py-1.5 font-ui text-sm text-ink-800 dark:text-ink-200 focus:outline-none focus:ring-2 focus:ring-amber-warm/40 cursor-pointer"
          >
            <option value={0}>Not started</option>
            {chapters.map((ch) => (
              <option key={ch.number} value={ch.number}>
                Ch. {ch.number} {ch.title ? `— ${ch.title}` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Chapter list with statuses */}
      <div className="space-y-2">
        <h4 className="font-ui text-sm font-semibold text-ink-500 dark:text-ink-400 uppercase tracking-wider">
          All Chapters
        </h4>
        {chapters.map((ch, i) => {
          const cs = chapterStatuses.find((c) => c.number === ch.number);
          const isBookmarked = ch.number <= bookmark;
          const isNonStory = cs?.is_non_story === true;
          const screenplayDone = cs?.screenplay_status === "complete";
          const audioDone = cs?.audio_status === "complete";
          const isCurrentlyProcessing = isProcessing && progress?.current_chapter === ch.number;
          const isFailed = cs?.screenplay_status === "failed";

          return (
            <div
              key={ch.id}
              className={cn(
                "glass-card px-5 py-4 flex items-center justify-between animate-slide-up",
                isBookmarked && "opacity-60",
                isNonStory && "opacity-40",
                isCurrentlyProcessing && "ring-2 ring-amber-warm/40",
              )}
              style={{ animationDelay: `${i * 25}ms`, animationFillMode: "both" }}
            >
              <div className="flex items-center gap-4">
                <span className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center font-mono text-sm",
                  audioDone
                    ? "bg-stage-green/10 text-stage-green"
                    : screenplayDone
                    ? "bg-stage-blue/10 text-stage-blue"
                    : isFailed
                    ? "bg-stage-red/10 text-stage-red"
                    : "bg-ink-100 dark:bg-ink-800 text-ink-500 dark:text-ink-400"
                )}>
                  {isCurrentlyProcessing ? (
                    <Loader2 className="w-4 h-4 animate-spin text-amber-warm" />
                  ) : audioDone ? (
                    <CheckCircle2 className="w-4 h-4" />
                  ) : screenplayDone ? (
                    <FileText className="w-4 h-4" />
                  ) : isFailed ? (
                    <AlertCircle className="w-4 h-4" />
                  ) : (
                    ch.number
                  )}
                </span>
                <div className="text-left">
                  <p className="font-ui font-medium text-ink-800 dark:text-ink-200">
                    {ch.title || `Chapter ${ch.number}`}
                  </p>
                  <p className="font-ui text-xs text-ink-400 mt-0.5">
                    {formatWordCount(ch.word_count)}
                    {cs?.score ? ` · Score: ${cs.score.toFixed(1)}` : ""}
                    {isCurrentlyProcessing ? " · Generating..." : ""}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {/* Status badges */}
                <div className="flex gap-1.5">
                  {screenplayDone && (
                    <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-stage-blue/10 text-stage-blue">
                      Screenplay
                    </span>
                  )}
                  {audioDone && (
                    <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-stage-green/10 text-stage-green">
                      Audio
                    </span>
                  )}
                  {isFailed && (
                    <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-stage-red/10 text-stage-red">
                      Failed
                    </span>
                  )}
                  {isNonStory && (
                    <span className="text-xs font-ui px-2 py-0.5 rounded-full bg-ink-200/50 dark:bg-ink-700/50 text-ink-400">
                      Skipped
                    </span>
                  )}
                </div>

                {/* Retry button for failed chapters */}
                {isFailed && !isProcessing && (
                  <button
                    onClick={() => handleBatchGenerate(ch.number)}
                    disabled={loading}
                    className="text-xs font-ui px-3 py-1 rounded-lg bg-stage-red/10 text-stage-red hover:bg-stage-red hover:text-white transition-all flex items-center gap-1"
                    title="Retry this chapter"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Retry
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Helper: pick a sensible default voice for a character based on their traits
function getDefaultVoice(char: Character): string {
  const gender = (char.gender || "").toLowerCase();
  const age = (char.age_range || "").toLowerCase();
  const personality = (char.personality || []).map((p) => p.toLowerCase());

  if (age === "child") return "en-US-AnaNeural";

  const isGb = personality.some((p) => ["proper", "formal", "stoic", "royal"].includes(p));
  const isAu = personality.some((p) => ["rough", "wild", "friendly", "outdoorsy"].includes(p));
  const accent = isGb ? "gb" : isAu ? "au" : "us";

  const map: Record<string, string> = {
    "male_gb": "en-GB-ThomasNeural",
    "male_us": "en-US-GuyNeural",
    "male_au": "en-AU-WilliamNeural",
    "female_gb": "en-GB-SoniaNeural",
    "female_us": "en-US-AvaNeural",
    "female_au": "en-AU-NatashaNeural",
  };
  return map[`${gender}_${accent}`] || "en-GB-RyanNeural";
}

function VoiceCastingTab({
  bookId,
  characters,
  voices,
  onCharactersUpdated,
  onDetect,
  detecting,
}: {
  bookId: string;
  characters: Character[];
  voices: Voice[];
  onCharactersUpdated: (chars: Character[]) => void;
  onDetect: () => void;
  detecting: boolean;
}) {
  const [saving, setSaving] = useState<string | null>(null); // character id currently being saved
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<HTMLAudioElement | null>(null);
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);

  if (characters.length === 0) {
    return (
      <div className="text-center py-16">
        <Volume2 className="w-12 h-12 text-ink-300 dark:text-ink-600 mx-auto mb-4" />
        <h3 className="font-display text-xl font-semibold text-ink-700 dark:text-ink-300 mb-2">
          Detect characters first
        </h3>
        <p className="font-ui text-ink-500 dark:text-ink-400 mb-6 max-w-md mx-auto">
          Voice casting requires a character list. Run character detection first.
        </p>
        <button onClick={onDetect} className="btn-primary" disabled={detecting}>
          {detecting ? <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> : <Brain className="w-4 h-4 inline mr-2" />}
          Detect Characters
        </button>
      </div>
    );
  }

  // Group voices by gender for the dropdown
  const voicesByGender = voices.reduce<Record<string, Voice[]>>((acc, v) => {
    const group = v.gender === "child" ? "Children" : v.gender === "male" ? "Male Voices" : "Female Voices";
    if (!acc[group]) acc[group] = [];
    acc[group].push(v);
    return acc;
  }, {});

  const handleVoiceChange = async (char: Character, voiceId: string) => {
    // Optimistic update
    const updated = characters.map((c) => c.id === char.id ? { ...c, voice_id: voiceId } : c);
    onCharactersUpdated(updated);

    setSaving(char.id);
    try {
      await updateCharacterVoice(bookId, char.id, voiceId);
      setSaved((prev) => new Set([...prev, char.id]));
      setTimeout(() => setSaved((prev) => { const n = new Set(prev); n.delete(char.id); return n; }), 2000);
    } catch (e) {
      // Revert on error
      onCharactersUpdated(characters);
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="font-display text-lg font-semibold text-ink-900 dark:text-ink-100">Voice Casting</h3>
          <p className="font-ui text-sm text-ink-500 dark:text-ink-400 mt-0.5">
            Assign a voice to each character. Changes are saved automatically and used during audio generation.
          </p>
        </div>
      </div>

      {/* Narrator row */}
      <div className="glass-card p-4 border border-amber-warm/20">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-amber-warm/10 flex items-center justify-center flex-shrink-0">
            <Mic className="w-5 h-5 text-amber-warm" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-ui font-semibold text-ink-900 dark:text-ink-100">Narrator</p>
            <p className="font-ui text-xs text-ink-400 mt-0.5">Reads all narration and stage directions</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="font-ui text-xs text-ink-500 dark:text-ink-400 bg-ink-100 dark:bg-ink-800 px-2 py-1 rounded-lg">
              Ryan · British · Default
            </span>
          </div>
        </div>
      </div>

      {/* Character rows */}
      {characters.map((char, i) => {
        const currentVoiceId = char.voice_id || getDefaultVoice(char);
        const currentVoice = voices.find((v) => v.id === currentVoiceId);
        const isSaving = saving === char.id;
        const justSaved = saved.has(char.id);

        return (
          <div
            key={char.id}
            className="glass-card p-4 animate-slide-up"
            style={{ animationDelay: `${i * 40}ms`, animationFillMode: "both" }}
          >
            <div className="flex items-center gap-4 flex-wrap sm:flex-nowrap">
              {/* Avatar */}
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center font-display font-bold text-white text-sm flex-shrink-0"
                style={{ backgroundColor: char.color_hex || "#6B9080" }}
              >
                {char.name.charAt(0)}
              </div>

              {/* Name + traits */}
              <div className="flex-1 min-w-0">
                <p className="font-ui font-semibold text-ink-900 dark:text-ink-100">{char.name}</p>
                <p className="font-ui text-xs text-ink-400 capitalize mt-0.5">
                  {[char.frequency, char.gender, char.age_range?.replace("_", " ")].filter(Boolean).join(" · ")}
                </p>
              </div>

              {/* Voice dropdown */}
              <div className="flex items-center gap-2 flex-shrink-0 w-full sm:w-auto">
                <div className="relative flex-1 sm:w-64">
                  <select
                    value={currentVoiceId}
                    onChange={(e) => handleVoiceChange(char, e.target.value)}
                    disabled={isSaving}
                    className="w-full appearance-none bg-surface-light dark:bg-surface-dark border border-ink-200/50 dark:border-ink-700/50 rounded-xl px-3 py-2 pr-8 font-ui text-sm text-ink-800 dark:text-ink-200 focus:outline-none focus:ring-2 focus:ring-amber-warm/40 disabled:opacity-50 cursor-pointer"
                  >
                    {Object.entries(voicesByGender).map(([group, groupVoices]) => (
                      <optgroup key={group} label={group}>
                        {groupVoices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label} ({v.accent}) — {v.description}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2">
                    <ChevronRight className="w-3.5 h-3.5 text-ink-400 rotate-90" />
                  </div>
                </div>

                {/* Status indicator */}
                <div className="w-6 flex-shrink-0">
                  {isSaving && <Loader2 className="w-4 h-4 text-ink-400 animate-spin" />}
                  {justSaved && !isSaving && <CheckCircle2 className="w-4 h-4 text-stage-green" />}
                </div>
              </div>
            </div>

            {/* Current voice label */}
            {currentVoice && (
              <div className="mt-2 ml-14 flex items-center gap-1.5">
                <Volume2 className="w-3 h-3 text-ink-400" />
                <span className="font-ui text-xs text-ink-400">
                  {currentVoice.label} · {currentVoice.accent}
                  {!char.voice_id && " (auto-assigned)"}
                </span>
              </div>
            )}
          </div>
        );
      })}
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

// ---------------------------------------------------------------------------
// Screenplay View Tab
// ---------------------------------------------------------------------------

function ScreenplayViewTab({
  bookId,
  chapters,
  characters,
}: {
  bookId: string;
  chapters: Chapter[];
  characters: Character[];
}) {
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"radio_play" | "faithful">("radio_play");
  const [currentlyPlayingIndex, setCurrentlyPlayingIndex] = useState<number | null>(null);

  // ── Audio engine ────────────────────────────────────────────────────────────
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Stop and release any playing audio
  const stopPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    setCurrentlyPlayingIndex(null);
  };

  // Build absolute URL from relative audio path
  const buildAudioUrl = (relUrl: string) => {
    if (relUrl.startsWith("http")) return relUrl;
    const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
    return `${base}${relUrl.startsWith("/") ? relUrl : `/${relUrl}`}`;
  };

  // Play a segment at the given index. Called directly from onClick — stays in user gesture stack.
  const playSegment = (index: number, segments: ScreenplaySegment[]) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    const seg = segments[index];
    if (!seg?.audio_url) { setCurrentlyPlayingIndex(null); return; }

    const audio = new Audio(buildAudioUrl(seg.audio_url));
    audioRef.current = audio;
    setCurrentlyPlayingIndex(index);

    audio.play().catch(() => { audioRef.current = null; setCurrentlyPlayingIndex(null); });
    audio.onended = () => {
      audioRef.current = null;
      setCurrentlyPlayingIndex(null);
      const next = segments.findIndex((s, idx) => idx > index && s.audio_url);
      if (next !== -1) playSegment(next, segments); // auto-advance (audio event → allowed)
    };
    audio.onerror = () => { audioRef.current = null; setCurrentlyPlayingIndex(null); };
  };

  // Stop audio when tab unmounts
  useEffect(() => () => { audioRef.current?.pause(); }, []);
  // ────────────────────────────────────────────────────────────────────────────

  const charColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    characters.forEach((c) => { map[c.name] = c.color_hex || "#6B9080"; });
    return map;
  }, [characters]);

  const loadScreenplay = useCallback(async (ch: Chapter, m: string) => {
    stopPlayback();
    setSelectedChapter(ch);
    setLoading(true);
    setScreenplay(null);
    try {
      const sp = await getScreenplay(ch.id, m);
      setScreenplay(sp);
    } catch {
      setScreenplay(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="flex gap-6 min-h-[500px]">
      {/* Chapter sidebar */}
      <div className="w-56 flex-shrink-0 space-y-1 overflow-y-auto max-h-[80vh] pr-2">
        <p className="font-ui text-xs uppercase tracking-wider text-ink-400 mb-3 px-2">Chapters</p>
        {chapters.map((ch) => (
          <button
            key={ch.id}
            onClick={() => loadScreenplay(ch, mode)}
            className={cn(
              "w-full text-left px-3 py-2.5 rounded-xl text-sm font-ui transition-colors",
              selectedChapter?.id === ch.id
                ? "bg-amber-warm/15 text-amber-warm font-medium"
                : "hover:bg-ink-100 dark:hover:bg-ink-800/50 text-ink-600 dark:text-ink-400"
            )}
          >
            <span className="text-ink-400 dark:text-ink-600 mr-2 font-mono text-xs">{ch.number}</span>
            {ch.title || `Chapter ${ch.number}`}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {!selectedChapter ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Pencil className="w-12 h-12 text-ink-200 dark:text-ink-700 mb-4" />
            <p className="font-ui text-ink-400">Select a chapter to view its screenplay</p>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
          </div>
        ) : !screenplay ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Sparkles className="w-12 h-12 text-ink-200 dark:text-ink-700 mb-4" />
            <p className="font-ui text-ink-500 mb-2">No screenplay for this chapter yet</p>
            <p className="font-ui text-xs text-ink-400">Generate it from the Production tab</p>
          </div>
        ) : (
          <div>
            {/* Header row */}
            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
              <h3 className="font-display text-xl font-semibold text-ink-900 dark:text-ink-100">
                {selectedChapter.title || `Chapter ${selectedChapter.number}`}
              </h3>
              <div className="flex items-center bg-ink-100 dark:bg-ink-800/50 rounded-lg p-0.5">
                <button
                  onClick={() => { setMode("radio_play"); loadScreenplay(selectedChapter, "radio_play"); }}
                  className={cn("px-3 py-1.5 rounded-md text-xs font-ui font-medium transition-all",
                    mode === "radio_play" ? "bg-amber-warm text-ink-950 shadow-sm" : "text-ink-500 hover:text-ink-700 dark:hover:text-ink-300")}
                >
                  <Radio className="w-3 h-3 inline mr-1" />Radio Play
                </button>
                <button
                  onClick={() => { setMode("faithful"); loadScreenplay(selectedChapter, "faithful"); }}
                  className={cn("px-3 py-1.5 rounded-md text-xs font-ui font-medium transition-all",
                    mode === "faithful" ? "bg-amber-warm text-ink-950 shadow-sm" : "text-ink-500 hover:text-ink-700 dark:hover:text-ink-300")}
                >
                  <BookOpen className="w-3 h-3 inline mr-1" />Faithful
                </button>
              </div>
            </div>

            {/* Score card */}
            {screenplay.weighted_avg !== null && screenplay.weighted_avg !== undefined && (
              <div className="glass-card p-5 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-stage-green" />
                    <span className="font-ui font-semibold text-sm text-ink-800 dark:text-ink-200">
                      Director&apos;s Score — Round {screenplay.total_rounds}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-display text-2xl font-bold text-amber-warm">
                      {screenplay.weighted_avg.toFixed(1)}
                    </span>
                    {screenplay.audio_status === "complete" && (
                      <button
                        onClick={() => {
                          if (currentlyPlayingIndex !== null) {
                            stopPlayback();
                          } else {
                            const firstIdx = screenplay.segments.findIndex((s) => s.audio_url);
                            if (firstIdx !== -1) playSegment(firstIdx, screenplay.segments);
                          }
                        }}
                        className={cn(
                          "btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5",
                          currentlyPlayingIndex !== null ? "bg-amber-warm" : "bg-stage-green hover:bg-stage-green/90"
                        )}
                      >
                        {currentlyPlayingIndex !== null
                          ? <><Volume2 className="w-3 h-3 animate-pulse" /> Stop</>
                          : <><Play className="w-3 h-3 fill-current" /> Listen</>}
                      </button>
                    )}
                  </div>
                </div>
                {screenplay.final_scores && (
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    {Object.entries(screenplay.final_scores).map(([key, score]) => (
                      <div key={key}>
                        <div className="flex justify-between mb-1">
                          <span className="font-ui text-xs text-ink-500">{CRITERIA_LABELS[key] || key}</span>
                          <span className={cn("font-mono text-xs font-semibold",
                            (score as number) >= 8 ? "text-stage-green" : (score as number) >= 6 ? "text-amber-warm" : "text-stage-red"
                          )}>{score as number}</span>
                        </div>
                        <div className="h-1.5 bg-ink-100 dark:bg-ink-800 rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full transition-all",
                              (score as number) >= 8 ? "bg-stage-green" : (score as number) >= 6 ? "bg-amber-warm" : "bg-stage-red")}
                            style={{ width: `${((score as number) / 10) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Segments */}
            <div className="space-y-1">
              {screenplay.segments.map((seg, i) => (
                <SegmentCard
                  key={seg.id || i}
                  segment={seg}
                  index={i}
                  isPlaying={currentlyPlayingIndex === i}
                  onPlay={() => playSegment(i, screenplay.segments)}
                  onStop={stopPlayback}
                  charColorMap={charColorMap}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audio Player Tab
// ---------------------------------------------------------------------------

function AudioPlayerTab({
  bookId,
  chapters,
  characters,
}: {
  bookId: string;
  chapters: Chapter[];
  characters: Character[];
}) {
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [loadingScreenplay, setLoadingScreenplay] = useState(false);
  const [currentlyPlayingIndex, setCurrentlyPlayingIndex] = useState<number | null>(null);

  // ── Audio engine ────────────────────────────────────────────────────────────
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stopPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    setCurrentlyPlayingIndex(null);
  };

  const buildAudioUrl = (relUrl: string) => {
    if (relUrl.startsWith("http")) return relUrl;
    const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
    return `${base}${relUrl.startsWith("/") ? relUrl : `/${relUrl}`}`;
  };

  // Must be called directly from onClick to stay within user gesture stack.
  const playSegment = (index: number, segments: ScreenplaySegment[]) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    const seg = segments[index];
    if (!seg?.audio_url) { setCurrentlyPlayingIndex(null); return; }

    const audio = new Audio(buildAudioUrl(seg.audio_url));
    audioRef.current = audio;
    setCurrentlyPlayingIndex(index);

    audio.play().catch(() => { audioRef.current = null; setCurrentlyPlayingIndex(null); });
    audio.onended = () => {
      audioRef.current = null;
      setCurrentlyPlayingIndex(null);
      const next = segments.findIndex((s, idx) => idx > index && s.audio_url);
      if (next !== -1) playSegment(next, segments); // auto-advance from audio event
    };
    audio.onerror = () => { audioRef.current = null; setCurrentlyPlayingIndex(null); };
  };

  // Stop audio when tab unmounts
  useEffect(() => () => { audioRef.current?.pause(); }, []);
  // ────────────────────────────────────────────────────────────────────────────

  const charColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    characters.forEach((c) => { map[c.name] = c.color_hex || "#6B9080"; });
    return map;
  }, [characters]);

  useEffect(() => {
    getBatchStatus(bookId).then(setBatchStatus).catch(() => null);
  }, [bookId]);

  const chapterStatuses = batchStatus?.chapters || [];
  const audioChapters = chapters.filter((ch) => {
    const cs = chapterStatuses.find((c) => c.number === ch.number);
    return cs?.audio_status === "complete";
  });

  // Load a chapter's screenplay (no auto-play — user must click Play after load)
  const handleSelectChapter = async (ch: Chapter) => {
    if (selectedChapter?.id === ch.id) return;
    stopPlayback();
    setSelectedChapter(ch);
    setLoadingScreenplay(true);
    setScreenplay(null);
    try {
      const sp = await getScreenplay(ch.id, "radio_play");
      setScreenplay(sp);
    } catch {
      setScreenplay(null);
    } finally {
      setLoadingScreenplay(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Now playing bar */}
      {selectedChapter && screenplay && (
        <div className="glass-card p-4 border border-amber-warm/20 flex items-center gap-4 sticky top-20 z-10">
          <div className={cn(
            "w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0",
            currentlyPlayingIndex !== null ? "bg-amber-warm/20" : "bg-stage-green/10"
          )}>
            {currentlyPlayingIndex !== null
              ? <Volume2 className="w-5 h-5 text-amber-warm animate-pulse" />
              : <Play className="w-5 h-5 text-stage-green" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-ui text-sm font-semibold text-ink-900 dark:text-ink-100">
              {currentlyPlayingIndex !== null ? "▶ Now Playing" : "Ready"} — {selectedChapter.title || `Chapter ${selectedChapter.number}`}
            </p>
            {currentlyPlayingIndex !== null && screenplay.segments[currentlyPlayingIndex] && (
              <p className="font-ui text-xs text-ink-400 truncate mt-0.5">
                {screenplay.segments[currentlyPlayingIndex].character_name
                  ? `${screenplay.segments[currentlyPlayingIndex].character_name}: `
                  : "Narrator: "}
                {screenplay.segments[currentlyPlayingIndex].text.slice(0, 90)}
              </p>
            )}
          </div>
          <button
            onClick={() => {
              if (currentlyPlayingIndex !== null) {
                stopPlayback();
              } else {
                const firstIdx = screenplay.segments.findIndex((s) => s.audio_url);
                if (firstIdx !== -1) playSegment(firstIdx, screenplay.segments);
              }
            }}
            className={cn(
              "flex-shrink-0 px-4 py-2 rounded-xl text-sm font-ui font-medium transition-all",
              currentlyPlayingIndex !== null
                ? "bg-stage-red/10 text-stage-red hover:bg-stage-red/20"
                : "bg-stage-green/10 text-stage-green hover:bg-stage-green hover:text-white"
            )}
          >
            {currentlyPlayingIndex !== null ? "Stop" : "Play All"}
          </button>
        </div>
      )}

      {/* Chapter list */}
      {audioChapters.length === 0 ? (
        <div className="text-center py-16">
          <Headphones className="w-12 h-12 text-ink-300 dark:text-ink-600 mx-auto mb-4" />
          <h3 className="font-display text-xl font-semibold text-ink-700 dark:text-ink-300 mb-2">No audio ready yet</h3>
          <p className="font-ui text-ink-500 dark:text-ink-400 max-w-md mx-auto">
            Generate screenplays and audio from the Production tab first.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="font-ui text-xs uppercase tracking-wider text-ink-400 font-semibold">
            {audioChapters.length} Chapter{audioChapters.length !== 1 ? "s" : ""} with Audio
          </p>
          {audioChapters.map((ch) => {
            const cs = chapterStatuses.find((c) => c.number === ch.number);
            const isSelected = ch.id === selectedChapter?.id;
            const isPlaying = isSelected && currentlyPlayingIndex !== null;

            return (
              <div
                key={ch.id}
                className={cn(
                  "glass-card transition-all duration-200",
                  isSelected && "ring-2 ring-amber-warm/40"
                )}
              >
                <div className="px-5 py-4 flex items-center justify-between">
                  <button
                    className="flex items-center gap-4 flex-1 text-left"
                    onClick={() => handleSelectChapter(ch)}
                  >
                    <span className={cn(
                      "w-9 h-9 rounded-xl flex items-center justify-center font-mono text-sm flex-shrink-0 transition-all",
                      isPlaying ? "bg-amber-warm text-ink-950" : isSelected ? "bg-stage-green/20 text-stage-green" : "bg-stage-green/10 text-stage-green"
                    )}>
                      {isPlaying ? <Volume2 className="w-4 h-4 animate-pulse" /> : <Play className="w-4 h-4" />}
                    </span>
                    <div>
                      <p className="font-ui font-medium text-ink-800 dark:text-ink-200">
                        {ch.title || `Chapter ${ch.number}`}
                      </p>
                      <p className="font-ui text-xs text-ink-400 mt-0.5">
                        {formatWordCount(ch.word_count)}
                        {cs?.score ? ` · Score ${cs.score.toFixed(1)}` : ""}
                        {isSelected && screenplay
                          ? ` · ${screenplay.segments.filter((s) => s.audio_url).length} audio segments`
                          : ""}
                      </p>
                    </div>
                  </button>

                  <button
                    onClick={() => {
                      if (isPlaying) {
                        stopPlayback();
                      } else if (isSelected && screenplay) {
                        // Screenplay already loaded — play directly (user gesture ✓)
                        const firstIdx = screenplay.segments.findIndex((s) => s.audio_url);
                        if (firstIdx !== -1) playSegment(firstIdx, screenplay.segments);
                      } else {
                        // Need to load first — just select the chapter; user clicks Play after
                        handleSelectChapter(ch);
                      }
                    }}
                    className={cn(
                      "ml-4 flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-ui font-medium transition-all flex-shrink-0",
                      isPlaying
                        ? "bg-amber-warm text-ink-950"
                        : "bg-stage-green/10 text-stage-green hover:bg-stage-green hover:text-white"
                    )}
                  >
                    {loadingScreenplay && isSelected ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : isPlaying ? (
                      <Volume2 className="w-4 h-4 animate-pulse" />
                    ) : (
                      <Play className="w-4 h-4 fill-current" />
                    )}
                    {loadingScreenplay && isSelected ? "Loading..." : isPlaying ? "Stop" : "Play"}
                  </button>
                </div>

                {/* Expanded segment list when this chapter is selected */}
                {isSelected && !loadingScreenplay && screenplay && (
                  <div className="px-5 pb-5 pt-0 border-t border-ink-200/10 dark:border-ink-800/20">
                    <div className="space-y-1 mt-4">
                      {screenplay.segments.map((seg, i) => (
                        <SegmentCard
                          key={seg.id || i}
                          segment={seg}
                          index={i}
                          isPlaying={currentlyPlayingIndex === i}
                          onPlay={() => playSegment(i, screenplay.segments)}
                          onStop={stopPlayback}
                          charColorMap={charColorMap}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {isSelected && loadingScreenplay && (
                  <div className="px-5 pb-5 flex items-center justify-center h-24">
                    <Loader2 className="w-6 h-6 text-amber-warm animate-spin" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared SegmentCard (screenplay + audio tabs)
// Pure display component — no internal audio logic.
// onPlay / onStop are called directly from onClick (within user gesture stack).
// ---------------------------------------------------------------------------

function SegmentCard({
  segment,
  index,
  charColorMap,
  isPlaying,
  onPlay,
  onStop,
}: {
  segment: ScreenplaySegment;
  index: number;
  charColorMap: Record<string, string>;
  isPlaying: boolean;
  onPlay: () => void;
  onStop: () => void;
}) {
  const color = segment.character_name ? charColorMap[segment.character_name] : undefined;
  const hasAudio = !!segment.audio_url;

  const PlayBtn = () => (
    <button
      onClick={() => { if (isPlaying) onStop(); else if (hasAudio) onPlay(); }}
      disabled={!hasAudio}
      className={cn(
        "ml-auto p-2.5 rounded-full transition-all flex-shrink-0 border-2",
        isPlaying
          ? "bg-amber-warm text-ink-950 border-amber-warm shadow-lg scale-110"
          : hasAudio
            ? "bg-stage-green/10 text-stage-green border-stage-green/30 hover:bg-stage-green hover:text-white"
            : "opacity-0 pointer-events-none border-transparent"
      )}
    >
      {isPlaying ? <Volume2 className="w-4 h-4 animate-pulse" /> : <Play className="w-4 h-4 fill-current" />}
    </button>
  );

  if (segment.type === "sound_cue") {
    return (
      <div className="flex items-center justify-between my-3 px-4 py-2.5 rounded-xl bg-stage-blue/5 border border-stage-blue/15">
        <div className="flex items-center gap-3">
          <Volume2 className="w-4 h-4 text-stage-blue flex-shrink-0" />
          <span className="font-mono text-sm uppercase tracking-wider text-stage-blue">{segment.text}</span>
        </div>
        <PlayBtn />
      </div>
    );
  }

  if (segment.type === "narration") {
    return (
      <div className="flex gap-6 px-4 py-3 rounded-xl hover:bg-ink-50 dark:hover:bg-ink-900/20 group">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <BookOpen className="w-3.5 h-3.5 text-ink-400" />
            <span className="font-ui text-[10px] uppercase tracking-[0.2em] text-ink-400">Narrator</span>
            {segment.emotion && (
              <span className={cn("text-[10px] font-ui italic", EMOTION_COLORS[segment.emotion] || "text-ink-400")}>
                ({segment.emotion})
              </span>
            )}
          </div>
          <p className="font-body text-base leading-relaxed text-ink-700 dark:text-ink-300">{segment.text}</p>
        </div>
        <PlayBtn />
      </div>
    );
  }

  // Dialogue
  return (
    <div
      className="flex gap-6 px-4 py-3 rounded-xl hover:bg-ink-50 dark:hover:bg-ink-900/20 group border-l-2"
      style={{ borderLeftColor: color || "#6B9080" }}
    >
      <div className="flex-1">
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className="w-5 h-5 rounded-md flex items-center justify-center text-white text-[10px] font-bold"
            style={{ backgroundColor: color || "#6B9080" }}
          >
            {segment.character_name?.charAt(0) || "?"}
          </span>
          <span className="font-ui text-sm font-semibold" style={{ color: color || "#6B9080" }}>
            {segment.character_name}
          </span>
          {segment.emotion && (
            <span className={cn("text-[10px] font-ui italic", EMOTION_COLORS[segment.emotion] || "text-ink-400")}>
              ({segment.emotion})
            </span>
          )}
        </div>
        <p className="font-body text-base leading-relaxed text-ink-800 dark:text-ink-200">{segment.text}</p>
      </div>
      <PlayBtn />
    </div>
  );
}
