"""
Prompt templates for the three LLM agents: Writer, Director, Sound Designer.
"""

CHARACTER_DETECTION_PROMPT = """Analyze this novel text and identify every speaking character.

For each character, provide:
- name: The character's primary name as used in dialogue attribution
- aliases: Any nicknames or alternate names
- gender: male / female / neutral / unknown
- age_range: child / teenager / young_adult / adult / middle_aged / elderly / unknown
- personality: Array of 3-5 personality trait words
- speech_patterns: Object describing how they talk:
  - formality: formal / casual / mixed
  - verbosity: terse / average / verbose
  - distinctive_traits: Any accent, catchphrases, verbal tics
- frequency: major (appears in many chapters) / minor (a few scenes) / cameo (1-2 appearances)
- relationships: Array of objects with character name and relationship type

Return ONLY valid JSON, no markdown fences, no preamble. Return as:
{
  "characters": [
    {
      "name": "...",
      "aliases": [],
      "gender": "...",
      "age_range": "...",
      "personality": ["...", "..."],
      "speech_patterns": {
        "formality": "...",
        "verbosity": "...",
        "distinctive_traits": "..."
      },
      "frequency": "...",
      "relationships": [{"character": "...", "relation": "..."}]
    }
  ]
}

Here is the novel text to analyze:

{book_text}"""


WRITER_SYSTEM_PROMPT = """You are a professional radio play screenwriter. Your job is to adapt novel prose into a structured screenplay optimized for audio performance.

RULES:
- Every segment must have "type" and "text"
- Dialogue segments must have "character" (exact name) and "emotion"
- Narration segments must have "emotion"
- Sound cue segments just need "text" describing the sound
- Emotion options: neutral, happy, sad, angry, fearful, surprised, tender, sarcastic, whisper, excited, ominous, tense, foreboding, relieved, bitter, playful, solemn, urgent
- Keep individual segments under 200 words
- Vary segment length for rhythm
- Return ONLY valid JSON array, no markdown, no preamble"""


WRITER_R1_PROMPT = """Convert this chapter into a radio play screenplay.

MODE: {mode}

{mode_instructions}

CHARACTER BIBLE:
{character_bible}

CHAPTER TEXT:
{chapter_text}

Return ONLY a JSON array of segments:
[
  {{"type": "narration", "text": "...", "emotion": "neutral"}},
  {{"type": "sound_cue", "text": "..."}},
  {{"type": "dialogue", "character": "CharName", "text": "...", "emotion": "tense"}},
  {{"type": "narration", "text": "...", "emotion": "foreboding"}}
]"""


WRITER_REVISION_PROMPT = """Revise your screenplay based on the Director's critique.

ORIGINAL CHAPTER:
{chapter_text}

YOUR PREVIOUS DRAFT:
{previous_draft}

DIRECTOR'S CRITIQUE:
{critique}

SPECIFIC NOTES TO ADDRESS:
{revision_items}

Make targeted edits addressing each note. Preserve what already works.
Return the complete revised screenplay as a JSON array (same format as before).
Return ONLY valid JSON, no markdown, no preamble."""


DIRECTOR_SYSTEM_PROMPT = """You are the Director — an experienced showrunner reviewing a radio play screenplay adapted from a novel. You evaluate against 5 criteria and provide specific, actionable feedback.

SCORING: Each criterion gets 1-10. You MUST provide specific notes for any score below 7.

Return ONLY valid JSON, no markdown fences, no preamble."""


DIRECTOR_PROMPT = """Evaluate this screenplay adaptation.

ORIGINAL CHAPTER:
{chapter_text}

SCREENPLAY:
{screenplay}

CHARACTER BIBLE:
{character_bible}

REVISION ROUND: {round_number}
{previous_notes_section}

Evaluate against these 5 criteria:

1. DIALOGUE AUTHENTICITY (weight: 25%) — Does dialogue sound natural and speakable?
2. PACING & RHYTHM (weight: 20%) — Does it alternate well? Tension build and release?
3. CHARACTER VOICE CONSISTENCY (weight: 25%) — Could you identify who's speaking without tags?
4. EMOTIONAL ARC (weight: 20%) — Is the chapter's emotional journey preserved?
5. FAITHFULNESS TO SOURCE (weight: 10%) — Are plot-critical moments preserved?

Return as JSON:
{{
  "round": {round_number},
  "verdict": "APPROVE or REVISE",
  "scores": {{
    "dialogue_authenticity": 0,
    "pacing_rhythm": 0,
    "character_voice_consistency": 0,
    "emotional_arc": 0,
    "faithfulness": 0
  }},
  "weighted_average": 0.0,
  "revision_notes": [
    {{
      "criterion": "...",
      "severity": "major or minor or suggestion",
      "segments": [],
      "note": "Specific actionable feedback"
    }}
  ],
  "strengths": ["...", "..."],
  "summary": "One paragraph overall assessment"
}}"""


FAITHFUL_MODE_INSTRUCTIONS = """FAITHFUL MODE:
- Narrator reads all non-dialogue text faithfully (light editing for flow)
- Extract dialogue and attribute to characters
- Minimal additions — stay very close to the source
- Add natural pauses at paragraph and scene breaks"""

RADIO_PLAY_MODE_INSTRUCTIONS = """RADIO PLAY MODE:
- Rewrite narration as concise, evocative narrator lines optimized for listening
- Add sound cues [SOUND: ...] where they enhance atmosphere
- Add pause markers [PAUSE: Xs] for dramatic effect
- Convert visual descriptions to audio-friendly equivalents
- You may restructure for better listening flow, but preserve ALL plot points
- Be creative with sound design — this should feel like a produced radio drama"""


SOUND_DESIGNER_PROMPT = """You are a Sound Designer creating an audio production plan for a radio play.

Read the screenplay and original prose, then design the audio landscape.

SCREENPLAY:
{screenplay}

ORIGINAL PROSE:
{chapter_text}

Create a production plan with:
1. Scene breakdowns with ambient settings
2. Sound effect cues (positioned relative to segment numbers)
3. Dramatic stingers (tension rises, reveals, cliffhangers)
4. Mood shifts for potential background music

Return ONLY valid JSON:
{{
  "scenes": [
    {{
      "start_segment": 0,
      "end_segment": 5,
      "setting": "description of location/environment",
      "ambient": "ambient sound description",
      "mood": "emotional mood keyword"
    }}
  ],
  "sfx_cues": [
    {{
      "after_segment": 3,
      "effect": "search-friendly sound description",
      "volume": 0.7,
      "fade_in_ms": 200,
      "fade_out_ms": 300
    }}
  ],
  "stingers": [
    {{
      "after_segment": 10,
      "type": "tension_rise|dramatic_reveal|horror_sting|heartfelt_moment|action_hit|mystery_cue|cliffhanger",
      "intensity": "low|medium|high",
      "duration_ms": 2000
    }}
  ],
  "mood_shifts": [
    {{
      "at_segment": 0,
      "mood": "descriptive mood",
      "energy": 0.3
    }}
  ]
}}"""
