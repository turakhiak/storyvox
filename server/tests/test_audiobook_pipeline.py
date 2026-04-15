"""
Audiobook-mode regression tests for the screenplay pipeline.

Protects against the class of bugs the user hit where "faithful" mode ran
end-to-end but produced the wrong shape — wrong prompts, wrong score keys,
stray sound_cues, or a hardcoded best_round of 1.

The cloud pipeline is exercised via a FakeCloudClient that records every
prompt it sees and returns canned responses — no real LLM calls. If prompt
identities, weight keys, segment filtering, or best_round selection regress,
these tests catch it.
"""
import asyncio
from typing import Any, Optional

import pytest

from services.llm.pipeline import ScreenplayPipeline, PipelineResult
from services.llm.prompts import (
    AUDIOBOOK_WRITER_SYSTEM_PROMPT,
    AUDIOBOOK_DIRECTOR_SYSTEM_PROMPT,
    WRITER_SYSTEM_PROMPT,
    DIRECTOR_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeCloudClient:
    """
    Minimal LLMClient stand-in for cloud pipeline tests.

    - Records every (system, user) prompt it sees so tests can assert mode
      correctness.
    - Returns whatever is in `self.responses` queue, one per call.
    - `is_local = False` so ScreenplayPipeline takes the cloud path.
    """

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []

    @property
    def is_local(self) -> bool:
        return False

    async def generate(self, system, user, temperature=0.7, response_schema=None):
        raise NotImplementedError("Pipeline uses generate_json")

    async def generate_json(self, system, user, temperature=0.7, response_schema=None):
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        if not self.responses:
            raise AssertionError("FakeCloudClient exhausted — pipeline made more calls than expected")
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Valid audiobook writer response — a dialogue and a narration segment.
# The pipeline's _validate_segments will keep these as-is.
AUDIOBOOK_WRITER_RESPONSE = {
    "segments": [
        {"type": "narration", "text": "The door creaked open.", "emotion": "tense"},
        {"type": "dialogue", "character": "Alice", "text": "Who's there?", "emotion": "fearful"},
        # A stray sound_cue that the prompt says not to produce — the
        # pipeline must strip this in audiobook mode.
        {"type": "sound_cue", "text": "creaking door", "emotion": "neutral"},
    ]
}

# Director response using AUDIOBOOK scoring keys.
AUDIOBOOK_DIRECTOR_RESPONSE_LOW = {
    "scores": {
        "text_faithfulness": 6,
        "dialogue_attribution": 6,
        "character_voice_consistency": 6,
        "flow_and_pacing": 6,
    },
    "revision_notes": [
        {"criterion": "text_faithfulness", "severity": "major", "segments": [0], "note": "Tighten."}
    ],
}

AUDIOBOOK_DIRECTOR_RESPONSE_HIGH = {
    "scores": {
        "text_faithfulness": 9,
        "dialogue_attribution": 9,
        "character_voice_consistency": 8,
        "flow_and_pacing": 9,
    },
    "revision_notes": [],
}


# ---------------------------------------------------------------------------
# Tests — unit-level guards
# ---------------------------------------------------------------------------

def test_audiobook_weights_differ_from_radio_play():
    """Audiobook mode must use its own weight dict, not the radio_play defaults."""
    pipe = ScreenplayPipeline(writer=FakeCloudClient([]), director=FakeCloudClient([]))
    faithful = pipe._active_weights("faithful")
    radio = pipe._active_weights("radio_play")
    assert set(faithful.keys()) == {
        "text_faithfulness", "dialogue_attribution",
        "character_voice_consistency", "flow_and_pacing",
    }
    assert set(radio.keys()) == {
        "dialogue_authenticity", "pacing_rhythm",
        "character_voice_consistency", "emotional_arc", "faithfulness",
    }
    # Faithfulness weight dominates in audiobook (0.40) vs radio (0.10)
    assert faithful["text_faithfulness"] > radio["faithfulness"]


def test_validate_segments_strips_sound_cues_in_audiobook_mode():
    """Audiobook output must never contain sound_cue segments."""
    pipe = ScreenplayPipeline(writer=FakeCloudClient([]), director=FakeCloudClient([]))
    mixed = [
        {"type": "narration", "text": "Hello."},
        {"type": "sound_cue", "text": "wind blowing"},
        {"type": "dialogue", "character": "Bob", "text": "Hi."},
    ]
    kept = pipe._validate_segments(mixed, strip_sound_cues=True)
    types = [s["type"] for s in kept]
    assert "sound_cue" not in types
    assert types == ["narration", "dialogue"]


def test_normalize_critique_defaults_audiobook_keys():
    """Missing audiobook score keys default to 5, not to radio_play keys."""
    pipe = ScreenplayPipeline(writer=FakeCloudClient([]), director=FakeCloudClient([]))
    weights = pipe._active_weights("faithful")
    crit = pipe._normalize_critique({"scores": {}}, weights=weights)
    scores = crit["scores"]
    # Every audiobook key must be present with default 5
    for key in weights:
        assert key in scores
        assert scores[key] == 5
    # Radio-play-only keys should NOT leak in
    assert "dialogue_authenticity" not in scores
    assert "pacing_rhythm" not in scores


def test_calc_weighted_avg_uses_audiobook_weights():
    """_calc_weighted_avg must respect the passed-in weights dict."""
    pipe = ScreenplayPipeline(writer=FakeCloudClient([]), director=FakeCloudClient([]))
    weights = pipe._active_weights("faithful")
    # All 10s should yield 10.0 regardless of which keys weights uses
    scores = {k: 10 for k in weights}
    assert pipe._calc_weighted_avg(scores, weights) == 10.0


# ---------------------------------------------------------------------------
# Tests — local pipeline guard
# ---------------------------------------------------------------------------

def test_local_pipeline_rejects_faithful_mode():
    """Audiobook mode on local Ollama must fail loudly, not silently fall back."""

    class FakeLocal:
        is_local = True

        async def generate_json(self, *a, **kw): raise AssertionError("should not be called")
        async def generate(self, *a, **kw): raise AssertionError("should not be called")

    pipe = ScreenplayPipeline(writer=FakeLocal(), director=FakeLocal())
    with pytest.raises(RuntimeError, match="Audiobook mode requires the cloud pipeline"):
        asyncio.run(pipe.process_chapter(
            chapter_text="The door creaked open.",
            character_bible=[],
            mode="faithful",
        ))


# ---------------------------------------------------------------------------
# Tests — cloud pipeline end-to-end
# ---------------------------------------------------------------------------

def test_cloud_pipeline_audiobook_uses_audiobook_prompts():
    """Audiobook mode must feed AUDIOBOOK_* system prompts to Writer + Director."""
    writer = FakeCloudClient([AUDIOBOOK_WRITER_RESPONSE])
    # High scores → director approves after round 1, so only one director call.
    director = FakeCloudClient([AUDIOBOOK_DIRECTOR_RESPONSE_HIGH])

    pipe = ScreenplayPipeline(writer=writer, director=director)
    result = asyncio.run(pipe.process_chapter(
        chapter_text="The door creaked open. Alice whispered: Who's there?",
        character_bible=[{"name": "Alice", "gender": "female", "age_range": "adult"}],
        mode="faithful",
    ))

    # Writer was called with the AUDIOBOOK system prompt (not the radio-play one)
    assert len(writer.calls) >= 1
    assert writer.calls[0]["system"] == AUDIOBOOK_WRITER_SYSTEM_PROMPT
    assert writer.calls[0]["system"] != WRITER_SYSTEM_PROMPT
    # Director too
    assert len(director.calls) >= 1
    assert director.calls[0]["system"] == AUDIOBOOK_DIRECTOR_SYSTEM_PROMPT
    assert director.calls[0]["system"] != DIRECTOR_SYSTEM_PROMPT


def test_cloud_pipeline_audiobook_strips_sound_cues_from_output():
    """Stray sound_cues from the writer must not appear in the final screenplay."""
    writer = FakeCloudClient([AUDIOBOOK_WRITER_RESPONSE])
    director = FakeCloudClient([AUDIOBOOK_DIRECTOR_RESPONSE_HIGH])

    pipe = ScreenplayPipeline(writer=writer, director=director)
    result = asyncio.run(pipe.process_chapter(
        chapter_text="Short text.",
        character_bible=[],
        mode="faithful",
    ))

    types = [s["type"] for s in result.final_screenplay]
    assert "sound_cue" not in types, f"Audiobook leaked sound_cue segments: {result.final_screenplay}"
    # And sound_plan stays None (sound designer is skipped for audiobooks)
    assert result.sound_plan is None


def test_cloud_pipeline_audiobook_final_scores_use_audiobook_keys():
    """final_scores must carry the audiobook score keys, not radio_play ones."""
    writer = FakeCloudClient([AUDIOBOOK_WRITER_RESPONSE])
    director = FakeCloudClient([AUDIOBOOK_DIRECTOR_RESPONSE_HIGH])

    pipe = ScreenplayPipeline(writer=writer, director=director)
    result = asyncio.run(pipe.process_chapter(
        chapter_text="Short text.",
        character_bible=[],
        mode="faithful",
    ))

    assert set(result.final_scores.keys()) == {
        "text_faithfulness", "dialogue_attribution",
        "character_voice_consistency", "flow_and_pacing",
    }
    # These radio-play keys must NOT appear — if they do, the wrong weights
    # dict was used somewhere.
    for leaked in ("dialogue_authenticity", "pacing_rhythm", "emotional_arc", "faithfulness"):
        assert leaked not in result.final_scores


def test_cloud_pipeline_best_round_tracks_highest_scoring_round():
    """
    Regression for pipeline.py hardcoding best_round=1. When round 2 scores
    higher than round 1, best_round must be 2 — otherwise the frontend's
    `is_best` flag gets stamped on the wrong RevisionRound row.
    """
    # Writer returns SAME segments for round 1 and round 2 — we only care
    # about score progression for this test.
    writer = FakeCloudClient([AUDIOBOOK_WRITER_RESPONSE, AUDIOBOOK_WRITER_RESPONSE])
    # Round 1: low (approval gate fails → loop continues)
    # Round 2: high (approval gate passes → loop stops)
    director = FakeCloudClient([
        AUDIOBOOK_DIRECTOR_RESPONSE_LOW,
        AUDIOBOOK_DIRECTOR_RESPONSE_HIGH,
    ])

    pipe = ScreenplayPipeline(writer=writer, director=director)
    result = asyncio.run(pipe.process_chapter(
        chapter_text="Short text.",
        character_bible=[],
        mode="faithful",
    ))

    # Two rounds should have executed
    assert len(result.rounds) == 1, (
        # Only the best round per chunk is saved — so all_rounds has 1 entry,
        # which should be round 2 (the higher-scoring one).
        f"Expected 1 best-round per chunk, got {len(result.rounds)}"
    )
    best_saved = result.rounds[0]
    assert best_saved.round_number == 2, (
        f"Best round should be round 2 (higher score), got round {best_saved.round_number}"
    )
    # And the PipelineResult.best_round field must match — NOT hardcoded to 1.
    assert result.best_round == 2, (
        f"best_round regression — expected 2, got {result.best_round}. "
        f"This indicates pipeline.py reintroduced a hardcoded best_round=1."
    )
