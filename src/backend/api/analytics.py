"""Analytics routes — deterministic analytics and adequacy assessment."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import DBSession, RequireInterventionist, authorize_child_access
from src.backend.schemas.api_schemas import (
    AdequacyCheckResponse,
    AdequacyResponse,
    AnalyticsRequest,
    AnalyticsResponse,
    KpiResponse,
    ReviewPeriodCreate,
    ReviewPeriodResponse,
)
from src.backend.services import analytics_service, audit_service

router = APIRouter(tags=["analytics"])


@router.post("/children/{child_id}/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    child_id: uuid.UUID,
    body: AnalyticsRequest,
    user: RequireInterventionist,
    db: DBSession,
) -> AnalyticsResponse:
    await authorize_child_access(user, child_id, db)

    try:
        analytics, adequacy, _ = await analytics_service.compute_analytics(
            db, child_id, body.review_period_id, body.goal_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    await audit_service.log_event(
        db=db,
        user_id=user.id,
        action="compute_analytics",
        resource_type="analytics",
        child_id=child_id,
        detail={
            "review_period_id": str(body.review_period_id),
            "adequacy_level": adequacy.level.value,
        },
    )
    await db.commit()

    return AnalyticsResponse(
        child_id=child_id,
        review_period_id=body.review_period_id,
        goal_id=body.goal_id,
        kpis=[
            KpiResponse(
                name=k.name,
                numerator=k.numerator,
                denominator=k.denominator,
                value=k.value,
                abstained=k.abstained,
                abstention_reason=k.abstention_reason,
                display_eligible=k.display_eligible,
            )
            for k in analytics.kpis
        ],
        adequacy=AdequacyResponse(
            level=adequacy.level.value,
            eligible=adequacy.eligible,
            checks=[
                AdequacyCheckResponse(
                    check=c.check.value,
                    passed=c.passed,
                    detail=c.detail,
                    value=c.value,
                    threshold=c.threshold,
                )
                for c in adequacy.checks
            ],
            partial_abstentions=adequacy.partial_abstentions,
            quality_flags=adequacy.quality_flags,
        ),
        computed_at=analytics.computed_at,
    )


@router.post("/children/{child_id}/review-periods", response_model=ReviewPeriodResponse, status_code=status.HTTP_201_CREATED)
async def create_review_period(
    child_id: uuid.UUID,
    body: ReviewPeriodCreate,
    user: RequireInterventionist,
    db: DBSession,
) -> ReviewPeriodResponse:
    await authorize_child_access(user, child_id, db)

    from src.backend.models.goal import ReviewPeriod

    period = ReviewPeriod(
        child_id=child_id,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(period)
    await db.flush()

    await audit_service.log_event(
        db=db,
        user_id=user.id,
        action="create_review_period",
        resource_type="review_period",
        resource_id=str(period.id),
        child_id=child_id,
    )
    await db.commit()
    await db.refresh(period)

    return ReviewPeriodResponse(
        id=period.id,
        child_id=period.child_id,
        start_date=period.start_date,
        end_date=period.end_date,
        is_active=period.is_active,
        created_at=period.created_at,
    )
