"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, Loader2, Play, Radio, BookOpen, Sparkles,
  CheckCircle2, RefreshCw, ChevronLeft, ChevronRight,
  Mic, Volume2, AlertCircle, Pencil, Eye
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getBook, getChapter, getChapters, getCharacters,
  getScreenplay, generateScreenplay, getRevisions, deleteScreenplay,
  generateAudio,
} from "@/lib/api";
import type { Book, Chapter, Character, Screenplay, RevisionRound, ScreenplaySegment } from "@/lib/api";

const CRITERIA_LABELS: Record<string, string> = {
  dialogue_authenticity: "Dialogue",
  pacing_rhythm: "Pacing",
  character_voice_consistency: "Voice Consistency",
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
  foreboding: "text-indigo-400",
  excited: "text-amber-400",
};

export default function ScreenplayPage() {
  const { id, chapter: chapterNum } = useParams<{ id: string; chapter: string }>();
  const router = useRouter();
  const num = parseInt(chapterNum, 10);

  const [book, setBook] = useState<Book | null>(null);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [revisions, setRevisions] = useState<RevisionRound[]>([]);
  const [currentlyPlayingIndex, setCurrentlyPlayingIndex] = useState<number | null>(null);
  const [totalChapters, setTotalChapters] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingAudio, setGeneratingAudio] = useState(false);
  const [mode, setMode] = useState<"radio_play" | "faithful">("radio_play");
  const [viewMode, setViewMode] = useState<"screenplay" | "sidebyside">("screenplay");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !num) return;
    setLoading(true);
    // Reset playback on chapter change
    setCurrentlyPlayingIndex(null);
    Promise.all([
      getBook(id).then(setBook),
      getChapter(id, num).then(setChapter),
      getChapters(id).then((chs) => setTotalChapters(chs.length)),
      getCharacters(id).then(setCharacters).catch(() => []),
    ])
      .then(async () => {
        // Try to load existing screenplay
        try {
          const sp = await getScreenplay(
            (await getChapter(id, num)).id,
            mode
          );
          setScreenplay(sp);
          if (sp.status === "complete") {
            const revs = await getRevisions(sp.chapter_id, mode);
            setRevisions(revs);
          }
        } catch {
          // No screenplay yet
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id, num, mode]);

  // Polling logic for async generation
  useEffect(() => {
    if (!screenplay || !chapter) return;
    
    const needsPolling = 
      screenplay.status === "processing" || 
      screenplay.audio_status === "processing";

    if (!needsPolling) return;

    const interval = setInterval(async () => {
      try {
        const updated = await getScreenplay(chapter.id, mode);
        setScreenplay(updated);
        
        if (updated.status === "complete" && screenplay.status === "processing") {
          const revs = await getRevisions(updated.chapter_id, mode);
          setRevisions(revs);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [screenplay?.status, screenplay?.audio_status, chapter?.id, mode]);

  const handleGenerate = async () => {
    if (!chapter) return;
    setGenerating(true);
    setError(null);
    try {
      const sp = await generateScreenplay(chapter.id, mode);
      setScreenplay(sp);
    } catch (e: any) {
      setError(e.message);
      setGenerating(false);
    }
  };

  const handleRegenerate = async () => {
    if (!chapter) return;
    try {
      await deleteScreenplay(chapter.id, mode);
      setScreenplay(null);
      setRevisions([]);
      handleGenerate();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleGenerateAudio = async (force: boolean = false) => {
    if (!screenplay) return;
    setGeneratingAudio(true);
    setError(null);
    try {
      const updated = await generateAudio(screenplay.chapter_id, mode, force);
      setScreenplay(updated);
    } catch (err: any) {
      setError(err.message);
      setGeneratingAudio(false);
    }
  };

  // Build character color map
  const charColorMap: Record<string, string> = {};
  characters.forEach((c) => {
    charColorMap[c.name] = c.color_hex || "#6B9080";
  });

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-dark">
        <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-light dark:bg-surface-dark">
      {/* Nav */}
      <nav className="border-b border-ink-200/20 dark:border-ink-800/40 bg-surface-light/80 dark:bg-surface-dark/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => router.push(`/book/${id}`)}
            className="btn-ghost flex items-center gap-2 text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            {book?.title}
          </button>

          <div className="flex items-center gap-2">
            {/* Mode toggle */}
            <div className="flex items-center bg-ink-100 dark:bg-ink-800/50 rounded-lg p-0.5">
              <button
                onClick={() => setMode("radio_play")}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-ui font-medium transition-all",
                  mode === "radio_play"
                    ? "bg-amber-warm text-ink-950 shadow-sm"
                    : "text-ink-500 hover:text-ink-700 dark:hover:text-ink-300"
                )}
              >
                <Radio className="w-3 h-3 inline mr-1" />
                Radio Play
              </button>
              <button
                onClick={() => setMode("faithful")}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-ui font-medium transition-all",
                  mode === "faithful"
                    ? "bg-amber-warm text-ink-950 shadow-sm"
                    : "text-ink-500 hover:text-ink-700 dark:hover:text-ink-300"
                )}
              >
                <BookOpen className="w-3 h-3 inline mr-1" />
                Faithful
              </button>
            </div>
          </div>
        </div>
      </nav>

      {error && (
        <div className="max-w-7xl mx-auto px-6 mt-4">
          <div className="bg-stage-red/10 border border-stage-red/20 rounded-xl px-4 py-3 flex items-center gap-2 text-sm">
            <AlertCircle className="w-4 h-4 text-stage-red" />
            <span className="text-stage-red font-ui">{error}</span>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Chapter header */}
        <div className="mb-8">
          <span className="font-ui text-xs uppercase tracking-[0.2em] text-ink-400">
            Chapter {num} — Screenplay
          </span>
          <h1 className="font-display text-2xl font-bold text-ink-950 dark:text-ink-50 mt-1">
            {chapter?.title || `Chapter ${num}`}
          </h1>
        </div>

        {(!screenplay || screenplay.status === "failed") && !generating && screenplay?.status !== "processing" ? (
          /* Generate CTA */
          <div className="text-center py-20">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-amber-warm/20 to-stage-purple/20 flex items-center justify-center mx-auto mb-6">
              <Sparkles className="w-8 h-8 text-amber-warm" />
            </div>
            <h2 className="font-display text-xl font-semibold text-ink-800 dark:text-ink-200 mb-2">
              {screenplay?.status === "failed" ? "Screenplay generation failed" : "Ready to create the screenplay"}
            </h2>
            <p className="font-ui text-ink-500 dark:text-ink-400 max-w-md mx-auto mb-8">
              {screenplay?.status === "failed" 
                ? "Something went wrong during the adaptation. You can try regenerating below."
                : `The Writer LLM will draft a ${mode === "radio_play" ? "radio play" : "faithful"} adaptation, then the Director will critique and refine it through up to 4 rounds.`}
            </p>
            <button onClick={handleRegenerate} className="btn-primary text-lg px-8 py-4">
              <Sparkles className="w-5 h-5 inline mr-2" />
              {screenplay?.status === "failed" ? "Retry Generation" : "Generate Screenplay"}
            </button>
          </div>
        ) : (generating || screenplay?.status === "processing") ? (
          /* Processing state */
          <div className="max-w-2xl mx-auto py-16">
            <div className="glass-card p-8 text-center">
              <div className="w-16 h-16 rounded-2xl bg-amber-warm/10 flex items-center justify-center mx-auto mb-6">
                <Loader2 className="w-8 h-8 text-amber-warm animate-spin" />
              </div>
              <h3 className="font-display text-xl font-semibold text-ink-800 dark:text-ink-200 mb-2">
                Writer & Director at work...
              </h3>
              <p className="font-ui text-ink-500 dark:text-ink-400 text-sm">
                The Writer is drafting the screenplay and the Director is reviewing it.
                This may take 1-3 minutes depending on chapter length.
              </p>

              <div className="mt-8 flex justify-center gap-4">
                {[1, 2, 3, 4].map((bar) => (
                  <div
                    key={bar}
                    className="w-1 bg-amber-warm/60 rounded-full animate-waveform"
                    style={{
                      animationDelay: `${bar * 0.15}s`,
                      height: "24px",
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        ) : screenplay ? (
          /* Screenplay view */
          <div>
            {/* Status & Actions card */}
            <div className="glass-card p-6 mb-8">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-stage-green" />
                    <span className="font-ui font-semibold text-ink-800 dark:text-ink-200">
                      Director&apos;s Score — Round {screenplay.total_rounds}
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    {screenplay.weighted_avg !== undefined && screenplay.weighted_avg !== null && (
                      <span className="font-display text-2xl font-bold text-amber-warm">
                        {screenplay.weighted_avg?.toFixed(1)}
                      </span>
                    )}
                    <div className="flex items-center gap-2">
                      {screenplay.audio_status !== "complete" ? (
                        <button
                          onClick={() => handleGenerateAudio(false)}
                          disabled={generatingAudio || screenplay.audio_status === "processing"}
                          className="btn-primary text-xs flex items-center gap-1.5"
                        >
                          {generatingAudio || screenplay.audio_status === "processing" ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <Mic className="w-3 h-3" />
                          )}
                          {screenplay.audio_status === "processing" ? "Producing Audio..." : "Generate Audio"}
                        </button>
                      ) : (
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1 text-xs text-stage-green font-ui">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Audio Ready
                          </div>
                          <button
                            onClick={() => handleGenerateAudio(true)}
                            disabled={generatingAudio}
                            title="Regenerate with more distinctive voices"
                            className="p-1.5 rounded-md hover:bg-ink-100 dark:hover:bg-ink-800 text-ink-400 hover:text-ink-600 transition-colors"
                          >
                            {generatingAudio ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <RefreshCw className="w-3 h-3" />
                            )}
                          </button>
                          {/* Global Play Button */}
                          <button 
                            onClick={() => {
                              const firstIdx = screenplay.segments.findIndex(s => s.audio_url);
                              if (firstIdx !== -1) {
                                setCurrentlyPlayingIndex(firstIdx);
                              }
                            }}
                            className={cn(
                              "btn-primary py-1 px-3 text-xs flex items-center gap-1.5 transition-all",
                              currentlyPlayingIndex !== null 
                                ? "bg-amber-warm text-ink-950 border-amber-warm" 
                                : "bg-stage-green hover:bg-stage-green/90"
                            )}
                          >
                            {currentlyPlayingIndex !== null ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Play className="w-3 h-3 fill-current" />
                            )}
                            {currentlyPlayingIndex !== null ? "Playing..." : "Listen Now"}
                          </button>
                        </div>
                      )}
                      <button onClick={handleRegenerate} className="btn-ghost text-xs flex items-center gap-1">
                        <RefreshCw className="w-3 h-3" />
                        Regenerate
                      </button>
                    </div>
                  </div>
                </div>

                {screenplay.final_scores && (
                  <div className="grid grid-cols-5 gap-4 mt-4">
                    {Object.entries(screenplay.final_scores).map(([key, score]) => (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-ui text-xs text-ink-500 dark:text-ink-400">
                            {CRITERIA_LABELS[key] || key}
                          </span>
                          <span className="font-mono text-xs font-semibold text-ink-700 dark:text-ink-300">
                            {score}
                          </span>
                        </div>
                        <div className="score-bar">
                          <div
                            className={cn(
                              "score-bar-fill",
                              score >= 8
                                ? "bg-stage-green"
                                : score >= 6
                                  ? "bg-amber-warm"
                                  : "bg-stage-red"
                            )}
                            style={{ width: `${(score / 10) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

            {/* Segments */}
            <div className="space-y-1">
              {screenplay.segments.map((seg, i) => (
                <SegmentCard
                  key={seg.id}
                  segment={seg}
                  index={i}
                  isPlaying={currentlyPlayingIndex === i}
                  onPlayRequested={() => setCurrentlyPlayingIndex(i)}
                  onPlaybackEnded={() => {
                    if (currentlyPlayingIndex === i) {
                      // Find next segment with audio
                      const nextIdx = screenplay.segments.findIndex((s, idx) => idx > i && s.audio_url);
                      if (nextIdx !== -1) {
                        setCurrentlyPlayingIndex(nextIdx);
                      } else {
                        setCurrentlyPlayingIndex(null);
                      }
                    }
                  }}
                  charColorMap={charColorMap}
                />
              ))}
            </div>

            {/* Chapter nav */}
            <div className="flex items-center justify-between mt-12 pt-8 border-t border-ink-200/10 dark:border-ink-800/20">
              <button
                onClick={() => router.push(`/book/${id}/screenplay/${num - 1}`)}
                disabled={num <= 1}
                className={cn(
                  "btn-ghost flex items-center gap-2",
                  num <= 1 && "opacity-30 cursor-not-allowed"
                )}
              >
                <ChevronLeft className="w-4 h-4" />
                Previous
              </button>
              <span className="font-mono text-xs text-ink-400">{num} / {totalChapters}</span>
              <button
                onClick={() => router.push(`/book/${id}/screenplay/${num + 1}`)}
                disabled={num >= totalChapters}
                className={cn(
                  "btn-ghost flex items-center gap-2",
                  num >= totalChapters && "opacity-30 cursor-not-allowed"
                )}
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}

function SegmentCard({
  segment,
  index,
  charColorMap,
  isPlaying,
  onPlayRequested,
  onPlaybackEnded,
}: {
  segment: ScreenplaySegment;
  index: number;
  charColorMap: Record<string, string>;
  isPlaying: boolean;
  onPlayRequested: () => void;
  onPlaybackEnded: () => void;
}) {
  const [localPlaying, setLocalPlaying] = useState(false);
  const audioRef = useState<HTMLAudioElement | null>(null)[0];
  const color = segment.character_name ? charColorMap[segment.character_name] : undefined;

  useEffect(() => {
    if (isPlaying && !localPlaying) {
      handlePlay();
    } else if (!isPlaying && localPlaying) {
      // Optional: stop if externally deselected
    }
  }, [isPlaying]);

  const handlePlay = () => {
    if (!segment.audio_url) {
      onPlaybackEnded();
      return;
    }
    
    let url = segment.audio_url;
    if (!url.startsWith("http")) {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const cleanBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
      const cleanPath = url.startsWith("/") ? url : `/${url}`;
      url = `${cleanBase}${cleanPath}`;
    }

    const audio = new Audio(url);
    setLocalPlaying(true);
    audio.play().catch(e => {
      console.error("Playback failed:", e);
      setLocalPlaying(false);
      onPlaybackEnded();
    });
    
    audio.onended = () => {
      setLocalPlaying(false);
      onPlaybackEnded();
    };
    audio.onerror = () => {
      setLocalPlaying(false);
      onPlaybackEnded();
    };
  };

  const PlayButton = () => {
    const hasAudio = !!segment.audio_url;
    return (
      <button
        onClick={() => {
          if (localPlaying) {
            // Stop logic could go here
          } else {
            onPlayRequested();
          }
        }}
        disabled={!hasAudio}
        className={cn(
          "ml-auto p-2.5 rounded-full transition-all flex-shrink-0 border-2",
          localPlaying 
            ? "bg-amber-warm text-ink-950 border-amber-warm shadow-lg scale-110" 
            : hasAudio
              ? "bg-stage-green/10 text-stage-green border-stage-green/30 hover:bg-stage-green hover:text-white"
              : "bg-ink-100 text-ink-300 border-transparent opacity-0 pointer-events-none"
        )}
      >
        {localPlaying ? (
          <Volume2 className="w-5 h-5 animate-pulse" />
        ) : (
          <Play className="w-5 h-5 fill-current" />
        )}
      </button>
    );
  };

  if (segment.type === "sound_cue") {
    return (
      <div className="segment-sound-cue flex items-center justify-between my-4 animate-fade-in bg-stage-blue/5 border-stage-blue/20"
        style={{ animationDelay: `${index * 20}ms` }}
      >
        <div className="flex items-center gap-3">
          <Volume2 className="w-4 h-4 text-stage-blue flex-shrink-0" />
          <span className="font-mono text-sm uppercase tracking-wider text-stage-blue">{segment.text}</span>
        </div>
        <PlayButton />
      </div>
    );
  }

  if (segment.type === "narration") {
    return (
      <div className="segment-narration animate-fade-in group flex gap-6" style={{ animationDelay: `${index * 20}ms` }}>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <BookOpen className="w-3.5 h-3.5 text-ink-400" />
            <span className="font-ui text-[10px] uppercase tracking-[0.2em] text-ink-400">Narrator</span>
            <span className={cn("text-[10px] font-ui italic", EMOTION_COLORS[segment.emotion] || "text-ink-400")}>
              ({segment.emotion})
            </span>
          </div>
          <p className="font-body text-lg leading-relaxed">{segment.text}</p>
        </div>
        <PlayButton />
      </div>
    );
  }

  // Dialogue
  return (
    <div
      className="segment-dialogue animate-fade-in group flex gap-6"
      style={{
        borderLeftColor: color || "#6B9080",
        animationDelay: `${index * 20}ms`,
      }}
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
          <span className={cn("text-[10px] font-ui italic", EMOTION_COLORS[segment.emotion] || "text-ink-400")}>
            ({segment.emotion})
          </span>
        </div>
        <p className="font-body text-lg leading-relaxed text-ink-800 dark:text-ink-200">
          {segment.text}
        </p>
      </div>
      <PlayButton />
    </div>
  );
}
