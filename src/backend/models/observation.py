from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.backend.database import Base


class ObservationStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    CLARIFYING = "clarifying"
    FINALIZED = "finalized"
    FAILED = "failed"


class Observation(Base):
    """IMMUTABLE once finalized — raw_text is immutable immediately on submission."""

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("children.id"),
        nullable=False,
        index=True,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    setting: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[ObservationStatus] = mapped_column(
        nullable=False,
        default=ObservationStatus.PENDING,
    )
    conversation_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    extraction_result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    child: Mapped["Child"] = relationship(back_populates="observations")  # noqa: F821
    structured_records: Mapped[list["StructuredRecord"]] = relationship(
        back_populates="observation",
    )
    clarification_turns: Mapped[list["ClarificationTurn"]] = relationship(
        back_populates="observation",
        order_by="ClarificationTurn.turn_number",
    )


class ClarificationTurn(Base):
    """APPEND-ONLY — clarification exchanges during the observation flow."""

    __tablename__ = "clarification_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.id"),
        nullable=False,
        index=True,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    observation: Mapped["Observation"] = relationship(
        back_populates="clarification_turns",
    )


class RecordStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


class StructuredRecord(Base):
    """Versioned — corrections create new versions, originals are preserved."""

    __tablename__ = "structured_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.id"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[RecordStatus] = mapped_column(
        nullable=False,
        default=RecordStatus.PENDING,
    )
    record_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("structured_records.id"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    observation: Mapped["Observation"] = relationship(
        back_populates="structured_records",
    )
