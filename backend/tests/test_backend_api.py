import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
import services.session_manager as session_manager
from middleware.auth import get_current_user
from routers import auth, profile, sessions
from services.auth import create_access_token, hash_password


VALID_PRIVATE_KEY = """-----BEGIN OPENSSH PRIVATE KEY-----
key-material
-----END OPENSSH PRIVATE KEY-----"""


async def _insert_user(
    username: str,
    password: str = "password",
    *,
    is_active: bool = True,
    is_admin: bool = False,
    private_key: str | None = None,
) -> int:
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """INSERT INTO users
               (username, email, hashed_password, is_active, is_admin, ssh_private_key)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                username,
                f"{username}@example.com",
                hash_password(password),
                1 if is_active else 0,
                1 if is_admin else 0,
                private_key,
            ),
        )
        await db.commit()
        async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            return row[0]


async def _insert_session(
    session_id: str,
    user_id: int,
    *,
    container_id: str = "container-x",
    status: str = "active",
) -> None:
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """INSERT INTO sessions (id, user_id, container_id, status)
               VALUES (?, ?, ?, ?)""",
            (session_id, user_id, container_id, status),
        )
        await db.commit()


def _build_app(*routers) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return app


class TempDbMixin:
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        self.original_session_db_path = session_manager.DB_PATH
        self.db_path = os.path.join(self.tempdir.name, "test.db")
        database.DB_PATH = self.db_path
        session_manager.DB_PATH = self.db_path
        asyncio.run(database.init_db())

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        session_manager.DB_PATH = self.original_session_db_path
        self.tempdir.cleanup()


class AuthApiTests(TempDbMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.alice_id = asyncio.run(_insert_user("alice"))
        self.disabled_id = asyncio.run(_insert_user("disabled", is_active=False))
        self.client = TestClient(_build_app(auth.router))

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_login_returns_access_token_for_valid_credentials(self):
        response = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "password"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["token_type"], "bearer")
        self.assertGreater(body["expires_in"], 0)

    def test_login_rejects_invalid_password(self):
        response = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid credentials")

    def test_login_rejects_deactivated_account(self):
        response = self.client.post(
            "/api/auth/login",
            data={"username": "disabled", "password": "password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Account deactivated")


class ProfileApiTests(TempDbMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.user_id = asyncio.run(_insert_user("alice"))
        self.app = _build_app(auth.router, profile.router)
        self.app.dependency_overrides[get_current_user] = self._current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def _current_user(self):
        return {
            "id": self.user_id,
            "username": "alice",
            "email": "alice@example.com",
            "is_active": True,
            "is_admin": False,
        }

    def test_profile_private_key_lifecycle(self):
        response = self.client.get("/api/profile/ssh-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"has_private_key": False})

        response = self.client.put(
            "/api/profile/ssh-key",
            json={"ssh_private_key": VALID_PRIVATE_KEY},
        )
        self.assertEqual(response.status_code, 204)

        response = self.client.get("/api/profile/ssh-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"has_private_key": True})

        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_ssh_key"])

        response = self.client.delete("/api/profile/ssh-key")
        self.assertEqual(response.status_code, 204)

        response = self.client.get("/api/profile/ssh-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"has_private_key": False})

    def test_profile_rejects_invalid_private_key(self):
        response = self.client.put(
            "/api/profile/ssh-key",
            json={"ssh_private_key": "not-a-private-key"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid SSH private key format")


class SessionsApiTests(TempDbMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.user_id = asyncio.run(_insert_user("alice"))
        self.other_user_id = asyncio.run(_insert_user("bob"))
        self.client = TestClient(_build_app(sessions.router))
        self.token = create_access_token(self.user_id, False)
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_create_session_returns_created_session(self):
        fake_session = {
            "id": "session-1",
            "user_id": self.user_id,
            "container_id": "container-1",
            "status": "active",
            "created_at": "2026-01-01 00:00:00",
            "last_activity": "2026-01-01 00:00:00",
            "terminated_at": None,
            "termination_reason": None,
        }

        with patch.object(session_manager, "create_session", AsyncMock(return_value=fake_session)) as create_mock:
            response = self.client.post("/api/sessions", headers=self.headers)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "session-1")
        create_mock.assert_awaited_once_with(self.user_id)

    def test_create_session_returns_429_when_limit_reached(self):
        with patch.object(session_manager, "create_session", AsyncMock(return_value=None)):
            response = self.client.post("/api/sessions", headers=self.headers)

        self.assertEqual(response.status_code, 429)
        self.assertIn("Maximum", response.json()["detail"])

    def test_get_session_rejects_other_users_session(self):
        asyncio.run(_insert_session("session-owned-by-bob", self.other_user_id))

        response = self.client.get("/api/sessions/session-owned-by-bob", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Session not found")

    def test_delete_session_terminates_owned_session(self):
        asyncio.run(_insert_session("session-owned-by-alice", self.user_id))

        with patch.object(session_manager, "terminate_session", AsyncMock()) as terminate_mock:
            response = self.client.delete("/api/sessions/session-owned-by-alice", headers=self.headers)

        self.assertEqual(response.status_code, 204)
        terminate_mock.assert_awaited_once_with("session-owned-by-alice", "user_request")


class SessionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        self.original_session_db_path = session_manager.DB_PATH
        self.db_path = os.path.join(self.tempdir.name, "test.db")
        database.DB_PATH = self.db_path
        session_manager.DB_PATH = self.db_path
        await database.init_db()

    async def asyncTearDown(self):
        database.DB_PATH = self.original_db_path
        session_manager.DB_PATH = self.original_session_db_path
        self.tempdir.cleanup()

    async def test_create_session_injects_private_key_when_present(self):
        user_id = await _insert_user("carol", private_key=VALID_PRIVATE_KEY)

        with (
            patch.object(session_manager.dm, "create_container", AsyncMock(return_value="container-1")),
            patch.object(session_manager.dm, "inject_ssh_keys", AsyncMock()) as inject_mock,
        ):
            session = await session_manager.create_session(user_id)

        self.assertIsNotNone(session)
        inject_mock.assert_awaited_once_with("container-1", VALID_PRIVATE_KEY)

    async def test_create_session_skips_injection_without_private_key(self):
        user_id = await _insert_user("dave", private_key=None)

        with (
            patch.object(session_manager.dm, "create_container", AsyncMock(return_value="container-2")),
            patch.object(session_manager.dm, "inject_ssh_keys", AsyncMock()) as inject_mock,
        ):
            session = await session_manager.create_session(user_id)

        self.assertIsNotNone(session)
        inject_mock.assert_not_awaited()

    async def test_create_session_continues_when_injection_fails(self):
        user_id = await _insert_user("erin", private_key=VALID_PRIVATE_KEY)

        with (
            patch.object(session_manager.dm, "create_container", AsyncMock(return_value="container-3")),
            patch.object(session_manager.dm, "inject_ssh_keys", AsyncMock(side_effect=RuntimeError("boom"))),
        ):
            session = await session_manager.create_session(user_id)

        self.assertIsNotNone(session)
        self.assertEqual(session["container_id"], "container-3")


if __name__ == "__main__":
    unittest.main()
