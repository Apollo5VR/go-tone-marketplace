"""Test fixtures for Go-Tone Marketplace.

Uses an in-memory SQLite database so tests never touch the real DB.
Each test function gets a fresh database with seeded games.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient


# ── Database isolation ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_db(monkeypatch):
    """Point the app at an in-memory SQLite database for every test.

    ``autouse=True`` means every test gets this automatically — no
    risk of accidentally hitting the real marketplace.db.
    """
    # Use a temp file DB (in-memory would lose tables across connections).
    fd, path = tempfile.mkstemp(suffix=".db", prefix="gotone_test_")
    os.close(fd)

    # Override the DB_PATH that app.database reads at import time.
    import app.database
    monkeypatch.setattr(app.database, "DB_PATH", path)

    # Re-initialise the schema + seed data.
    app.database.init_db()
    app.database.seed_games()

    yield path

    # Cleanup
    try:
        os.unlink(path)
    except OSError:
        pass


# ── Test client ───────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """FastAPI TestClient — no server needed."""
    from app.app import app
    with TestClient(app) as c:
        yield c


# ── Helper factories ──────────────────────────────────────────────────────

@pytest.fixture
def register_user(client):
    """Helper: register a user and return the full response JSON."""
    def _register(email="test@gotone.com", password="secret123", name="Tester"):
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
            "name": name,
        })
        return resp
    return _register


@pytest.fixture
def login_user(client):
    """Helper: login and return the full response JSON."""
    def _login(email="test@gotone.com", password="secret123"):
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": password,
        })
        return resp
    return _login


@pytest.fixture
def auth_headers(register_user, login_user):
    """Register + login a default free-tier user, return Authorization header dict.

    Use this when you need an authenticated user for most tests.
    """
    register_user()
    resp = login_user()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
