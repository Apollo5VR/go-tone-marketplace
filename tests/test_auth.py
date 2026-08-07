"""Signup and login flow tests."""

import pytest


class TestRegister:
    """Registration endpoint: POST /api/auth/register"""

    def test_success_returns_token_and_user(self, client):
        """A successful registration returns a JWT + user object with tier='free'."""
        resp = client.post("/api/auth/register", json={
            "email": "new@gotone.com",
            "password": "strongpass1",
            "name": "New User",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "new@gotone.com"
        assert body["user"]["name"] == "New User"
        assert body["user"]["tier"] == "free", "New accounts default to free tier"
        assert "id" in body["user"]

    def test_duplicate_email_is_rejected(self, client, register_user):
        """Registering the same email twice returns 409."""
        register_user(email="dup@gotone.com")
        resp = register_user(email="dup@gotone.com")

        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()


class TestLogin:
    """Login endpoint: POST /api/auth/login"""

    def test_success_returns_token_and_user(self, client, register_user):
        """Login with valid credentials returns a JWT and user data."""
        register_user(email="login@gotone.com")
        resp = client.post("/api/auth/login", json={
            "email": "login@gotone.com",
            "password": "secret123",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "login@gotone.com"

    def test_wrong_password_returns_401(self, client, register_user):
        """Wrong password gets a 401."""
        register_user(email="wrongpw@gotone.com")
        resp = client.post("/api/auth/login", json={
            "email": "wrongpw@gotone.com",
            "password": "not-the-password",
        })

        assert resp.status_code == 401

    def test_nonexistent_email_returns_401(self, client):
        """Email that was never registered gets a 401."""
        resp = client.post("/api/auth/login", json={
            "email": "ghost@gotone.com",
            "password": "whatever",
        })

        assert resp.status_code == 401


class TestProfile:
    """Profile endpoint: GET /api/user/profile"""

    def test_with_valid_token_returns_profile(self, client, auth_headers):
        """A valid bearer token returns the user's profile."""
        resp = client.get("/api/user/profile", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "test@gotone.com"
        assert body["tier"] == "free"

    def test_without_token_returns_401(self, client):
        """No Authorization header → 401."""
        resp = client.get("/api/user/profile")
        assert resp.status_code == 401

    def test_with_invalid_token_returns_401(self, client):
        """A garbled token → 401."""
        resp = client.get("/api/user/profile", headers={
            "Authorization": "Bearer this.is.not.a.valid.jwt",
        })
        assert resp.status_code == 401
