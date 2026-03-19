/**
 * StoryVox API client — communicates with the FastAPI backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Wake up Render's free-tier server (it sleeps after 15 min of inactivity). */
export async function pingServer(): Promise<boolean> {
  try {
    await fetch(`${API_URL}/api/books`, { method: "GET" });
    return true;
  } catch {
    return false;
  }
}

export interface Book {
  id: string;
  title: string;
  author: string;
  language: string;
  cover_url: string | null;
  total_chapters: number;
  total_words: number;
  description: string | null;
  status: string;
  listen_bookmark: number;
  batch_status: string;
  batch_progress: BatchProgress | null;
  created_at: string;
}

export interface BatchProgress {
  current_chapter: number | null;
  current_index: number;
  total_in_batch: number;
  completed: string[];
  failed: string[];
  chapter_numbers?: number[];
  error?: string;
}

export interface BatchStatus {
  book_id: string;
  listen_bookmark: number;
  batch_status: string;
  batch_progress: BatchProgress | null;
  total_chapters: number;
  chapters: ChapterStatus[];
}

export interface ChapterStatus {
  number: number;
  title: string | null;
  chapter_id: string;
  status: string;
  screenplay_status: string | null;
  audio_status: string | null;
  score: number | null;
  is_non_story?: boolean;
}

export interface Chapter {
  id: string;
  book_id: string;
  number: number;
  title: string | null;
  word_count: number;
  status: string;
  raw_text?: string;
}

export interface Character {
  id: string;
  book_id: string;
  name: string;
  aliases: string[];
  gender: string | null;
  age_range: string | null;
  personality: string[];
  speech_patterns: Record<string, string>;
  frequency: string;
  relationships: Array<{ character: string; relation: string }>;
  color_hex: string | null;
  voice_id: string | null;
}

export interface ScreenplaySegment {
  id: string;
  order_index: number;
  type: "dialogue" | "narration" | "sound_cue";
  character_name: string | null;
  text: string;
  emotion: string;
  audio_url: string | null;
}

export interface Screenplay {
  id: string;
  chapter_id: string;
  mode: string;
  status: string;
  audio_status: string;
  total_rounds: number;
  final_scores: Record<string, number> | null;
  weighted_avg: number | null;
  segments: ScreenplaySegment[];
}

export interface RevisionRound {
  id: string;
  round_number: number;
  scores: Record<string, number>;
  weighted_avg: number | null;
  approved: boolean;
  is_best: boolean;
  critique: {
    summary?: string;
    strengths?: string[];
    revision_notes?: Array<{
      criterion: string;
      severity: string;
      segments: number[];
      note: string;
    }>;
  };
}

// Retry delays (ms) — transient 503 from deploys, etc.  Keep short since
// the starter plan does NOT cold-start; long waits just frustrate.
const RETRY_DELAYS = [2_000, 4_000, 8_000]; // ~14s total budget (3 retries)

async function request<T>(path: string, options?: RequestInit, retries = 3): Promise<T> {
  // Don't send Content-Type on GET/HEAD — no body, and the header triggers a CORS preflight.
  const method = (options?.method || "GET").toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const baseHeaders: Record<string, string> = hasBody
    ? { "Content-Type": "application/json" }
    : {};

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const t0 = Date.now();
      const res = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: { ...baseHeaders, ...options?.headers },
      });
      const elapsed = Date.now() - t0;

      if (!res.ok) {
        const isUnavailable = res.status === 503 || res.status === 502 || res.status === 504;
        const isLast = attempt === retries;
        console.warn(`[StoryVox] ${method} ${path} → ${res.status} (${elapsed}ms, attempt ${attempt + 1}/${retries + 1})`);
        if (isUnavailable && !isLast) {
          await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt] ?? 8_000));
          continue;
        }
        const body = await res.text().catch(() => "");
        let detail: string;
        try { detail = JSON.parse(body).detail; } catch { detail = ""; }
        if (isUnavailable) {
          throw new Error(`Server returned ${res.status} for ${method} ${path}. Response: ${body.slice(0, 200)}`);
        }
        throw new Error(detail || `API error ${res.status}: ${body.slice(0, 200)}`);
      }

      if (attempt > 0) {
        console.info(`[StoryVox] ${method} ${path} → ${res.status} OK after ${attempt + 1} attempts (${elapsed}ms)`);
      }
      return res.json();
    } catch (e: any) {
      const isNetworkError = e instanceof TypeError && (
        e.message.includes("fetch") || e.message.includes("network") || e.message.includes("Network")
      );
      const isLast = attempt === retries;
      if (isNetworkError && !isLast) {
        console.warn(`[StoryVox] ${method} ${path} → NETWORK ERROR: ${e.message} (attempt ${attempt + 1}/${retries + 1})`);
        await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt] ?? 8_000));
        continue;
      }
      if (isNetworkError) {
        throw new Error(`Network error on ${method} ${path}: ${e.message}`);
      }
      throw e;
    }
  }
  throw new Error(`Request failed after ${retries + 1} attempts: ${method} ${path}`);
}

// === Books ===

export async function uploadBook(file: File): Promise<Book> {
  const formData = new FormData();
  formData.append("file", file);

  for (let attempt = 0; attempt <= 3; attempt++) {
    const res = await fetch(`${API_URL}/api/books`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const isUnavailable = res.status === 503 || res.status === 502 || res.status === 504;
      if (isUnavailable && attempt < 3) {
        console.warn(`[StoryVox] POST /api/books → ${res.status} (attempt ${attempt + 1}/4)`);
        await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt] ?? 8_000));
        continue;
      }
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || "Upload failed");
    }

    return res.json();
  }

  throw new Error("Upload failed after retries");
}

export async function getBooks(): Promise<Book[]> {
  return request("/api/books");
}

export async function getBook(id: string): Promise<Book> {
  return request(`/api/books/${id}`);
}

export async function deleteBook(id: string): Promise<void> {
  await request(`/api/books/${id}`, { method: "DELETE" });
}

// === Chapters ===

export async function getChapters(bookId: string): Promise<Chapter[]> {
  return request(`/api/books/${bookId}/chapters`);
}

export async function getChapter(bookId: string, chapterNum: number): Promise<Chapter> {
  return request(`/api/books/${bookId}/chapters/${chapterNum}`);
}

// === Characters ===

export async function detectCharacters(bookId: string): Promise<Character[]> {
  return request(`/api/books/${bookId}/characters`, { method: "POST" });
}

export async function getCharacters(bookId: string): Promise<Character[]> {
  return request(`/api/books/${bookId}/characters`);
}

export async function updateCharacterVoice(
  bookId: string,
  characterId: string,
  voiceId: string
): Promise<Character> {
  return request(`/api/books/${bookId}/characters/${characterId}`, {
    method: "PATCH",
    body: JSON.stringify({ voice_id: voiceId }),
  });
}

export interface Voice {
  id: string;
  label: string;
  gender: string;
  accent: string;
  description: string;
}

export async function getVoices(): Promise<Voice[]> {
  return request("/api/voices");
}

// === Screenplay ===

export async function generateScreenplay(
  chapterId: string,
  mode: string = "radio_play"
): Promise<Screenplay> {
  return request(`/api/chapters/${chapterId}/screenplay?mode=${mode}`, {
    method: "POST",
  });
}

export async function getScreenplay(
  chapterId: string,
  mode: string = "radio_play"
): Promise<Screenplay> {
  return request(`/api/chapters/${chapterId}/screenplay?mode=${mode}`);
}

export async function getRevisions(
  chapterId: string,
  mode: string = "radio_play"
): Promise<RevisionRound[]> {
  return request(`/api/chapters/${chapterId}/screenplay/revisions?mode=${mode}`);
}

export async function deleteScreenplay(
  chapterId: string,
  mode: string = "radio_play"
): Promise<void> {
  await request(`/api/chapters/${chapterId}/screenplay?mode=${mode}`, {
    method: "DELETE",
  });
}

export async function generateAudio(
  chapterId: string,
  mode: string = "radio_play",
  force: boolean = false
): Promise<Screenplay> {
  return request(`/api/chapters/${chapterId}/screenplay/audio?mode=${mode}&force=${force}`, {
    method: "POST",
  });
}

// === Batch Processing ===

export async function batchGenerate(
  bookId: string,
  options?: { count?: number; startFrom?: number; audio?: boolean; mode?: string }
): Promise<Book> {
  const params = new URLSearchParams();
  params.set("mode", options?.mode || "radio_play");
  if (options?.count) params.set("count", String(options.count));
  if (options?.startFrom !== undefined) params.set("start_from", String(options.startFrom));
  if (options?.audio !== undefined) params.set("audio", String(options.audio));
  return request(`/api/books/${bookId}/batch/generate?${params}`, { method: "POST" });
}

export async function getBatchStatus(bookId: string): Promise<BatchStatus> {
  return request(`/api/books/${bookId}/batch/status`);
}

export async function stopBatch(bookId: string): Promise<void> {
  await request(`/api/books/${bookId}/batch/stop`, { method: "POST" });
}

export async function resetBatch(bookId: string): Promise<void> {
  await request(`/api/books/${bookId}/batch/reset`, { method: "POST" });
}

export async function updateBookmark(bookId: string, chapterNum: number): Promise<void> {
  await request(`/api/books/${bookId}/bookmark?chapter_num=${chapterNum}`, { method: "PATCH" });
}

// === Helpers ===

export function getCoverUrl(coverPath: string | null): string {
  if (!coverPath) return "";
  if (coverPath.startsWith("http")) return coverPath;
  return `${API_URL}${coverPath}`;
}

export function formatWordCount(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k words`;
  return `${count} words`;
}

export function formatDuration(words: number): string {
  // Average reading speed ~250 wpm, listening ~150 wpm
  const mins = Math.ceil(words / 150);
  if (mins >= 60) {
    const hrs = Math.floor(mins / 60);
    const rem = mins % 60;
    return `${hrs}h ${rem}m`;
  }
  return `${mins} min`;
}
