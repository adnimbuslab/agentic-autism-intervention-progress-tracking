"""Unit tests for auth_service — password hashing, JWT creation/validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from src.backend.config import settings
from src.backend.models.user import Role


class TestPasswordHashing:
    def test_hash_password_returns_different_from_plain(self):
        with patch("src.backend.services.auth_service._pwd_context") as ctx:
            ctx.hash.return_value = "$2b$12$mockedhash"
            from src.backend.services.auth_service import hash_password

            result = hash_password("securepass123")
            ctx.hash.assert_called_once_with("securepass123")
            assert result == "$2b$12$mockedhash"

    def test_verify_password_delegates_to_context(self):
        with patch("src.backend.services.auth_service._pwd_context") as ctx:
            ctx.verify.return_value = True
            from src.backend.services.auth_service import verify_password

            assert verify_password("plain", "hashed") is True
            ctx.verify.assert_called_once_with("plain", "hashed")

    def test_verify_password_wrong_returns_false(self):
        with patch("src.backend.services.auth_service._pwd_context") as ctx:
            ctx.verify.return_value = False
            from src.backend.services.auth_service import verify_password

            assert verify_password("wrong", "hashed") is False


class TestCreateAccessToken:
    def test_token_contains_sub_claim(self):
        from src.backend.services.auth_service import create_access_token

        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == str(uid)

    def test_token_contains_exp_claim(self):
        from src.backend.services.auth_service import create_access_token

        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert "exp" in payload

    def test_token_fails_with_wrong_key(self):
        from src.backend.services.auth_service import create_access_token

        uid = uuid.uuid4()
        token = create_access_token(uid)
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-secret-key", algorithms=[settings.jwt_algorithm])


class TestCreateUser:
    async def test_create_user_adds_to_session(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.auth_service.hash_password", return_value="$2b$12$fakedhash"):
            from src.backend.services.auth_service import create_user

            user = await create_user(
                db,
                email="test@example.com",
                password="securepass123",
                full_name="Test User",
                role=Role.INTERVENTIONIST,
            )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.role == Role.INTERVENTIONIST
        assert user.hashed_password == "$2b$12$fakedhash"

    async def test_create_user_does_not_store_plaintext(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.auth_service.hash_password", return_value="$2b$12$hashed"):
            from src.backend.services.auth_service import create_user

            user = await create_user(
                db, email="a@b.com", password="plaintext", full_name="A", role=Role.PARENT,
            )
        assert user.hashed_password != "plaintext"


class TestAuthenticateUser:
    async def test_authenticate_valid_user(self):
        db = AsyncMock()
        user_mock = MagicMock()
        user_mock.hashed_password = "$2b$12$somehash"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("src.backend.services.auth_service.verify_password", return_value=True):
            from src.backend.services.auth_service import authenticate_user

            result = await authenticate_user(db, "test@example.com", "securepass123")
        assert result is user_mock

    async def test_authenticate_wrong_password(self):
        db = AsyncMock()
        user_mock = MagicMock()
        user_mock.hashed_password = "$2b$12$somehash"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("src.backend.services.auth_service.verify_password", return_value=False):
            from src.backend.services.auth_service import authenticate_user

            result = await authenticate_user(db, "test@example.com", "wrongpassword")
        assert result is None

    async def test_authenticate_unknown_email(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        from src.backend.services.auth_service import authenticate_user

        result = await authenticate_user(db, "nobody@example.com", "anything")
        assert result is None


class TestGetUserByEmail:
    async def test_returns_user_when_found(self):
        db = AsyncMock()
        user_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user_mock
        db.execute = AsyncMock(return_value=result_mock)

        from src.backend.services.auth_service import get_user_by_email

        result = await get_user_by_email(db, "found@example.com")
        assert result is user_mock

    async def test_returns_none_when_not_found(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        from src.backend.services.auth_service import get_user_by_email

        result = await get_user_by_email(db, "missing@example.com")
        assert result is None
