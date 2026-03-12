"""
Screenplay Pipeline — Writer/Director dual-LLM feedback loop.

Writer (cheap/fast) drafts the screenplay.
Director (smart/analytical) critiques it.
Loop until approved or max 4 rounds.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from .gemini_client import GeminiClient
from .prompts import (
    WRITER_SYSTEM_PROMPT, WRITER_R1_PROMPT, WRITER_REVISION_PROMPT,
    DIRECTOR_SYSTEM_PROMPT, DIRECTOR_PROMPT,
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


class ScreenplayPipeline:
    MAX_ROUNDS = settings.max_revision_rounds
    WEIGHTS = {
        "dialogue_authenticity": 0.25,
        "pacing_rhythm": 0.20,
        "character_voice_consistency": 0.25,
        "emotional_arc": 0.20,
        "faithfulness": 0.10,
    }

    def __init__(self, writer: GeminiClient, director: GeminiClient):
        self.writer = writer
        self.director = director

    async def process_chapter(
        self,
        chapter_text: str,
        character_bible: list[dict],
        mode: str = "radio_play",
        on_round_complete: Optional[Callable[[RevisionRoundResult], Awaitable]] = None,
    ) -> PipelineResult:
        """Run the full Writer/Director loop for a chapter."""

        mode_instructions = (
            FAITHFUL_MODE_INSTRUCTIONS if mode == "faithful"
            else RADIO_PLAY_MODE_INSTRUCTIONS
        )
        char_bible_str = json.dumps(character_bible, indent=2)
        rounds: list[RevisionRoundResult] = []
        previous_critique: Optional[dict] = None
        previous_draft: Optional[list] = None
        best_round_idx = 0
        best_avg = 0.0

        for round_num in range(1, self.MAX_ROUNDS + 1):
            logger.info(f"Starting round {round_num} for mode={mode}")

            # === WRITER PHASE ===
            try:
                if round_num == 1:
                    prompt = WRITER_R1_PROMPT.format(
                        mode=mode,
                        mode_instructions=mode_instructions,
                        character_bible=char_bible_str,
                        chapter_text=chapter_text[:12000],  # Limit context
                    )
                    screenplay = await self.writer.generate_json(
                        WRITER_SYSTEM_PROMPT, prompt, temperature=0.8
                    )
                else:
                    revision_items = self._format_revision_items(previous_critique)
                    prompt = WRITER_REVISION_PROMPT.format(
                        chapter_text=chapter_text[:8000],
                        previous_draft=json.dumps(previous_draft)[:6000],
                        critique=json.dumps(previous_critique.get("revision_notes", []))[:3000],
                        revision_items=revision_items,
                    )
                    screenplay = await self.writer.generate_json(
                        WRITER_SYSTEM_PROMPT, prompt, temperature=0.7
                    )

                # Validate screenplay structure
                if isinstance(screenplay, dict) and "segments" in screenplay:
                    screenplay = screenplay["segments"]
                if not isinstance(screenplay, list):
                    screenplay = [screenplay] if isinstance(screenplay, dict) else []

                screenplay = self._validate_segments(screenplay)

            except Exception as e:
                logger.error(f"Writer failed in round {round_num}: {e}")
                if previous_draft:
                    screenplay = previous_draft
                else:
                    screenplay = [{"type": "narration", "text": chapter_text[:500], "emotion": "neutral"}]

            # === DIRECTOR PHASE ===
            try:
                previous_notes_section = ""
                if previous_critique:
                    previous_notes_section = f"PREVIOUS NOTES:\n{json.dumps(previous_critique.get('revision_notes', []))[:2000]}\n\nCheck whether these notes were addressed."

                director_prompt = DIRECTOR_PROMPT.format(
                    chapter_text=chapter_text[:8000],
                    screenplay=json.dumps(screenplay)[:6000],
                    character_bible=char_bible_str[:3000],
                    round_number=round_num,
                    previous_notes_section=previous_notes_section,
                )
                critique = await self.director.generate_json(
                    DIRECTOR_SYSTEM_PROMPT, director_prompt, temperature=0.3
                )

                scores = critique.get("scores", {})
                weighted_avg = self._calc_weighted_avg(scores)
                critique["weighted_average"] = weighted_avg

            except Exception as e:
                logger.error(f"Director failed in round {round_num}: {e}")
                scores = {k: 7 for k in self.WEIGHTS}
                weighted_avg = 7.0
                critique = {
                    "round": round_num,
                    "verdict": "APPROVE",
                    "scores": scores,
                    "weighted_average": 7.0,
                    "revision_notes": [],
                    "strengths": ["Auto-approved due to Director error"],
                    "summary": "Director evaluation failed; auto-approved."
                }

            approved = self._should_approve(scores, round_num)

            round_result = RevisionRoundResult(
                round_number=round_num,
                screenplay=screenplay,
                critique=critique,
                scores=scores,
                weighted_avg=weighted_avg,
                approved=approved,
            )
            rounds.append(round_result)

            if weighted_avg > best_avg:
                best_avg = weighted_avg
                best_round_idx = len(rounds) - 1

            if on_round_complete:
                await on_round_complete(round_result)

            if approved:
                logger.info(f"Approved after round {round_num} with avg {weighted_avg:.1f}")
                break

            previous_critique = critique
            previous_draft = screenplay

        # Use the best round's screenplay
        best = rounds[best_round_idx]
        return PipelineResult(
            final_screenplay=best.screenplay,
            rounds=rounds,
            total_rounds=len(rounds),
            final_scores=best.scores,
            final_weighted_avg=best.weighted_avg,
            best_round=best.round_number,
        )

    def _should_approve(self, scores: dict, round_number: int) -> bool:
        if round_number >= self.MAX_ROUNDS:
            return True

        vals = list(scores.values())
        if not vals:
            return False

        min_score = min(vals)
        if min_score <= 3:
            return False
        if scores.get("faithfulness", 5) < 5:
            return False

        weighted_avg = self._calc_weighted_avg(scores)
        all_above_7 = all(v >= 7 for v in vals)

        if all_above_7 and weighted_avg >= settings.approval_threshold:
            return True
        if weighted_avg >= 8.0:
            return True

        return False

    def _calc_weighted_avg(self, scores: dict) -> float:
        total = 0.0
        for key, weight in self.WEIGHTS.items():
            total += scores.get(key, 5) * weight
        return round(total, 2)

    def _validate_segments(self, segments: list) -> list[dict]:
        """Ensure all segments have required fields."""
        valid = []
        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            if "type" not in seg or "text" not in seg:
                continue

            cleaned = {
                "type": seg["type"],
                "text": seg["text"],
                "emotion": seg.get("emotion", "neutral"),
            }
            if seg["type"] == "dialogue":
                cleaned["character"] = seg.get("character", "Unknown")
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
