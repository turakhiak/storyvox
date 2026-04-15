"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, ChevronLeft, ChevronRight, Settings,
  Minus, Plus, Loader2, Type, Gauge, Play, Pause,
  SkipForward, SkipBack, Headphones, Volume2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getBook, getChapter, getChapters, updateBookmark, getScreenplay,
} from "@/lib/api";
import type { Book, Chapter, Screenplay, ScreenplaySegment } from "@/lib/api";
import { useLibraryStore, READER_FONTS, type ReaderFontId } from "@/store/library";

// Build absolute URL from a relative audio path served by the API.
function buildAudioUrl(relUrl: string): string {
  if (relUrl.startsWith("http")) return relUrl;
  const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
  return `${base}${relUrl.startsWith("/") ? relUrl : `/${relUrl}`}`;
}

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

  // Audio playback state
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [loadingAudio, setLoadingAudio] = useState(false);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  // Refs to dom elements + audio object (kept outside React state because
  // updating them shouldn't re-render the whole reader on every audio tick).
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const segmentRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const num = parseInt(chapterNum, 10);

  // Load the book + this chapter + total count up-front
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

  // Once we know the chapter id, try to load its screenplay (whichever mode
  // exists). Failures are silent — the reader works fine without audio.
  useEffect(() => {
    if (!chapter?.id) return;
    setScreenplay(null);
    setPlayingIndex(null);
    setLoadingAudio(true);
    let cancelled = false;
    (async () => {
      let sp: Screenplay | null = null;
      try {
        sp = await getScreenplay(chapter.id, "radio_play");
      } catch {
        try { sp = await getScreenplay(chapter.id, "faithful"); } catch { /* none */ }
      }
      if (!cancelled) {
        setScreenplay(sp);
        setLoadingAudio(false);
      }
    })();
    return () => { cancelled = true; };
  }, [chapter?.id]);

  // Update the listening bookmark when the user lands on a chapter so the
  // library "Continue" button knows where they are. Bookmark = num - 1
  // because the bookmark means "last chapter listened through".
  useEffect(() => {
    if (!id || !num || num < 2) return;
    updateBookmark(id, num - 1).catch(() => {});
  }, [id, num]);

  // Stop any in-flight audio when the user navigates away or chapter changes.
  // Without this the audio keeps playing into the next chapter's load screen.
  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    setPlayingIndex(null);
  }, []);

  useEffect(() => () => stopAudio(), [stopAudio]);
  useEffect(() => { stopAudio(); }, [num, stopAudio]);

  const goToChapter = useCallback((n: number) => {
    if (n >= 1 && n <= totalChapters) {
      stopAudio();
      router.push(`/book/${id}/read/${n}`);
    }
  }, [id, totalChapters, router, stopAudio]);

  // Find the next playable segment (one with audio_url) at or after `from`.
  const nextPlayableFrom = useCallback((segments: ScreenplaySegment[], from: number) => {
    return segments.findIndex((s, i) => i >= from && s.audio_url);
  }, []);

  // Play a specific segment. Must be invoked synchronously from a click event
  // for autoplay to work in mobile browsers.
  const playSegment = useCallback((index: number, segments: ScreenplaySegment[]) => {
    // Tear down any existing audio element first
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    const seg = segments[index];
    if (!seg?.audio_url) {
      // Skip to next playable segment if this one is silent (sound cue, missing audio)
      const next = nextPlayableFrom(segments, index + 1);
      if (next === -1) { setPlayingIndex(null); return; }
      playSegment(next, segments);
      return;
    }

    const audio = new Audio(buildAudioUrl(seg.audio_url));
    audio.playbackRate = ttsSpeed;
    audioRef.current = audio;
    setPlayingIndex(index);

    // Scroll the active segment into view if it has a DOM ref
    const node = segmentRefs.current[index];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    audio.play().catch(() => {
      // Autoplay rejected — fall back to "ready, click to play" state
      audioRef.current = null;
      setPlayingIndex(null);
    });

    audio.onended = () => {
      audioRef.current = null;
      const next = nextPlayableFrom(segments, index + 1);
      if (next !== -1) {
        playSegment(next, segments);  // event handler — autoplay allowed
      } else {
        setPlayingIndex(null);
        // Auto-advance to the next chapter if there is one
        if (num < totalChapters) {
          // Small delay so the "finished" state is visible for a moment
          setTimeout(() => goToChapter(num + 1), 800);
        }
      }
    };
    audio.onerror = () => {
      audioRef.current = null;
      // Skip past broken segment
      const next = nextPlayableFrom(segments, index + 1);
      if (next !== -1) playSegment(next, segments);
      else setPlayingIndex(null);
    };
  }, [ttsSpeed, num, totalChapters, goToChapter, nextPlayableFrom]);

  // Live-update playback rate when user changes ttsSpeed mid-playback
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = ttsSpeed;
  }, [ttsSpeed]);

  // Aggregate audio info — drives whether we render audio controls at all
  const playableSegments = (screenplay?.segments || []).filter((s) => s.audio_url);
  const hasAudio = playableSegments.length > 0;
  const audioComplete = screenplay?.audio_status === "complete";

  // Toggle play/pause from any control
  const togglePlay = useCallback(() => {
    if (!screenplay) return;
    if (playingIndex !== null) {
      stopAudio();
    } else {
      const first = nextPlayableFrom(screenplay.segments, 0);
      if (first !== -1) playSegment(first, screenplay.segments);
    }
  }, [screenplay, playingIndex, stopAudio, nextPlayableFrom, playSegment]);

  const skipBack = useCallback(() => {
    if (!screenplay || playingIndex === null) return;
    // Find previous playable segment
    for (let i = playingIndex - 1; i >= 0; i--) {
      if (screenplay.segments[i].audio_url) { playSegment(i, screenplay.segments); return; }
    }
  }, [screenplay, playingIndex, playSegment]);

  const skipForward = useCallback(() => {
    if (!screenplay || playingIndex === null) return;
    const next = nextPlayableFrom(screenplay.segments, playingIndex + 1);
    if (next !== -1) playSegment(next, screenplay.segments);
  }, [screenplay, playingIndex, nextPlayableFrom, playSegment]);

  // Keyboard nav — arrow keys for chapter, space for play/pause
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowLeft") goToChapter(num - 1);
      else if (e.key === "ArrowRight") goToChapter(num + 1);
      else if (e.key === " " && hasAudio) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [num, goToChapter, hasAudio, togglePlay]);

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

  // Currently-playing segment — used by the bottom player to show context
  const playingSeg = playingIndex !== null ? screenplay?.segments[playingIndex] : null;
  // Index among PLAYABLE segments only — for "5 / 42" display
  const playablePosition = playingIndex !== null
    ? playableSegments.findIndex((s) => s.id === screenplay?.segments[playingIndex]?.id) + 1
    : 0;

  return (
    <div className={cn("min-h-screen transition-colors duration-300", bgClass)}>
      {/* Reader nav */}
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

        {/* Settings panel — ereader-style toolbar */}
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

              {/* TTS speed */}
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 opacity-50" aria-label="TTS speed" />
                <select
                  value={ttsSpeed}
                  onChange={(e) => setTtsSpeed(parseFloat(e.target.value))}
                  className="bg-ink-100/10 hover:bg-ink-100/20 border border-ink-200/10 rounded-lg px-2 h-9 text-xs font-mono cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-warm/40"
                  title="Audio playback speed"
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

      {/* Chapter content — pad bottom to clear the sticky audio bar */}
      <main className={cn(
        "max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12",
        hasAudio && "pb-32 sm:pb-28"
      )}>
        {/* Chapter header */}
        <div className="mb-8 sm:mb-12 text-center">
          <span className="font-ui text-xs uppercase tracking-[0.2em] opacity-40">
            Chapter {num}
          </span>
          <h1 className="font-display text-2xl sm:text-3xl font-bold mt-2">
            {chapter?.title || `Chapter ${num}`}
          </h1>

          {/* Audio CTA — appears only after we know whether audio exists.
              When audio exists we offer a big Listen button; when it doesn't
              we show a quiet hint so the user knows the Studio can make one. */}
          {!loadingAudio && hasAudio && (
            <button
              onClick={togglePlay}
              className={cn(
                "mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-full font-ui text-sm font-medium transition-all min-h-[44px]",
                playingIndex !== null
                  ? "bg-amber-warm/20 text-amber-warm hover:bg-amber-warm/30"
                  : "bg-amber-warm text-ink-950 hover:bg-amber-warm/90 shadow-md"
              )}
            >
              {playingIndex !== null
                ? <><Pause className="w-4 h-4" /> Pause</>
                : <><Play className="w-4 h-4 fill-current" /> Listen to this chapter</>
              }
              <span className="opacity-60 text-xs ml-1">
                · {playableSegments.length} segments
                {!audioComplete && screenplay?.audio_status === "partial" && " (partial)"}
              </span>
            </button>
          )}
          {!loadingAudio && !hasAudio && (
            <p className="mt-5 font-ui text-xs opacity-40 max-w-sm mx-auto">
              No audio yet for this chapter — open the Studio (top-right of the book page) to generate it.
            </p>
          )}
        </div>

        {/* Reading body.
            When we have a screenplay, render the segments in book-prose form
            so the visible text matches the audio exactly (and we can highlight
            the active line). When we don't, fall back to the raw text from
            the source file. */}
        <div
          className="reader-content mx-auto"
          style={{
            fontSize: `${readerFontSize}px`,
            fontFamily: fontStack,
            lineHeight: readerLineHeight,
          }}
        >
          {screenplay && screenplay.segments.length > 0 ? (
            <SegmentProse
              segments={screenplay.segments}
              playingIndex={playingIndex}
              onPlaySegment={(idx) => playSegment(idx, screenplay.segments)}
              segmentRefs={segmentRefs}
            />
          ) : (
            chapter?.raw_text?.split("\n\n").map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))
          )}
        </div>

        {/* Chapter navigation */}
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

      {/* Sticky bottom audio player.
          Only mounts when we actually have audio for this chapter — keeps
          the reader chrome out of the way when there's nothing to play.
          Theming follows the reader theme via bg-inherit + backdrop-blur. */}
      {hasAudio && (
        <div className="fixed inset-x-0 bottom-0 z-40 backdrop-blur-xl bg-inherit/85 border-t border-ink-200/10 dark:border-ink-800/30 shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">
          <div className="max-w-4xl mx-auto px-3 sm:px-6 py-2.5 sm:py-3 flex items-center gap-3 sm:gap-4">
            {/* Headphones icon as audio mode indicator */}
            <div className={cn(
              "w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center flex-shrink-0",
              playingIndex !== null ? "bg-amber-warm/20" : "bg-ink-200/20"
            )}>
              {playingIndex !== null
                ? <Volume2 className="w-4 h-4 text-amber-warm animate-pulse" />
                : <Headphones className="w-4 h-4 opacity-60" />
              }
            </div>

            {/* Now-playing snippet — truncates so long lines never wrap the bar */}
            <div className="flex-1 min-w-0">
              {playingSeg ? (
                <>
                  <p className="font-ui text-[11px] sm:text-xs opacity-60 truncate">
                    {playingSeg.character_name ? playingSeg.character_name : "Narrator"}
                    <span className="opacity-50"> · {playablePosition} / {playableSegments.length}</span>
                  </p>
                  <p className="font-ui text-xs sm:text-sm truncate mt-0.5">
                    {playingSeg.text}
                  </p>
                </>
              ) : (
                <p className="font-ui text-xs sm:text-sm opacity-60 truncate">
                  Tap play to listen along · {playableSegments.length} segments
                  {ttsSpeed !== 1.0 && <span className="opacity-70"> · {ttsSpeed}×</span>}
                </p>
              )}
            </div>

            {/* Transport controls — bigger touch targets on mobile */}
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={skipBack}
                disabled={playingIndex === null || playingIndex === 0}
                className="w-10 h-10 sm:w-11 sm:h-11 rounded-full flex items-center justify-center hover:bg-ink-100/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Previous segment"
              >
                <SkipBack className="w-4 h-4" />
              </button>
              <button
                onClick={togglePlay}
                className={cn(
                  "w-12 h-12 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all",
                  playingIndex !== null
                    ? "bg-amber-warm/20 text-amber-warm hover:bg-amber-warm/30"
                    : "bg-amber-warm text-ink-950 hover:bg-amber-warm/90"
                )}
                aria-label={playingIndex !== null ? "Pause" : "Play"}
              >
                {playingIndex !== null
                  ? <Pause className="w-5 h-5" />
                  : <Play className="w-5 h-5 fill-current ml-0.5" />}
              </button>
              <button
                onClick={skipForward}
                disabled={playingIndex === null}
                className="w-10 h-10 sm:w-11 sm:h-11 rounded-full flex items-center justify-center hover:bg-ink-100/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Next segment"
              >
                <SkipForward className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SegmentProse — renders screenplay segments as plain book prose.
//
// Goal: visually look like a normal book, not a screenplay editor. So:
//   - narration → plain paragraph
//   - dialogue  → indented paragraph in quotes, with a light "— Character"
//                 attribution after the line (suppressed if back-to-back
//                 lines from the same speaker)
//   - sound_cue → small italic centered marker
//
// The currently-playing segment gets a soft amber highlight + a click
// handler to seek there.
// ---------------------------------------------------------------------------
function SegmentProse({
  segments,
  playingIndex,
  onPlaySegment,
  segmentRefs,
}: {
  segments: ScreenplaySegment[];
  playingIndex: number | null;
  onPlaySegment: (idx: number) => void;
  segmentRefs: React.MutableRefObject<Record<number, HTMLDivElement | null>>;
}) {
  return (
    <>
      {segments.map((seg, i) => {
        const isActive = playingIndex === i;
        const hasAudio = !!seg.audio_url;
        const prevSpeaker = i > 0 ? segments[i - 1].character_name : null;
        const sameSpeakerAsPrev =
          seg.type === "dialogue" && seg.character_name === prevSpeaker;

        const baseCls = cn(
          "transition-colors duration-300 rounded-md -mx-2 px-2 py-1",
          hasAudio && "cursor-pointer hover:bg-amber-warm/5",
          isActive && "bg-amber-warm/15"
        );

        if (seg.type === "sound_cue") {
          return (
            <div
              key={seg.id || i}
              ref={(el) => { segmentRefs.current[i] = el; }}
              onClick={() => hasAudio && onPlaySegment(i)}
              className={cn(baseCls, "text-center italic opacity-50 my-4 text-sm")}
            >
              [ {seg.text} ]
            </div>
          );
        }

        if (seg.type === "narration") {
          return (
            <div
              key={seg.id || i}
              ref={(el) => { segmentRefs.current[i] = el; }}
              onClick={() => hasAudio && onPlaySegment(i)}
              className={baseCls}
            >
              <p>{seg.text}</p>
            </div>
          );
        }

        // Dialogue — wrap in quotes and add attribution after the line.
        // Quotes are only added if the segment text doesn't already start
        // with one, so we don't double-quote audiobook-mode segments.
        const text = seg.text.trim();
        const startsWithQuote = /^[“"'‘]/.test(text);
        const display = startsWithQuote ? text : `“${text}”`;
        return (
          <div
            key={seg.id || i}
            ref={(el) => { segmentRefs.current[i] = el; }}
            onClick={() => hasAudio && onPlaySegment(i)}
            className={baseCls}
          >
            <p>
              {display}
              {seg.character_name && !sameSpeakerAsPrev && (
                <span className="opacity-50 text-sm ml-2">— {seg.character_name}</span>
              )}
            </p>
          </div>
        );
      })}
    </>
  );
}
