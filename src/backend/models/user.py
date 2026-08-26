from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.backend.database import Base


class Role(str, enum.Enum):
    INTERVENTIONIST = "interventionist"
    PARENT = "parent"
    TEACHER = "teacher"
    TRAINER = "trainer"
    EPA = "epa"
    SECONDARY_INTERVENTIONIST = "secondary_interventionist"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    actor_assignments: Mapped[list["ActorAssignment"]] = relationship(  # noqa: F821
        back_populates="user",
        foreign_keys="[ActorAssignment.user_id]",
    )
