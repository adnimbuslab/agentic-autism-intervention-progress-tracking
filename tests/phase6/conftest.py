"""Phase 6 shared fixtures — re-exports Phase 3 helpers and adds Phase 6 specific fixtures."""

from __future__ import annotations

from tests.phase3.conftest import (
    contributor_client,
    contributor_user,
    interventionist_client,
    interventionist_user,
    make_actor,
    make_audit_event,
    make_child,
    make_goal,
    make_mock_session,
    make_observation,
    make_record,
    make_schedule,
    make_user,
    mock_db,
    unauth_client,
)

__all__ = [
    "contributor_client",
    "contributor_user",
    "interventionist_client",
    "interventionist_user",
    "make_actor",
    "make_audit_event",
    "make_child",
    "make_goal",
    "make_mock_session",
    "make_observation",
    "make_record",
    "make_schedule",
    "make_user",
    "mock_db",
    "unauth_client",
]
