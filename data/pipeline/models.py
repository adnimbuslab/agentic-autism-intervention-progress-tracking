"""Pydantic models for CHAT file parsing and the unified dataset."""

from __future__ import annotations

import enum
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DependentTier(BaseModel):
    """A dependent tier line (e.g., %spa, %act, %gpx) linked to a parent utterance."""

    tier_type: str
    content: str


class Utterance(BaseModel):
    """A single speaker utterance from a CHAT transcript."""

    speaker: str
    text: str
    line_number: int
    dependent_tiers: list[DependentTier] = Field(default_factory=list)


class SessionHeader(BaseModel):
    """Parsed metadata from CHAT file headers."""

    participants: dict[str, str] = Field(default_factory=dict)
    participant_ids: dict[str, dict[str, str]] = Field(default_factory=dict)
    languages: list[str] = Field(default_factory=list)
    date: Optional[date] = None
    location: Optional[str] = None
    situation: Optional[str] = None
    raw_headers: dict[str, str] = Field(default_factory=dict)


class Session(BaseModel):
    """A fully parsed CHAT session (.cha file)."""

    source_file: str
    corpus: str
    child_id: str
    header: SessionHeader
    utterances: list[Utterance] = Field(default_factory=list)

    @property
    def utterance_count(self) -> int:
        return len(self.utterances)


class UnifiedRow(BaseModel):
    """A single row in the unified long-format dataset."""

    corpus: str
    child_id: str
    session_id: str
    source_file: str
    date: Optional[date] = None
    relative_month: Optional[int] = None
    speaker: str
    utterance_text: str
    line_number: int
    tier_spa: Optional[str] = None
    tier_act: Optional[str] = None
    tier_gpx: Optional[str] = None


class DeidentificationReport(BaseModel):
    """Summary of deidentification operations performed on a corpus."""

    total_sessions: int = 0
    replacement_count: int = 0
    flagged_items: list[str] = Field(default_factory=list)


class DeidentifiedResult(BaseModel):
    """Container for deidentified sessions and their report."""

    sessions: list[Session] = Field(default_factory=list)
    report: DeidentificationReport = Field(default_factory=DeidentificationReport)


class EpisodeType(str, enum.Enum):
    """Communicative/behavioral episode category."""

    REQUEST = "request"
    IMITATION = "imitation"
    JOINT_ATTENTION = "joint_attention"
    PROTEST = "protest"
    RESPONSE = "response"
    INITIATION = "initiation"
    PLAY = "play"
    OTHER = "other"


class Episode(BaseModel):
    """A coherent multi-turn behavioral episode extracted from a session."""

    episode_id: str
    corpus: str
    child_id: str
    session_id: str
    source_file: str
    episode_type: EpisodeType
    utterances: list[Utterance]
    start_line: int
    end_line: int


class SegmentTurn(BaseModel):
    """A single turn within a behavioral segment, with tier annotations."""

    speaker: str
    text: str
    spa: Optional[str] = None
    act: Optional[str] = None
    gpx: Optional[str] = None


class SegmentSource(BaseModel):
    """Provenance information for a behavioral segment."""

    corpus: str
    child_id: str
    session_id: str
    source_file: str
    turns: list[SegmentTurn]


class ProvisionalExtraction(BaseModel):
    """Placeholder for future LLM-based structured extraction."""

    status: str = "provisional_llm"
    structured_record: None = None
    provider: None = None
    model: None = None
    prompt_version: None = None
    schema_version: None = None
    generated_at: None = None


class BehavioralSegment(BaseModel):
    """A selected behavioral segment ready for downstream extraction."""

    segment_id: str
    source: SegmentSource
    provisional_extraction: ProvisionalExtraction = Field(default_factory=ProvisionalExtraction)
