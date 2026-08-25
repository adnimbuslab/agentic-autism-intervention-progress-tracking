"""Pydantic models for CHAT file parsing and the unified dataset."""

from __future__ import annotations

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
