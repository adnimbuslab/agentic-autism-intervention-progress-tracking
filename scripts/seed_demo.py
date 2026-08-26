"""Deterministic demo seed script — creates synthetic data for local development.

Usage:
    python -m scripts.seed_demo

All entities are clearly synthetic/demo-only. Idempotent: checks for existing
demo data before inserting. Does NOT use real research data or participant info.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database import async_session_factory
from src.backend.models.actor import ActorAssignment
from src.backend.models.audit import AuditEvent
from src.backend.models.child import Child
from src.backend.models.goal import Goal, GoalType, ReviewPeriod
from src.backend.models.observation import (
    ClarificationTurn,
    Observation,
    ObservationStatus,
    RecordStatus,
    StructuredRecord,
)
from src.backend.models.schedule import ReportingExpectation
from src.backend.models.user import Role, User
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
)
from src.backend.services.auth_service import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEMO_PASSWORD = "DemoPass123!"

DEMO_IDS = {
    "interventionist": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    "parent_a": uuid.UUID("00000000-0000-0000-0000-000000000002"),
    "teacher_b": uuid.UUID("00000000-0000-0000-0000-000000000003"),
    "child_alex": uuid.UUID("00000000-0000-0000-0000-000000000010"),
    "child_sam": uuid.UUID("00000000-0000-0000-0000-000000000011"),
}


async def _user_exists(db: AsyncSession) -> bool:
    result = await db.execute(
        select(User).where(User.id == DEMO_IDS["interventionist"])
    )
    return result.scalar_one_or_none() is not None


async def seed_users(db: AsyncSession) -> dict[str, User]:
    users = {}
    specs = [
        ("interventionist", "demo-interventionist@example.com", "Dr. Demo Interventionist", Role.INTERVENTIONIST),
        ("parent_a", "demo-parent@example.com", "Demo Parent A", Role.PARENT),
        ("teacher_b", "demo-teacher@example.com", "Demo Teacher B", Role.TEACHER),
    ]
    for key, email, name, role in specs:
        user = User(
            id=DEMO_IDS[key],
            email=email,
            hashed_password=hash_password(DEMO_PASSWORD),
            full_name=name,
            role=role,
        )
        db.add(user)
        users[key] = user
    await db.flush()
    logger.info("Created %d demo users", len(users))
    return users


async def seed_children(db: AsyncSession, interventionist: User) -> dict[str, Child]:
    children = {}
    specs = [
        ("child_alex", "Demo Child Alex", date(2020, 3, 15)),
        ("child_sam", "Demo Child Sam", date(2019, 8, 22)),
    ]
    for key, name, dob in specs:
        child = Child(
            id=DEMO_IDS[key],
            display_name=name,
            date_of_birth=datetime(dob.year, dob.month, dob.day, tzinfo=UTC),
            created_by=interventionist.id,
        )
        db.add(child)
        children[key] = child
    await db.flush()
    logger.info("Created %d demo children", len(children))
    return children


async def seed_actors(
    db: AsyncSession,
    interventionist: User,
    parent: User,
    teacher: User,
    children: dict[str, Child],
) -> None:
    assignments = [
        (parent.id, children["child_alex"].id, Role.PARENT, "demo-parent@example.com"),
        (teacher.id, children["child_alex"].id, Role.TEACHER, "demo-teacher@example.com"),
        (parent.id, children["child_sam"].id, Role.PARENT, "demo-parent@example.com"),
    ]
    for user_id, child_id, role, email in assignments:
        aa = ActorAssignment(
            user_id=user_id,
            child_id=child_id,
            role=role,
            invited_by=interventionist.id,
            invitation_email=email,
        )
        db.add(aa)
    await db.flush()
    logger.info("Created %d actor assignments", len(assignments))


async def seed_goals(
    db: AsyncSession, interventionist: User, children: dict[str, Child]
) -> dict[str, Goal]:
    goals = {}
    specs = [
        ("alex_comm", children["child_alex"].id, GoalType.LONG_TERM, Domain.SOCIAL_COMMUNICATION,
         "Functional requesting", "Demo Child Alex will independently request desired items using verbal or gestural modality."),
        ("alex_play", children["child_alex"].id, GoalType.SHORT_TERM, Domain.PLAY,
         "Cooperative play", "Demo Child Alex will engage in cooperative play with peers for at least 3 minutes."),
        ("sam_lang", children["child_sam"].id, GoalType.LONG_TERM, Domain.LANGUAGE,
         "Two-word combinations", "Demo Child Sam will produce two-word combinations to communicate needs."),
    ]
    for key, child_id, goal_type, domain, title, desc in specs:
        goal = Goal(
            child_id=child_id,
            goal_type=goal_type,
            domain=domain,
            title=title,
            description=desc,
            created_by=interventionist.id,
        )
        db.add(goal)
        goals[key] = goal
    await db.flush()
    logger.info("Created %d demo goals", len(goals))
    return goals


async def seed_review_periods(
    db: AsyncSession, children: dict[str, Child]
) -> dict[str, ReviewPeriod]:
    periods = {}
    today = date.today()
    specs = [
        ("alex_period", children["child_alex"].id, today - timedelta(days=60), today),
        ("sam_period", children["child_sam"].id, today - timedelta(days=60), today),
    ]
    for key, child_id, start, end in specs:
        period = ReviewPeriod(child_id=child_id, start_date=start, end_date=end)
        db.add(period)
        periods[key] = period
    await db.flush()
    logger.info("Created %d review periods", len(periods))
    return periods


def _make_record_data(
    domain: str,
    behavior: str,
    modality: str,
    prompt_level: str,
    outcome: str,
    setting: str,
    contributor_role: str,
    obs_date: date,
) -> dict:
    return {
        "child_id": "demo",
        "session_id": "demo",
        "domain": domain,
        "behavior": behavior,
        "modality": modality,
        "prompt_level": prompt_level,
        "outcome": outcome,
        "setting": setting,
        "contributor_role": contributor_role,
        "observation_date": obs_date.isoformat(),
        "goal_context": None,
        "prompt_context": None,
        "duration_seconds": None,
        "confidence": 0.85,
        "abstention_reason": None,
    }


async def seed_observations_alex(
    db: AsyncSession,
    parent: User,
    teacher: User,
    child: Child,
) -> None:
    """Seed 8 observations for Alex — enough for ADEQUATE evidence across settings/contributors."""
    today = date.today()
    obs_specs = [
        (parent, Setting.HOME, today - timedelta(days=50), "Demo observation: Alex pointed to the cookie jar and said 'want cookie' without any prompting.", "social_communication", "pointed and said want cookie", "gestural", "independent", "correct", ContributorRole.PARENT),
        (parent, Setting.HOME, today - timedelta(days=45), "Demo observation: Alex reached for a toy car and vocalized 'car' with a gesture after I modeled the word.", "social_communication", "vocalized car with gesture", "multimodal", "model", "approximation", ContributorRole.PARENT),
        (teacher, Setting.SCHOOL, today - timedelta(days=40), "Demo observation: During circle time, Alex raised their hand and said 'more song' when the music stopped.", "social_communication", "raised hand said more song", "verbal", "independent", "correct", ContributorRole.TEACHER),
        (teacher, Setting.SCHOOL, today - timedelta(days=35), "Demo observation: Alex attempted to join a peer group during recess by approaching and waving.", "play", "approached and waved at peers", "gestural", "independent", "partial", ContributorRole.TEACHER),
        (parent, Setting.HOME, today - timedelta(days=30), "Demo observation: Alex used the picture board to request juice after a verbal prompt from me.", "social_communication", "used picture board for juice", "aac", "verbal", "correct", ContributorRole.PARENT),
        (teacher, Setting.SCHOOL, today - timedelta(days=25), "Demo observation: Alex played alongside two classmates with blocks for about 4 minutes before moving away.", "play", "parallel play with blocks 4 min", "gestural", "gestural", "partial", ContributorRole.TEACHER),
        (parent, Setting.HOME, today - timedelta(days=15), "Demo observation: Alex spontaneously said 'open please' when the snack container was closed.", "social_communication", "said open please spontaneously", "verbal", "independent", "correct", ContributorRole.PARENT),
        (teacher, Setting.SCHOOL, today - timedelta(days=10), "Demo observation: During snack time Alex pointed to the crackers and said 'more' after a gestural prompt.", "social_communication", "pointed and said more", "multimodal", "gestural", "correct", ContributorRole.TEACHER),
    ]

    for user, setting, obs_date, text, domain, behavior, modality, prompt_level, outcome, role in obs_specs:
        obs = Observation(
            child_id=child.id,
            submitted_by=user.id,
            raw_text=text,
            source_type="conversational",
            setting=setting.value,
            status=ObservationStatus.FINALIZED,
            submitted_at=datetime(obs_date.year, obs_date.month, obs_date.day, 10, 0, tzinfo=UTC),
            finalized_at=datetime(obs_date.year, obs_date.month, obs_date.day, 10, 5, tzinfo=UTC),
            conversation_json={"raw_text": text, "clarifications": []},
        )
        db.add(obs)
        await db.flush()

        record = StructuredRecord(
            observation_id=obs.id,
            version=1,
            status=RecordStatus.VALIDATED,
            record_data=_make_record_data(
                domain, behavior, modality, prompt_level, outcome,
                setting.value, role.value, obs_date,
            ),
            validation_result={"is_valid": True, "routing": "accept", "field_validations": [], "messages": []},
            provider="demo_seed",
            model="demo_seed_v1",
            prompt_version="demo",
        )
        db.add(record)

    await db.flush()

    last_obs_stmt = select(Observation).where(Observation.child_id == child.id).order_by(Observation.submitted_at.desc()).limit(1)
    result = await db.execute(last_obs_stmt)
    last_obs = result.scalar_one()
    clarification = ClarificationTurn(
        observation_id=last_obs.id,
        turn_number=1,
        question="Could you describe the type of prompt used — was it a gesture, verbal cue, or physical guidance?",
        answer="It was a gestural prompt — I pointed toward the crackers.",
        created_at=last_obs.submitted_at + timedelta(minutes=1),
        answered_at=last_obs.submitted_at + timedelta(minutes=2),
    )
    db.add(clarification)
    await db.flush()

    logger.info("Created 8 observations with records for Alex (ADEQUATE evidence)")


async def seed_observations_sam(
    db: AsyncSession,
    parent: User,
    child: Child,
) -> None:
    """Seed 2 observations for Sam — LIMITED/INSUFFICIENT evidence (single contributor, single setting)."""
    today = date.today()
    obs_specs = [
        (today - timedelta(days=40), "Demo observation: Sam said 'mama milk' while reaching toward the fridge.", "language", "said mama milk", "verbal", "independent", "correct"),
        (today - timedelta(days=20), "Demo observation: Sam pointed at a book and vocalized 'read' but it was unclear.", "language", "pointed and vocalized read", "multimodal", "independent", "approximation"),
    ]

    for obs_date, text, domain, behavior, modality, prompt_level, outcome in obs_specs:
        obs = Observation(
            child_id=child.id,
            submitted_by=parent.id,
            raw_text=text,
            source_type="conversational",
            setting=Setting.HOME.value,
            status=ObservationStatus.FINALIZED,
            submitted_at=datetime(obs_date.year, obs_date.month, obs_date.day, 14, 0, tzinfo=UTC),
            finalized_at=datetime(obs_date.year, obs_date.month, obs_date.day, 14, 3, tzinfo=UTC),
            conversation_json={"raw_text": text, "clarifications": []},
        )
        db.add(obs)
        await db.flush()

        record = StructuredRecord(
            observation_id=obs.id,
            version=1,
            status=RecordStatus.VALIDATED,
            record_data=_make_record_data(
                domain, behavior, modality, prompt_level, outcome,
                Setting.HOME.value, ContributorRole.PARENT.value, obs_date,
            ),
            validation_result={"is_valid": True, "routing": "accept", "field_validations": [], "messages": []},
            provider="demo_seed",
            model="demo_seed_v1",
            prompt_version="demo",
        )
        db.add(record)

    await db.flush()
    logger.info("Created 2 observations with records for Sam (LIMITED evidence)")


async def seed_corrected_record(db: AsyncSession, interventionist: User, child: Child) -> None:
    """Add a corrected version of Alex's first record to demonstrate versioning."""
    stmt = (
        select(StructuredRecord)
        .join(Observation, StructuredRecord.observation_id == Observation.id)
        .where(Observation.child_id == child.id)
        .order_by(StructuredRecord.created_at)
        .limit(1)
    )
    result = await db.execute(stmt)
    first_record = result.scalar_one_or_none()
    if first_record is None:
        return

    corrected_data = dict(first_record.record_data)
    corrected_data["prompt_level"] = "gestural"

    corrected = StructuredRecord(
        observation_id=first_record.observation_id,
        version=2,
        status=RecordStatus.CORRECTED,
        record_data=corrected_data,
        validation_result=first_record.validation_result,
        corrected_by=interventionist.id,
        correction_reason="Corrected prompt level: parent clarified gestural prompt was used (demo)",
        previous_version_id=first_record.id,
        provider=first_record.provider,
        model=first_record.model,
        prompt_version=first_record.prompt_version,
    )
    db.add(corrected)
    await db.flush()
    logger.info("Created corrected record version for Alex's first observation")


async def seed_schedules(
    db: AsyncSession,
    children: dict[str, Child],
    goals: dict[str, Goal],
) -> None:
    specs = [
        (children["child_alex"].id, goals["alex_comm"].id, 7, "Weekly home observation"),
        (children["child_alex"].id, goals["alex_play"].id, 14, "Biweekly school observation"),
    ]
    for child_id, goal_id, cadence, desc in specs:
        sched = ReportingExpectation(
            child_id=child_id,
            goal_id=goal_id,
            cadence_days=cadence,
            description=desc,
        )
        db.add(sched)
    await db.flush()
    logger.info("Created %d schedules", len(specs))


async def seed_audit_events(db: AsyncSession, interventionist: User, children: dict[str, Child]) -> None:
    events = [
        ("create_child", "child", str(children["child_alex"].id), children["child_alex"].id, {"display_name": "Demo Child Alex"}),
        ("create_child", "child", str(children["child_sam"].id), children["child_sam"].id, {"display_name": "Demo Child Sam"}),
    ]
    for action, resource_type, resource_id, child_id, detail in events:
        event = AuditEvent(
            user_id=interventionist.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            child_id=child_id,
            detail=detail,
        )
        db.add(event)
    await db.flush()
    logger.info("Created %d audit events", len(events))


async def seed_all() -> None:
    async with async_session_factory() as db:
        if await _user_exists(db):
            logger.info("Demo data already exists — skipping seed (idempotent)")
            return

        users = await seed_users(db)
        children = await seed_children(db, users["interventionist"])
        await seed_actors(db, users["interventionist"], users["parent_a"], users["teacher_b"], children)
        goals = await seed_goals(db, users["interventionist"], children)
        await seed_review_periods(db, children)
        await seed_observations_alex(db, users["parent_a"], users["teacher_b"], children["child_alex"])
        await seed_observations_sam(db, users["parent_a"], children["child_sam"])
        await seed_corrected_record(db, users["interventionist"], children["child_alex"])
        await seed_schedules(db, children, goals)
        await seed_audit_events(db, users["interventionist"], children)

        await db.commit()
        logger.info("Demo seed complete")
        logger.info("  Interventionist: demo-interventionist@example.com / %s", DEMO_PASSWORD)
        logger.info("  Parent:          demo-parent@example.com / %s", DEMO_PASSWORD)
        logger.info("  Teacher:         demo-teacher@example.com / %s", DEMO_PASSWORD)
        logger.info("  Alex: ADEQUATE evidence (8 obs, 2 contributors, 2 settings)")
        logger.info("  Sam:  LIMITED evidence (2 obs, 1 contributor, 1 setting)")


if __name__ == "__main__":
    asyncio.run(seed_all())
