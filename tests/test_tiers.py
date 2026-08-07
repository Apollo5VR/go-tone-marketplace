"""Access-control tests: free (unsubscribed) vs paid (subscribed) users.

The subscription model means users don't buy games individually.  Instead:
- Free-tier users can play free games (is_premium=0).
- Paid-tier users can play everything — free + premium.
"""

import pytest
from app.auth_utils import hash_password, create_token
from app.database import get_db


# ── Helpers ────────────────────────────────────────────────────────────────

def _create_user(email: str, tier: str) -> dict:
    """Insert a user directly into the test DB and return their JWT."""
    import secrets
    user_id = secrets.token_hex(16)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, tier) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, hash_password("secret123"), "Test User", tier),
        )
        conn.commit()

    token = create_token(user_id, email, tier)
    return {"Authorization": f"Bearer {token}"}


def _find_game(client, premium: bool) -> dict:
    """Return the first free or premium game from the store."""
    resp = client.get("/api/games")
    games = resp.json()
    for g in games:
        if g["is_premium"] == premium:
            return g
    pytest.fail(f"No {'premium' if premium else 'free'} game found in seed data")


# ══════════════════════════════════════════════════════════════════════════
#  Free-tier (unsubscribed) user
# ══════════════════════════════════════════════════════════════════════════

class TestFreeTier:
    """A user with tier='free' — the default after registration."""

    @pytest.fixture
    def free_headers(self):
        """JWT for a free-tier user."""
        return _create_user("free@gotone.com", "free")

    def test_can_add_free_game_to_library(self, client, free_headers):
        """Free users should be able to add free (non-premium) games."""
        game = _find_game(client, premium=False)

        resp = client.post(
            f"/api/library/{game['slug']}/purchase",
            headers=free_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_cannot_purchase_premium_game(self, client, free_headers):
        """Free users attempting to get a premium game get HTTP 402."""
        game = _find_game(client, premium=True)

        resp = client.post(
            f"/api/library/{game['slug']}/purchase",
            headers=free_headers,
        )

        assert resp.status_code == 402
        assert "upgrade" in resp.json()["detail"].lower()

    def test_library_lists_purchased_free_games(self, client, free_headers):
        """After adding a free game, it shows up in the library."""
        game = _find_game(client, premium=False)
        client.post(f"/api/library/{game['slug']}/purchase", headers=free_headers)

        resp = client.get("/api/library", headers=free_headers)
        library = resp.json()

        owned_slugs = [g["slug"] for g in library["owned"]]
        assert game["slug"] in owned_slugs

    def test_can_submit_scores(self, client, free_headers):
        """Free users can play games and submit scores."""
        game = _find_game(client, premium=False)
        # Need to own it first
        client.post(f"/api/library/{game['slug']}/purchase", headers=free_headers)

        resp = client.post(
            f"/api/games/{game['slug']}/score",
            headers=free_headers,
            json={"weight": 20, "score": 1500, "reps": 10, "meters": 50.5},
        )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_can_view_leaderboard(self, client, free_headers):
        """Leaderboards are public — no auth needed, but free user can access."""
        resp = client.get("/api/leaderboard/rhythm-pull")
        assert resp.status_code == 200
        assert resp.json()["game"] == "rhythm-pull"


# ══════════════════════════════════════════════════════════════════════════
#  Paid-tier (subscribed) user
# ══════════════════════════════════════════════════════════════════════════

class TestPaidTier:
    """A user with tier='paid' — simulates an active subscription."""

    @pytest.fixture
    def paid_headers(self):
        """JWT for a paid-tier user."""
        return _create_user("paid@gotone.com", "paid")

    def test_can_purchase_premium_game(self, client, paid_headers):
        """Paid users can add premium games to their library."""
        game = _find_game(client, premium=True)

        resp = client.post(
            f"/api/library/{game['slug']}/purchase",
            headers=paid_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_can_add_free_game_too(self, client, paid_headers):
        """Paid users can also add free games."""
        game = _find_game(client, premium=False)

        resp = client.post(
            f"/api/library/{game['slug']}/purchase",
            headers=paid_headers,
        )

        assert resp.status_code == 200

    def test_library_contains_both_free_and_premium(self, client, paid_headers):
        """After adding both types, the library shows everything."""
        free_game = _find_game(client, premium=False)
        premium_game = _find_game(client, premium=True)

        client.post(f"/api/library/{free_game['slug']}/purchase", headers=paid_headers)
        client.post(f"/api/library/{premium_game['slug']}/purchase", headers=paid_headers)

        resp = client.get("/api/library", headers=paid_headers)
        library = resp.json()

        owned_slugs = [g["slug"] for g in library["owned"]]
        assert free_game["slug"] in owned_slugs
        assert premium_game["slug"] in owned_slugs


# ══════════════════════════════════════════════════════════════════════════
#  Unauthenticated user
# ══════════════════════════════════════════════════════════════════════════

class TestUnauthenticated:
    """No auth at all — the public storefront experience."""

    def test_can_browse_all_games(self, client):
        """Anyone can see the full game catalog."""
        resp = client.get("/api/games")
        assert resp.status_code == 200
        assert len(resp.json()) == 8  # seeded count

    def test_can_view_game_detail(self, client):
        """Game detail pages are public."""
        resp = client.get("/api/games/dragon-pull")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Dragon Pull"

    def test_cannot_access_library(self, client):
        """No token → cannot see library."""
        resp = client.get("/api/library")
        assert resp.status_code == 401

    def test_cannot_purchase(self, client):
        """No token → cannot add games to library."""
        resp = client.post("/api/library/rhythm-pull/purchase")
        assert resp.status_code == 401

    def test_can_view_leaderboard(self, client):
        """Leaderboards are public."""
        resp = client.get("/api/leaderboard/dragon-pull")
        assert resp.status_code == 200
