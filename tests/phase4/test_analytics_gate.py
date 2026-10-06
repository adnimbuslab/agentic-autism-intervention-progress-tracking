"""The status gate on longitudinal analytics.

Deterministic validation establishes that an extracted record is
schema-conformant; it does not establish that the record is true. A
schema-conformant value can still misread the source observation, and nobody
has looked at it. Admitting such a record here would let the analytics engine
compute a faithful trend over unreviewed evidence, which is the failure mode
the human-in-the-loop design exists to prevent.

So the gate admits exactly two states: VERIFIED (an interventionist read the
record and accepted it as written) and CORRECTED (an interventionist rewrote
it). These tests pin that set, because widening it is a one-word edit.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.models.observation import RecordStatus
from src.backend.services import analytics_service

ADMITTED = {RecordStatus.VERIFIED, RecordStatus.CORRECTED}


async def _compiled_query() -> str:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    await analytics_service.get_current_version_records(
        db, uuid.uuid4(), date(2025, 1, 1), date(2025, 2, 1)
    )
    stmt = db.execute.await_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestAnalyticsStatusGate:
    @pytest.mark.parametrize("status", sorted(ADMITTED, key=lambda s: s.value))
    async def test_human_accepted_records_are_admitted(self, status):
        sql = await _compiled_query()
        assert f"'{status.value}'" in sql

    @pytest.mark.parametrize(
        "status",
        sorted(set(RecordStatus) - ADMITTED, key=lambda s: s.value),
    )
    async def test_every_other_state_is_excluded(self, status):
        # VALIDATED is the one that matters: the extraction pipeline sets it
        # automatically on four of its five routing paths, so if it were
        # admitted here, AI output would reach analytics unreviewed.
        sql = await _compiled_query()
        assert f"'{status.value}'" not in sql

    async def test_the_gate_is_an_explicit_two_state_whitelist(self):
        sql = await _compiled_query()
        assert "structured_records.status IN ('verified', 'corrected')" in sql
