"""API routes for Go-Tone Marketplace."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
import secrets
from datetime import datetime

from app.database import get_db
from app.auth_utils import (
    hash_password, verify_password, create_token, decode_token,
)
from app.schemas import (
    UserCreate, UserLogin, UserResponse, TokenResponse, GameResponse,
    ReviewCreate, ScoreCreate,
)

router = APIRouter()


# ── Auth ────────────────────────────────────────────────────────────────────

@router.post("/api/auth/register")
def auth_register(data: UserCreate):
    """Register a new account."""
    import sqlite3
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (data.email,)).fetchone()
        if existing:
            raise HTTPException(409, "Email already registered")

        user_id = secrets.token_hex(16)
        pw_hash = hash_password(data.password)
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, tier) VALUES (?, ?, ?, ?, 'free')",
            (user_id, data.email, pw_hash, data.name),
        )
        conn.commit()

    token = create_token(user_id, data.email, "free")
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=data.email,
            name=data.name,
            tier="free",
            created_at=datetime.utcnow().isoformat(),
        ),
    )


@router.post("/api/auth/login")
def auth_login(data: UserLogin):
    """Login and get JWT token."""
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (data.email,)).fetchone()
        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(401, "Invalid credentials")

    token = create_token(user["id"], user["email"], user["tier"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            tier=user["tier"],
            created_at=user["created_at"],
        ),
    )


@router.get("/api/user/profile")
def get_profile(authorization: str = None):
    """Get current user profile (JWT required)."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

    return UserResponse(
        id=user["id"], email=user["email"], name=user["name"],
        tier=user["tier"], created_at=user["created_at"],
    )


def _get_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(401, "Invalid auth scheme")
    return token


# ── Games / Storefront ─────────────────────────────────────────────────────

@router.get("/api/games")
def list_games(category: str = "all", difficulty: int = None, premium: bool = None):
    """List games with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM games WHERE 1=1"
        params = []
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if difficulty:
            query += " AND difficulty = ?"
            params.append(difficulty)
        if premium is not None:
            query += " AND is_premium = ?"
            params.append(1 if premium else 0)
        query += " ORDER BY title"

        rows = conn.execute(query, params).fetchall()

    return [GameResponse(**dict(r)) for r in rows]


@router.get("/api/games/{slug}")
def get_game(slug: str):
    """Get game detail."""
    with get_db() as conn:
        game = conn.execute("SELECT * FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        reviews = conn.execute(
            "SELECT r.*, u.name AS reviewer_name FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.game_id = ? ORDER BY r.created_at DESC LIMIT 10",
            (game["id"],),
        ).fetchall()

    game_dict = dict(game)
    game_dict["is_premium"] = bool(game_dict["is_premium"])
    game_dict["reviews"] = [dict(r) for r in reviews]
    return game_dict


@router.get("/api/leaderboard/{slug}")
def get_leaderboard(slug: str, limit: int = 10):
    """Get top scores for a game."""
    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        scores = conn.execute(
            """SELECT s.*, u.name, u.tier
               FROM scores s JOIN users u ON s.user_id = u.id
               WHERE s.game_id = ?
               ORDER BY s.score DESC, s.created_at ASC
               LIMIT ?""",
            (game["id"], limit),
        ).fetchall()

    return {"game": slug, "leaderboard": [dict(s) for s in scores]}


# ── Reviews ─────────────────────────────────────────────────────────────────

@router.post("/api/games/{slug}/reviews")
def add_review(slug: str, data: ReviewCreate, authorization: str = None):
    """Add a review (requires auth)."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    if not (1 <= data.rating <= 5):
        raise HTTPException(400, "Rating must be 1-5")

    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        review_id = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO reviews (id, user_id, game_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
            (review_id, payload["sub"], game["id"], data.rating, data.comment),
        )

        # Update game rating
        new_avg = conn.execute(
            "SELECT AVG(rating), COUNT(*) FROM reviews WHERE game_id = ?",
            (game["id"],),
        ).fetchone()
        conn.execute(
            "UPDATE games SET rating = ?, reviews_count = ? WHERE id = ?",
            (new_avg[0] or 0, new_avg[1], game["id"]),
        )
        conn.commit()

    return {"ok": True, "review_id": review_id}


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  ⚠️  TEMPORARY DEMO MODE (see /app.py route_override)                       ║
# ║  In production we'd do session cookies.                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝

# ── Library (user's owned games) ─────────────────────────────────────────────

@router.get("/api/library")
def get_library(authorization: str = None):
    """Get user's owned games."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        items = conn.execute(
            """SELECT g.* FROM games g
               JOIN user_games ug ON g.id = ug.game_id
               WHERE ug.user_id = ?
               ORDER BY ug.purchased_at DESC""",
            (payload["sub"],),
        ).fetchall()
        free = conn.execute(
            "SELECT * FROM games WHERE is_premium = 0 AND NOT EXISTS (SELECT 1 FROM user_games WHERE game_id = games.id AND user_id = ?)",
            (payload["sub"],),
        ).fetchall()

    owned = [GameResponse(**dict(r)) for r in items]
    free_games = [GameResponse(**dict(r)) for r in free]

    return {"owned": owned, "free": free_games}


@router.post("/api/library/{game_slug}/purchase")
def purchase_game(game_slug: str, authorization: str = None):
    """Purchase a game (demo: free checkout)."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        game = conn.execute("SELECT * FROM games WHERE slug = ?", (game_slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        if not game["is_premium"]:
            # Free game
            conn.execute(
                "INSERT OR IGNORE INTO user_games (user_id, game_id) VALUES (?, ?)",
                (payload["sub"], game["id"]),
            )
            conn.commit()
            return {"ok": True, "message": "Game added to library!", "game": dict(game)}

        # Premium game: simulate Stripe checkout
        player = payload.get("tier", "free")
        if player == "free":
            raise HTTPException(402, "Upgrade to a paid tier to purchase premium games")

        conn.execute(
            "INSERT INTO user_games (user_id, game_id) VALUES (?, ?)",
            (payload["sub"], game["id"]),
        )
        conn.commit()
        return {"ok": True, "message": "Purchase successful!", "game": dict(game)}


# ── Scores ────────────────────────────────────────────────────────────────────

@router.post("/api/games/{slug}/score")
def submit_score(slug: str, data: ScoreCreate, authorization: str = None):
    """Submit a game score."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        score_id = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO scores (id, user_id, game_id, weight, score, reps, meters) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (score_id, payload["sub"], game["id"], data.weight, data.score, data.reps, data.meters),
        )
        conn.commit()

    return {"ok": True, "score_id": score_id}


# ── Wishlist ──────────────────────────────────────────────────────────────────

@router.get("/api/wishlist")
def get_wishlist(authorization: str = None):
    """Get user's wishlist."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        items = conn.execute(
            "SELECT g.* FROM games g JOIN wishlist w ON g.id = w.game_id WHERE w.user_id = ?",
            (payload["sub"],),
        ).fetchall()

    return [GameResponse(**dict(r)) for r in items]


@router.post("/api/wishlist")
def add_wishlist(item: WishlistAdd, authorization: str = None):
    """Add a game to wishlist."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE id = ?", (item.game_id,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        conn.execute(
            "INSERT OR IGNORE INTO wishlist (user_id, game_id) VALUES (?, ?)",
            (payload["sub"], item.game_id),
        )
        conn.commit()

    return {"ok": True}


@router.delete("/api/wishlist/{game_id}")
def remove_wishlist(game_id: str, authorization: str = None):
    """Remove from wishlist."""
    token = _get_token(authorization)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")

    with get_db() as conn:
        conn.execute(
            "DELETE FROM wishlist WHERE user_id = ? AND game_id = ?",
            (payload["sub"], game_id),
        )
        conn.commit()

    return {"ok": True}
