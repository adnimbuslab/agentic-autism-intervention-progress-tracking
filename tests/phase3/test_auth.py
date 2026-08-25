"""Tests for auth endpoints: register, login, me."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_user
from src.backend.models.user import Role


class TestRegister:
    async def test_register_creates_user(self, unauth_client, mock_db):
        mock_u = make_user(email="new@example.com")
        with (
            patch(
                "src.backend.services.auth_service.get_user_by_email",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.backend.services.auth_service.create_user",
                new_callable=AsyncMock,
                return_value=mock_u,
            ),
        ):
            resp = await unauth_client.post(
                "/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "securepass123",
                    "full_name": "New User",
                    "role": "interventionist",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert data["role"] == "interventionist"

    async def test_register_duplicate_email_returns_409(self, unauth_client, mock_db):
        existing = make_user(email="dup@example.com")
        with patch(
            "src.backend.services.auth_service.get_user_by_email",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            resp = await unauth_client.post(
                "/auth/register",
                json={
                    "email": "dup@example.com",
                    "password": "securepass123",
                    "full_name": "Dup User",
                    "role": "parent",
                },
            )
        assert resp.status_code == 409


class TestLogin:
    async def test_login_valid_credentials_returns_token(self, unauth_client, mock_db):
        mock_u = make_user()
        with (
            patch(
                "src.backend.services.auth_service.authenticate_user",
                new_callable=AsyncMock,
                return_value=mock_u,
            ),
            patch(
                "src.backend.services.auth_service.create_access_token",
                return_value="fake.jwt.token",
            ),
        ):
            resp = await unauth_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "password123"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_invalid_credentials_returns_401(self, unauth_client, mock_db):
        with patch(
            "src.backend.services.auth_service.authenticate_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await unauth_client.post(
                "/auth/login",
                json={"email": "wrong@example.com", "password": "badpass"},
            )
        assert resp.status_code == 401


class TestMe:
    async def test_me_returns_current_user(
        self, interventionist_client, interventionist_user
    ):
        resp = await interventionist_client.get("/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == interventionist_user.email
        assert data["role"] == "interventionist"
