"""Analytics service — orchestrates adequacy assessment, deterministic analytics,
and evidence packet construction."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.schemas import (
    AdequacyResult,
    AnalyticsResult,
    EvidencePacket,
)
from src.backend.models.goal import Goal, ReviewPeriod
from src.backend.models.observation import (
    Observation,
    ObservationStatus,
    RecordStatus,
    StructuredRecord,
)


async def get_review_period(
    db: AsyncSession, review_period_id: uuid.UUID
) -> ReviewPeriod | None:
    return await db.get(ReviewPeriod, review_period_id)


async def get_current_version_records(
    db: AsyncSession,
    child_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> list[StructuredRecord]:
    """Fetch the latest version of each structured record for a child in the given period.

    Corrected records supersede prior versions. Only validated or corrected records
    are included. Rejected/abstained records are excluded from analytics.
    """
    stmt = (
        select(StructuredRecord)
        .join(Observation, StructuredRecord.observation_id == Observation.id)
        .where(
            Observation.child_id == child_id,
            Observation.status == ObservationStatus.FINALIZED,
            Observation.submitted_at >= start_date.isoformat(),
            Observation.submitted_at <= (end_date.isoformat() + "T23:59:59"),
            StructuredRecord.status.in_([RecordStatus.VALIDATED, RecordStatus.CORRECTED]),
        )
        .order_by(StructuredRecord.created_at)
    )
    result = await db.execute(stmt)
    all_records = list(result.scalars().all())

    latest_by_obs: dict[uuid.UUID, StructuredRecord] = {}
    for record in all_records:
        existing = latest_by_obs.get(record.observation_id)
        if existing is None or record.version > existing.version:
            latest_by_obs[record.observation_id] = record

    return list(latest_by_obs.values())


async def get_active_goals(
    db: AsyncSession, child_id: uuid.UUID
) -> list[Goal]:
    stmt = (
        select(Goal)
        .where(Goal.child_id == child_id, Goal.is_active.is_(True))
        .order_by(Goal.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _record_to_dict(record: StructuredRecord) -> dict:
    data = dict(record.record_data) if record.record_data else {}
    data["_record_id"] = str(record.id)
    data["_observation_id"] = str(record.observation_id)
    data["_version"] = record.version
    return data


async def compute_analytics(
    db: AsyncSession,
    child_id: uuid.UUID,
    review_period_id: uuid.UUID,
    goal_id: uuid.UUID | None = None,
) -> tuple[AnalyticsResult, AdequacyResult, list[StructuredRecord]]:
    period = await get_review_period(db, review_period_id)
    if period is None:
        raise ValueError(f"ReviewPeriod {review_period_id} not found")

    records = await get_current_version_records(
        db, child_id, period.start_date, period.end_date
    )
    goals = await get_active_goals(db, child_id)
    goal_dicts = [
        {"id": str(g.id), "domain": g.domain.value if g.domain else None, "title": g.title}
        for g in goals
    ]
    record_dicts = [_record_to_dict(r) for r in records]

    router = AdequacyRouter()
    adequacy = router.assess(
        records=record_dicts,
        goals=goal_dicts,
        review_start=period.start_date,
        review_end=period.end_date,
    )

    engine = AnalyticsEngine()
    analytics = engine.compute(
        child_id=str(child_id),
        review_period_id=str(review_period_id),
        records=record_dicts,
        adequacy=adequacy,
        goal_id=str(goal_id) if goal_id else None,
    )

    return analytics, adequacy, records


async def build_evidence_packet(
    db: AsyncSession,
    child_id: uuid.UUID,
    review_period_id: uuid.UUID,
    goal_id: uuid.UUID | None = None,
) -> EvidencePacket:
    period = await get_review_period(db, review_period_id)
    if period is None:
        raise ValueError(f"ReviewPeriod {review_period_id} not found")

    analytics, adequacy, records = await compute_analytics(
        db, child_id, review_period_id, goal_id
    )
    goals = await get_active_goals(db, child_id)

    record_dicts = [_record_to_dict(r) for r in records]
    contributor_summary = dict(Counter(
        r.get("contributor_role", "unknown") for r in record_dicts
    ))
    setting_summary = dict(Counter(
        r.get("setting", "unknown") for r in record_dicts
    ))

    # Count abstained/review records in the full set (not just current versions)
    all_obs_stmt = (
        select(StructuredRecord.status)
        .join(Observation, StructuredRecord.observation_id == Observation.id)
        .where(
            Observation.child_id == child_id,
            Observation.submitted_at >= period.start_date.isoformat(),
            Observation.submitted_at <= (period.end_date.isoformat() + "T23:59:59"),
        )
    )
    all_result = await db.execute(all_obs_stmt)
    all_statuses = [row[0] for row in all_result.all()]
    abstained_count = sum(1 for s in all_statuses if s == RecordStatus.ABSTAINED)
    review_count = sum(1 for s in all_statuses if s == RecordStatus.PENDING)

    return EvidencePacket(
        child_id=str(child_id),
        review_period_id=str(review_period_id),
        review_period_start=period.start_date.isoformat(),
        review_period_end=period.end_date.isoformat(),
        goals=[
            {"id": str(g.id), "domain": g.domain.value if g.domain else None, "title": g.title}
            for g in goals
        ],
        structured_records=record_dicts,
        record_ids=[str(r.id) for r in records],
        record_versions={str(r.id): r.version for r in records},
        analytics=analytics,
        adequacy=adequacy,
        quality_flags=adequacy.quality_flags,
        contributor_summary=contributor_summary,
        setting_summary=setting_summary,
        observation_count=len(records),
        abstained_count=abstained_count,
        review_count=review_count,
    )
