"""Unit tests for workspace_service — child, actor, goal CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.backend.models.user import Role
from src.backend.schemas.observation_schema import Domain


class TestCreateChild:
    async def test_creates_and_flushes(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.workspace_service.Child") as MockChild:
            mock_child = Mock()
            mock_child.display_name = "Test Child"
            MockChild.return_value = mock_child

            from src.backend.services.workspace_service import create_child

            child = await create_child(db, display_name="Test Child", created_by=uuid.uuid4())
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert child.display_name == "Test Child"

    async def test_sets_optional_date_of_birth(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        dob = datetime(2020, 1, 1, tzinfo=UTC)

        with patch("src.backend.services.workspace_service.Child") as MockChild:
            mock_child = Mock()
            mock_child.date_of_birth = dob
            MockChild.return_value = mock_child

            from src.backend.services.workspace_service import create_child

            child = await create_child(
                db, display_name="Child", created_by=uuid.uuid4(), date_of_birth=dob,
            )
        assert child.date_of_birth == dob


class TestUpdateChild:
    async def test_update_display_name(self):
        from src.backend.services.workspace_service import update_child

        db = AsyncMock()
        db.flush = AsyncMock()
        child = Mock()
        child.display_name = "Old Name"

        result = await update_child(db, child, display_name="New Name")
        assert result.display_name == "New Name"
        db.flush.assert_awaited_once()

    async def test_update_with_none_date_of_birth(self):
        from src.backend.services.workspace_service import update_child

        db = AsyncMock()
        db.flush = AsyncMock()
        child = Mock()
        child.date_of_birth = datetime(2020, 1, 1, tzinfo=UTC)

        result = await update_child(db, child, date_of_birth=None)
        assert result.date_of_birth is None

    async def test_no_change_when_no_args(self):
        from src.backend.services.workspace_service import update_child

        db = AsyncMock()
        db.flush = AsyncMock()
        child = Mock()
        child.display_name = "Original"

        result = await update_child(db, child)
        assert result.display_name == "Original"


class TestInviteActor:
    async def test_creates_assignment(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.workspace_service.ActorAssignment") as MockAssignment:
            mock_assign = Mock()
            mock_assign.role = Role.PARENT
            mock_assign.invitation_email = "parent@test.com"
            MockAssignment.return_value = mock_assign

            from src.backend.services.workspace_service import invite_actor

            assignment = await invite_actor(
                db,
                child_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                role=Role.PARENT,
                invited_by=uuid.uuid4(),
                invitation_email="parent@test.com",
            )
        db.add.assert_called_once()
        assert assignment.role == Role.PARENT
        assert assignment.invitation_email == "parent@test.com"


class TestRevokeActor:
    async def test_sets_revoked_at(self):
        from src.backend.services.workspace_service import revoke_actor

        db = AsyncMock()
        db.flush = AsyncMock()
        assignment = Mock()
        assignment.revoked_at = None
        db.get = AsyncMock(return_value=assignment)

        result = await revoke_actor(db, uuid.uuid4())
        assert result.revoked_at is not None

    async def test_raises_for_unknown_assignment(self):
        from src.backend.services.workspace_service import revoke_actor

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await revoke_actor(db, uuid.uuid4())


class TestGoalVersioning:
    async def test_update_goal_increments_version(self):
        from src.backend.services.workspace_service import update_goal

        db = AsyncMock()
        db.flush = AsyncMock()
        goal = Mock()
        goal.version = 1
        goal.title = "Old"

        result = await update_goal(db, goal, title="New")
        assert result.version == 2
        assert result.title == "New"

    async def test_update_goal_increments_version_multiple_times(self):
        from src.backend.services.workspace_service import update_goal

        db = AsyncMock()
        db.flush = AsyncMock()
        goal = Mock()
        goal.version = 3

        result = await update_goal(db, goal, description="Updated description")
        assert result.version == 4

    async def test_create_goal_sets_fields(self):
        from src.backend.models.goal import GoalType

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.workspace_service.Goal") as MockGoal:
            mock_goal = Mock()
            mock_goal.title = "Test Goal"
            mock_goal.goal_type = GoalType.SHORT_TERM
            mock_goal.domain = Domain.SOCIAL_COMMUNICATION
            MockGoal.return_value = mock_goal

            from src.backend.services.workspace_service import create_goal

            goal = await create_goal(
                db,
                child_id=uuid.uuid4(),
                created_by=uuid.uuid4(),
                goal_type=GoalType.SHORT_TERM,
                domain=Domain.SOCIAL_COMMUNICATION,
                title="Test Goal",
                description="A test goal",
            )
        assert goal.title == "Test Goal"
        assert goal.goal_type == GoalType.SHORT_TERM
        assert goal.domain == Domain.SOCIAL_COMMUNICATION
