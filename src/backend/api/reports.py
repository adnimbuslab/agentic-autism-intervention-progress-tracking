"""Report routes — generation, retrieval, listing, evidence, and flagging."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import DBSession, RequireInterventionist, authorize_child_access
from src.backend.schemas.api_schemas import (
    EvidencePacketResponse,
    ReportFlagRequest,
    ReportGenerateRequest,
    ReportListItem,
    ReportResponse,
    ReportSectionResponse,
)
from src.backend.services import report_service

router = APIRouter(tags=["reports"])


@router.post(
    "/children/{child_id}/reports/generate",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_report(
    child_id: uuid.UUID,
    body: ReportGenerateRequest,
    user: RequireInterventionist,
    db: DBSession,
) -> ReportResponse:
    await authorize_child_access(user, child_id, db)

    try:
        report = await report_service.generate_report(
            db, child_id, body.review_period_id, user.id, body.goal_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    sections = [
        ReportSectionResponse(**s)
        for s in report.report_json.get("sections", [])
    ]

    return ReportResponse(
        id=report.id,
        child_id=report.child_id,
        review_period_id=report.review_period_id,
        sections=sections,
        provider=report.provider,
        model=report.model,
        prompt_version=report.prompt_version,
        version=report.version,
        validation_passed=report.validation_passed,
        validation_errors=report.validation_errors,
        flagged=report.flagged,
        flagged_reason=report.flagged_reason,
        flagged_by=report.flagged_by,
        generated_at=report.generated_at,
    )


@router.get("/children/{child_id}/reports", response_model=list[ReportListItem])
async def list_reports(
    child_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
    limit: int = 50,
    offset: int = 0,
) -> list[ReportListItem]:
    await authorize_child_access(user, child_id, db)
    reports = await report_service.list_reports(db, child_id, limit, offset)
    return [
        ReportListItem(
            id=r.id,
            child_id=r.child_id,
            review_period_id=r.review_period_id,
            version=r.version,
            validation_passed=r.validation_passed,
            flagged=r.flagged,
            generated_at=r.generated_at,
        )
        for r in reports
    ]


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> ReportResponse:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    await authorize_child_access(user, report.child_id, db)

    sections = [
        ReportSectionResponse(**s)
        for s in report.report_json.get("sections", [])
    ]

    return ReportResponse(
        id=report.id,
        child_id=report.child_id,
        review_period_id=report.review_period_id,
        sections=sections,
        provider=report.provider,
        model=report.model,
        prompt_version=report.prompt_version,
        version=report.version,
        validation_passed=report.validation_passed,
        validation_errors=report.validation_errors,
        flagged=report.flagged,
        flagged_reason=report.flagged_reason,
        flagged_by=report.flagged_by,
        generated_at=report.generated_at,
    )


@router.get("/reports/{report_id}/evidence", response_model=EvidencePacketResponse)
async def get_evidence(
    report_id: uuid.UUID,
    user: RequireInterventionist,
    db: DBSession,
) -> EvidencePacketResponse:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    await authorize_child_access(user, report.child_id, db)

    ep = report.evidence_packet_json
    return EvidencePacketResponse(
        child_id=ep.get("child_id", ""),
        review_period_id=ep.get("review_period_id", ""),
        review_period_start=ep.get("review_period_start", ""),
        review_period_end=ep.get("review_period_end", ""),
        goals=ep.get("goals", []),
        record_ids=ep.get("record_ids", []),
        record_versions=ep.get("record_versions", {}),
        contributor_summary=ep.get("contributor_summary", {}),
        setting_summary=ep.get("setting_summary", {}),
        observation_count=ep.get("observation_count", 0),
        abstained_count=ep.get("abstained_count", 0),
        review_count=ep.get("review_count", 0),
        quality_flags=ep.get("quality_flags", []),
    )


@router.post("/reports/{report_id}/flag", response_model=ReportResponse)
async def flag_report(
    report_id: uuid.UUID,
    body: ReportFlagRequest,
    user: RequireInterventionist,
    db: DBSession,
) -> ReportResponse:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    await authorize_child_access(user, report.child_id, db)

    flagged = await report_service.flag_report(db, report_id, user.id, body.reason)

    sections = [
        ReportSectionResponse(**s)
        for s in flagged.report_json.get("sections", [])
    ]

    return ReportResponse(
        id=flagged.id,
        child_id=flagged.child_id,
        review_period_id=flagged.review_period_id,
        sections=sections,
        provider=flagged.provider,
        model=flagged.model,
        prompt_version=flagged.prompt_version,
        version=flagged.version,
        validation_passed=flagged.validation_passed,
        validation_errors=flagged.validation_errors,
        flagged=flagged.flagged,
        flagged_reason=flagged.flagged_reason,
        flagged_by=flagged.flagged_by,
        generated_at=flagged.generated_at,
    )
