from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.backend.database import Base


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    date_of_birth: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    actor_assignments: Mapped[list["ActorAssignment"]] = relationship(  # noqa: F821
        back_populates="child",
    )
    goals: Mapped[list["Goal"]] = relationship(back_populates="child")  # noqa: F821
    observations: Mapped[list["Observation"]] = relationship(  # noqa: F821
        back_populates="child",
    )
    review_periods: Mapped[list["ReviewPeriod"]] = relationship(  # noqa: F821
        back_populates="child",
    )
