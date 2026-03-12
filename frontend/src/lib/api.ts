/**
 * StoryVox API client — communicates with the FastAPI backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  created_at: string;
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
}

export interface Screenplay {
  id: string;
  chapter_id: string;
  mode: string;
  status: string;
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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// === Books ===

export async function uploadBook(file: File): Promise<Book> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/books`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "Upload failed");
  }

  return res.json();
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
