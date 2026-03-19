"""
Screenplay Pipeline — Writer/Director dual-LLM feedback loop.

Writer (cheap/fast) drafts the screenplay.
Director (smart/analytical) critiques it.
Loop until approved or max rounds.

Optimisations:
- Cloud providers: larger chunks (30k chars), 2 revision rounds
- Local Ollama: small chunks (3k chars), Writer-only single pass, Director skipped
"""
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from .gemini_client import GeminiClient, LLMClient
from .prompts import (
    WRITER_SYSTEM_PROMPT, WRITER_R1_PROMPT, WRITER_REVISION_PROMPT,
    WRITER_LOCAL_PROMPT,
    DIRECTOR_SYSTEM_PROMPT, DIRECTOR_PROMPT,
    SOUND_DESIGNER_PROMPT,
    FAITHFUL_MODE_INSTRUCTIONS, RADIO_PLAY_MODE_INSTRUCTIONS,
)
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class RevisionRoundResult:
    round_number: int
    screenplay: list[dict]
    critique: dict
    scores: dict
    weighted_avg: float
    approved: bool


@dataclass
class PipelineResult:
    final_screenplay: list[dict]
    rounds: list[RevisionRoundResult]
    total_rounds: int
    final_scores: dict
    final_weighted_avg: float
    best_round: int
    sound_plan: Optional[dict] = None


class ScreenplayPipeline:
    MAX_ROUNDS = 3
    CHUNK_OVERLAP = 200
    WEIGHTS = {
        "dialogue_authenticity": 0.25,
        "pacing_rhythm": 0.20,
        "character_voice_consistency": 0.25,
        "emotional_arc": 0.20,
        "faithfulness": 0.10,
    }

    def __init__(self, writer: LLMClient, director: LLMClient):
        self.writer = writer
        self.director = director

    def _get_chunk_size(self) -> int:
        """Use large chunks for cloud providers, small for local Ollama."""
        if self.writer.is_local or self.director.is_local:
            return settings.screenplay_chunk_size_local
        return settings.screenplay_chunk_size_cloud

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks, preferring paragraph boundaries."""
        chunk_size = self._get_chunk_size()
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break

            # Prefer paragraph boundary
            last_break = text.rfind("\n\n", start, end)
            if last_break != -1 and last_break > start + (chunk_size // 2):
                end = last_break + 2

            chunks.append(text[start:end])
            start = end - self.CHUNK_OVERLAP
        return chunks

    async def process_chapter(
        self,
        chapter_text: str,
        character_bible: list[dict],
        mode: str = "radio_play",
        on_round_complete: Optional[Callable[[RevisionRoundResult], Awaitable]] = None,
    ) -> PipelineResult:
        """Run the full Writer(/Director) loop for a chapter."""

        is_local = self.writer.is_local or self.director.is_local
        char_bible_str = json.dumps(character_bible, indent=2)
        chunks = self._chunk_text(chapter_text)

        logger.info(
            f"Pipeline: {len(chunks)} chunk(s), mode={mode}, chunk_size={self._get_chunk_size()}, "
            f"{'LOCAL fast-path (Writer only)' if is_local else 'CLOUD Writer+Director loop'}, "
            f"writer={type(self.writer).__name__}, director={type(self.director).__name__}"
        )

        if is_local:
            return await self._process_local(chunks, char_bible_str)
        else:
            return await self._process_cloud(chunks, char_bible_str, mode)

    # ------------------------------------------------------------------ #
    #  LOCAL fast-path: Writer only, no Director, sequential for continuity
    # ------------------------------------------------------------------ #

    async def _process_local(
        self,
        chunks: list[str],
        char_bible_str: str,
    ) -> PipelineResult:
        """
        Lightweight single-pass pipeline for local Ollama models.
        Skips the Director entirely to avoid doubling slow LLM calls.
        """
        from .schemas import ScreenplayDraft

        all_segments: list[dict] = []
        dummy_scores = {k: 5.0 for k in self.WEIGHTS}

        for chunk_idx, chunk_text in enumerate(chunks):
            logger.info(f"LOCAL chunk {chunk_idx + 1}/{len(chunks)}")

            # Add continuity hint from previous segments
            continuity = ""
            if all_segments:
                last = all_segments[-3:]
                continuity = (
                    f"CONTINUITY — last segments written:\n{json.dumps(last, indent=2)}\n\n"
                    f"Continue the story from here.\n\n"
                )

            prompt = continuity + WRITER_LOCAL_PROMPT.format(
                character_bible=char_bible_str,
                chapter_text=chunk_text,
            )

            try:
                result = await self.writer.generate_json(
                    WRITER_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.7,
                    response_schema=ScreenplayDraft,
                )
            except Exception as e:
                logger.error(f"LOCAL Writer failed on chunk {chunk_idx}: {e}")
                continue

            if isinstance(result, dict):
                segments = result.get("segments", [])
            elif isinstance(result, list):
                segments = result
            else:
                segments = []

            segments = self._validate_segments(segments)
            all_segments.extend(segments)

        # Guard: if Ollama returned nothing useful, fail loudly instead of saving empty screenplay
        if not all_segments:
            raise RuntimeError(
                "Local pipeline produced 0 segments. "
                "Ollama may have returned empty JSON ({}). "
                "Try a larger model or switch to a cloud provider."
            )

        dummy_round = RevisionRoundResult(
            round_number=1,
            screenplay=all_segments,
            critique={"summary": "Local mode — Director phase skipped"},
            scores=dummy_scores,
            weighted_avg=5.0,
            approved=True,
        )

        return PipelineResult(
            final_screenplay=all_segments,
            rounds=[dummy_round],
            total_rounds=1,
            final_scores=dummy_scores,
            final_weighted_avg=5.0,
            best_round=1,
            sound_plan=None,
        )

    # ------------------------------------------------------------------ #
    #  CLOUD revision loop: Writer + Director
    # ------------------------------------------------------------------ #

    async def _process_cloud(
        self,
        chunks: list[str],
        char_bible_str: str,
        mode: str,
    ) -> PipelineResult:
        """
        Full Writer/Director loop for cloud providers (Gemini/Groq).
        Chunks are processed sequentially to maintain narrative continuity
        (each chunk's prompt includes the last 3 segments of the previous chunk).
        """
        from .schemas import ScreenplayDraft, DirectorCritique

        mode_instructions = (
            FAITHFUL_MODE_INSTRUCTIONS if mode == "faithful"
            else RADIO_PLAY_MODE_INSTRUCTIONS
        )

        all_segments: list[dict] = []
        all_rounds: list[RevisionRoundResult] = []

        for chunk_idx, chunk_text in enumerate(chunks):
            logger.info(f"CLOUD chunk {chunk_idx + 1}/{len(chunks)}")

            previous_critique: Optional[dict] = None
            previous_draft: Optional[list] = None
            chunk_best_round: Optional[RevisionRoundResult] = None
            chunk_best_avg = -1.0

            continuity_context = ""
            if all_segments:
                last_segs = all_segments[-3:]
                continuity_context = (
                    f"CONTINUITY: The last few segments written were:\n"
                    f"{json.dumps(last_segs, indent=2)}\n\nContinue the story from here."
                )

            for round_num in range(1, self.MAX_ROUNDS + 1):
                logger.info(f"  Round {round_num}/{self.MAX_ROUNDS}")

                # === WRITER ===
                if round_num == 1:
                    prompt = WRITER_R1_PROMPT.format(
                        mode=mode,
                        mode_instructions=mode_instructions,
                        character_bible=char_bible_str,
                        chapter_text=chunk_text,
                    )
                    if continuity_context:
                        prompt = f"{continuity_context}\n\n{prompt}"
                else:
                    revision_items = self._format_revision_items(previous_critique)
                    prompt = WRITER_REVISION_PROMPT.format(
                        chapter_text=chunk_text,
                        previous_draft=json.dumps(previous_draft),
                        critique=json.dumps(previous_critique.get("revision_notes", [])),
                        revision_items=revision_items,
                    )

                try:
                    logger.info(f"  Writer call: chunk={chunk_idx} round={round_num} prompt_len={len(prompt)}")
                    result = await self.writer.generate_json(
                        WRITER_SYSTEM_PROMPT,
                        prompt,
                        temperature=0.7 if round_num == 1 else 0.5,
                        response_schema=ScreenplayDraft,
                    )
                    logger.info(f"  Writer returned: type={type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'list'}")
                except Exception as e:
                    logger.error(f"Writer failed chunk {chunk_idx} round {round_num}: {type(e).__name__}: {e}")
                    break

                if isinstance(result, dict):
                    screenplay = result.get("segments", [])
                    # Ollama sometimes returns a single segment object — wrap it
                    if not screenplay and "type" in result and "text" in result:
                        screenplay = [result]
                elif isinstance(result, list):
                    screenplay = result
                else:
                    screenplay = []

                screenplay = self._validate_segments(screenplay)

                # === DIRECTOR ===
                previous_notes_section = ""
                if previous_critique:
                    previous_notes_section = (
                        f"PREVIOUS NOTES:\n{json.dumps(previous_critique.get('revision_notes', []))}\n\n"
                        f"Check whether these notes were addressed."
                    )

                director_prompt = DIRECTOR_PROMPT.format(
                    chapter_text=chunk_text,
                    screenplay=json.dumps(screenplay),
                    character_bible=char_bible_str,
                    round_number=round_num,
                    previous_notes_section=previous_notes_section,
                )

                try:
                    critique = await self.director.generate_json(
                        DIRECTOR_SYSTEM_PROMPT,
                        director_prompt,
                        temperature=0.2,
                        response_schema=DirectorCritique,
                    )
                    critique = self._normalize_critique(critique)
                except Exception as e:
                    logger.error(f"Director failed chunk {chunk_idx} round {round_num}: {e}")
                    critique = {"scores": {k: 5 for k in self.WEIGHTS}, "revision_notes": []}

                scores = critique.get("scores", {})
                weighted_avg = self._calc_weighted_avg(scores)

                round_result = RevisionRoundResult(
                    round_number=round_num,
                    screenplay=screenplay,
                    critique=critique,
                    scores=scores,
                    weighted_avg=weighted_avg,
                    approved=(round_num == self.MAX_ROUNDS),
                )

                if weighted_avg >= chunk_best_avg:
                    chunk_best_avg = weighted_avg
                    chunk_best_round = round_result

                previous_critique = critique
                previous_draft = screenplay

                # Early exit if quality is already excellent
                if self._should_approve(scores, round_num):
                    logger.info(f"  Director approved at round {round_num} (score {weighted_avg:.2f})")
                    break

            if chunk_best_round:
                all_segments.extend(chunk_best_round.screenplay)
                all_rounds.append(chunk_best_round)

        # Guard: if all providers failed or returned nothing, raise so batch marks chapter as failed
        if not all_segments:
            raise RuntimeError(
                "Cloud pipeline produced 0 segments across all chunks. "
                "All LLM providers may have failed or hit quota limits."
            )

        # Aggregate scores across all best rounds
        final_scores = {k: 0.0 for k in self.WEIGHTS}
        for rnd in all_rounds:
            for k in self.WEIGHTS:
                final_scores[k] += rnd.scores.get(k, 5)

        if all_rounds:
            final_scores = {k: round(v / len(all_rounds), 1) for k, v in final_scores.items()}
        else:
            final_scores = {k: 5.0 for k in self.WEIGHTS}

        final_weighted_avg = self._calc_weighted_avg(final_scores)

        # === SOUND DESIGNER ===
        sound_plan = None
        try:
            from .schemas import SoundPlan
            logger.info("Running Sound Designer…")
            # Truncate to ~first 60 segments to stay within token limits
            # but never break mid-JSON
            segments_for_sound = all_segments[:60]
            sound_prompt = SOUND_DESIGNER_PROMPT.format(
                screenplay=json.dumps(segments_for_sound),
                chapter_text="",
            )
            sound_plan = await self.director.generate_json(
                "You are a professional Sound Designer for radio play productions.",
                sound_prompt,
                temperature=0.3,
                response_schema=SoundPlan,
            )
        except Exception as e:
            logger.warning(f"Sound Designer skipped: {e}")

        return PipelineResult(
            final_screenplay=all_segments,
            rounds=all_rounds,
            total_rounds=len(all_rounds),
            final_scores=final_scores,
            final_weighted_avg=final_weighted_avg,
            best_round=1,
            sound_plan=sound_plan,
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _should_approve(self, scores: dict, round_number: int) -> bool:
        if round_number >= self.MAX_ROUNDS:
            return True
        vals = list(scores.values())
        if not vals:
            return False
        if min(vals) <= 3:
            return False
        if scores.get("faithfulness", 5) < 5:
            return False
        weighted_avg = self._calc_weighted_avg(scores)
        if all(v >= 7 for v in vals) and weighted_avg >= settings.approval_threshold:
            return True
        if weighted_avg >= 8.0:
            return True
        return False

    def _calc_weighted_avg(self, scores: dict) -> float:
        total = 0.0
        for key, weight in self.WEIGHTS.items():
            total += scores.get(key, 5) * weight
        return round(total, 2)

    def _normalize_critique(self, critique: dict) -> dict:
        """
        Normalize director responses from different LLMs.

        Different LLMs use different key names:
          - Gemini (schema-aware): {"scores": {"faithfulness": 7, ...}, "revision_notes": [...]}
          - Groq (no schema):      {"evaluation": {"faithfulness_to_source": 4, ...}, "feedback": {...}}
          - Ollama:                 varies wildly

        This normalizes all of them into the canonical format.
        """
        if not isinstance(critique, dict):
            return {"scores": {k: 5 for k in self.WEIGHTS}, "revision_notes": []}

        # Normalize top-level "evaluation" → "scores"
        if "evaluation" in critique and "scores" not in critique:
            critique["scores"] = critique.pop("evaluation")
        # Normalize "feedback" → "revision_notes" (rough approximation)
        if "feedback" in critique and "revision_notes" not in critique:
            fb = critique.pop("feedback")
            if isinstance(fb, dict):
                notes = [
                    {"criterion": k, "severity": "minor", "segments": [], "note": v}
                    for k, v in fb.items() if isinstance(v, str)
                ]
                critique["revision_notes"] = notes

        # Normalize scores sub-dict
        scores = critique.get("scores", {})
        if isinstance(scores, dict):
            # faithfulness_to_source → faithfulness
            if "faithfulness_to_source" in scores and "faithfulness" not in scores:
                scores["faithfulness"] = scores.pop("faithfulness_to_source")
            # Ensure all expected keys exist with sensible defaults
            for k in self.WEIGHTS:
                if k not in scores:
                    scores[k] = 5
                else:
                    # Clamp to 1-10 range
                    try:
                        scores[k] = max(1, min(10, int(scores[k])))
                    except (TypeError, ValueError):
                        scores[k] = 5
            critique["scores"] = scores

        if "revision_notes" not in critique:
            critique["revision_notes"] = []

        return critique

    def _validate_segments(self, segments: list) -> list[dict]:
        """Ensure all segments have required fields, extract inline [SOUND:] tags, and strip empty entries."""
        import re
        valid = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            text = seg.get("text", "").strip()
            if not text:
                continue
            seg_type = seg.get("type", "narration").lower()

            # Extract [SOUND: ...] or [SFX: ...] markers from narration/dialogue text
            # and create separate sound_cue segments
            if seg_type in ("narration", "dialogue"):
                sound_pattern = r'\[(?:SOUND|SFX|PAUSE):\s*([^\]]+)\]'
                sounds = re.findall(sound_pattern, text, re.IGNORECASE)
                # Remove the markers from the text
                clean_text = re.sub(sound_pattern, '', text, flags=re.IGNORECASE).strip()
                clean_text = re.sub(r'\s{2,}', ' ', clean_text)  # collapse double spaces

                if clean_text:
                    cleaned = {
                        "type": seg_type,
                        "text": clean_text,
                        "emotion": seg.get("emotion", "neutral"),
                    }
                    char = seg.get("character") or seg.get("character_name")
                    if seg_type == "dialogue":
                        cleaned["character"] = char or "Unknown"
                    valid.append(cleaned)

                # Add extracted sounds as separate sound_cue segments
                for sound_text in sounds:
                    sound_text = sound_text.strip().rstrip(".")
                    # Truncate to 6 words max for sound cues
                    words = sound_text.split()
                    if len(words) > 6:
                        sound_text = " ".join(words[:6])
                    if sound_text:
                        valid.append({
                            "type": "sound_cue",
                            "text": sound_text,
                            "emotion": "neutral",
                        })
            else:
                # sound_cue or other types — clean up
                # Ensure sound_cue text is 2-6 words
                if seg_type == "sound_cue":
                    text = text.strip("[]").strip()
                    # Remove "SOUND:" prefix if present
                    if text.upper().startswith("SOUND:"):
                        text = text[6:].strip()
                    if text.upper().startswith("SFX:"):
                        text = text[4:].strip()
                    words = text.split()
                    if len(words) > 6:
                        text = " ".join(words[:6])
                    text = text.rstrip(".")

                cleaned = {
                    "type": seg_type,
                    "text": text,
                    "emotion": seg.get("emotion", "neutral"),
                }
                valid.append(cleaned)
        return valid

    def _format_revision_items(self, critique: dict) -> str:
        notes = critique.get("revision_notes", [])
        items = []
        for i, note in enumerate(notes, 1):
            severity = note.get("severity", "minor")
            segments = note.get("segments", [])
            text = note.get("note", "")
            items.append(f"{i}. [{severity.upper()}] Segments {segments}: {text}")
        return "\n".join(items) if items else "No specific notes."
