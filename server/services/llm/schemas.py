from pydantic import BaseModel, Field
from typing import List, Optional

class SpeechPatterns(BaseModel):
    formality: str = Field(..., description="formal / casual / mixed")
    verbosity: str = Field(..., description="terse / average / verbose")
    distinctive_traits: str = Field(..., description="Any accent, catchphrases, verbal tics")

class Relationship(BaseModel):
    character: str
    relation: str

class CharacterDetection(BaseModel):
    name: str
    aliases: List[str]
    gender: str
    age_range: str
    personality: List[str]
    speech_patterns: SpeechPatterns
    frequency: str = Field(..., description="major / minor / cameo")
    relationships: List[Relationship]

class CharacterDetectionResponse(BaseModel):
    characters: List[CharacterDetection]

class ScreenplaySegment(BaseModel):
    type: str = Field(..., description="narration / dialogue / sound_cue")
    text: str
    character: Optional[str] = Field(None, description="Character name for dialogue segments, null for narration/sound_cue")
    emotion: str = Field("neutral", description="neutral, happy, sad, angry, fearful, surprised, tender, sarcastic, whisper, excited, ominous, tense")

class ScreenplayDraft(BaseModel):
    segments: List[ScreenplaySegment]

class CriterionScore(BaseModel):
    dialogue_authenticity: int
    pacing_rhythm: int
    character_voice_consistency: int
    emotional_arc: int
    faithfulness: int

class RevisionNote(BaseModel):
    criterion: str = ""
    severity: str = Field("minor", description="major / minor / suggestion")
    segments: List[int] = []
    note: str = ""

class DirectorCritique(BaseModel):
    round: Optional[int] = None
    verdict: Optional[str] = Field(None, description="APPROVE or REVISE")
    scores: CriterionScore
    weighted_average: Optional[float] = None
    revision_notes: List[RevisionNote] = []
    strengths: List[str] = []
    summary: Optional[str] = None

class ScenePlan(BaseModel):
    start_segment: int
    end_segment: int
    setting: str
    ambient: str
    mood: str

class SoundEffectCue(BaseModel):
    after_segment: int = 0
    effect: str = ""
    volume: float = Field(0.5, description="0.0 to 1.0")
    fade_in_ms: int = Field(0, description="ms")
    fade_out_ms: int = Field(0, description="ms")

class DramaticStinger(BaseModel):
    after_segment: int = 0
    type: str = Field("tension_rise", description="tension_rise|dramatic_reveal|horror_sting|heartfelt_moment|action_hit|mystery_cue|cliffhanger")
    intensity: str = Field("medium", description="low|medium|high")
    duration_ms: int = Field(2000, description="ms")

class MoodShift(BaseModel):
    at_segment: int = 0
    mood: str = ""
    energy: float = 0.5

class SoundPlan(BaseModel):
    scenes: List[ScenePlan] = []
    sfx_cues: List[SoundEffectCue] = []
    stingers: List[DramaticStinger] = []
    mood_shifts: List[MoodShift] = []
