"""Report service — orchestrates report generation, retrieval, listing, and flagging."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.ml.reporting_client import ReportingClient
from src.backend.ml.schemas import EvidencePacket, GeneratedReportData
from src.backend.models.report import GeneratedReport
from src.backend.services import analytics_service, audit_service


async def generate_report(
    db: AsyncSession,
    child_id: uuid.UUID,
    review_period_id: uuid.UUID,
    user_id: uuid.UUID,
    goal_id: uuid.UUID | None = None,
) -> GeneratedReport:
    evidence_packet = await analytics_service.build_evidence_packet(
        db, child_id, review_period_id, goal_id
    )

    client = ReportingClient()
    report_data: GeneratedReportData = await client.generate_report(evidence_packet)

    existing_stmt = (
        select(GeneratedReport)
        .where(
            GeneratedReport.child_id == child_id,
            GeneratedReport.review_period_id == review_period_id,
        )
        .order_by(GeneratedReport.version.desc())
        .limit(1)
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    next_version = (existing.version + 1) if existing else 1

    report = GeneratedReport(
        child_id=child_id,
        review_period_id=review_period_id,
        report_json={
            "sections": [s.model_dump() for s in report_data.sections],
        },
        evidence_packet_json=evidence_packet.model_dump(mode="json"),
        provider=report_data.provider,
        model=report_data.model,
        prompt_version=report_data.prompt_version,
        version=next_version,
        validation_passed=report_data.validation_passed,
        validation_errors=(
            {"errors": report_data.validation_errors}
            if report_data.validation_errors
            else None
        ),
    )
    db.add(report)
    await db.flush()

    await audit_service.log_event(
        db=db,
        user_id=user_id,
        action="generate_report",
        resource_type="report",
        resource_id=str(report.id),
        child_id=child_id,
        detail={
            "review_period_id": str(review_period_id),
            "version": next_version,
            "validation_passed": report_data.validation_passed,
            "model": report_data.model,
            "prompt_version": report_data.prompt_version,
        },
    )

    await db.commit()
    return report


async def get_report(
    db: AsyncSession, report_id: uuid.UUID
) -> GeneratedReport | None:
    return await db.get(GeneratedReport, report_id)


async def list_reports(
    db: AsyncSession,
    child_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[GeneratedReport]:
    stmt = (
        select(GeneratedReport)
        .where(GeneratedReport.child_id == child_id)
        .order_by(GeneratedReport.generated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_evidence_packet(
    db: AsyncSession, report_id: uuid.UUID
) -> dict | None:
    report = await db.get(GeneratedReport, report_id)
    if report is None:
        return None
    return report.evidence_packet_json


async def flag_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
) -> GeneratedReport | None:
    report = await db.get(GeneratedReport, report_id)
    if report is None:
        return None

    report.flagged = True
    report.flagged_reason = reason
    report.flagged_by = user_id
    await db.flush()

    await audit_service.log_event(
        db=db,
        user_id=user_id,
        action="flag_report",
        resource_type="report",
        resource_id=str(report.id),
        child_id=report.child_id,
        detail={"reason": reason},
    )

    await db.commit()
    return report
