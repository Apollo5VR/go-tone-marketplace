"""Admin panel — separate router, auth-guarded, invisible from public nav."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Body, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database import get_db
from app.auth_utils import (
    hash_password, verify_password, create_token, decode_token, require_admin,
)

router = APIRouter(prefix="/admin")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ── Auth helper ──────────────────────────────────────────────────────────────

def _get_admin_token(authorization: "str | None") -> dict:
    """Extract and validate admin JWT from Bearer header."""
    if not authorization:
        raise HTTPException(401, "Unauthorized")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(401, "Invalid auth scheme")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")
    require_admin(payload)
    return payload


# ── Admin login ──────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login page — separate from public login."""
    return templates.TemplateResponse(request, "admin/login.html", context={"title": "Admin Login"})


@router.post("/api/login")
def admin_login(email: str = Body(...), password: str = Body(...)):
    """Admin login endpoint."""
    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if not user:
            raise HTTPException(401, "Invalid credentials")

        if not user["is_admin"]:
            raise HTTPException(403, "Admin access required")

        if not user["is_active"]:
            raise HTTPException(403, "Account deactivated")

        if not verify_password(password, user["password_hash"]):
            raise HTTPException(401, "Invalid credentials")

    token = create_token(user["id"], user["email"], user["tier"], is_admin=True)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "tier": user["tier"],
        },
    }


# ── Admin dashboard ─────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(request, "admin/dashboard.html", context={"title": "Admin Dashboard"})


@router.get("/api/stats")
def admin_stats(authorization: Optional[str] = Header(None)):
    """Dashboard statistics."""
    _get_admin_token(authorization)
    with get_db() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        subscribed = conn.execute("SELECT COUNT(*) FROM users WHERE tier IN ('monthly', 'annual')").fetchone()[0]
        free_users = conn.execute("SELECT COUNT(*) FROM users WHERE tier = 'free'").fetchone()[0]
        active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
        total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        total_scores = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        avg_rating = conn.execute("SELECT AVG(rating) FROM games").fetchone()[0] or 0

        # Recent signups
        recent_users = conn.execute(
            "SELECT id, email, name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

    return {
        "total_users": total_users,
        "subscribed": subscribed,
        "free_users": free_users,
        "active_users": active_users,
        "total_games": total_games,
        "total_scores": total_scores,
        "total_reviews": total_reviews,
        "avg_rating": round(avg_rating, 2),
        "recent_users": [dict(r) for r in recent_users],
    }


# ── Game management ─────────────────────────────────────────────────────────

@router.get("/games", response_class=HTMLResponse)
async def admin_games_page(request: Request):
    return templates.TemplateResponse(request, "admin/games.html", context={"title": "Manage Games"})


@router.get("/api/games")
def list_admin_games(authorization: Optional[str] = Header(None)):
    """List all games for admin."""
    _get_admin_token(authorization)
    with get_db() as conn:
        games = conn.execute("SELECT * FROM games ORDER BY title").fetchall()
    return [dict(g) for g in games]


@router.post("/api/games")
def create_game(data: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Create a new game."""
    _get_admin_token(authorization)

    slug = data.get("slug", data["title"].lower().replace(" ", "-"))
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if existing:
            raise HTTPException(409, "Game slug already exists")

        game_id = secrets.token_hex(16)
        conn.execute(
            """INSERT INTO games (id, slug, title, description, cover_image, category,
               difficulty, min_weight, max_weight, default_mode, price, is_premium, rating, reviews_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
            (
                game_id, slug,
                data["title"], data.get("description", ""),
                data.get("cover_image", ""),
                data.get("category", "strength"),
                data.get("difficulty", 1),
                data.get("min_weight", 5),
                data.get("max_weight", 50),
                data.get("default_mode", 1),
                data.get("price", 0),
                1 if data.get("is_premium") else 0,
            ),
        )
        conn.commit()
    return {"ok": True, "id": game_id, "slug": slug}


@router.put("/api/games/{slug}")
def update_game(slug: str, data: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Update a game."""
    _get_admin_token(authorization)
    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        # Allow slug changes
        new_slug = data.get("slug", slug)
        if new_slug != slug:
            existing = conn.execute("SELECT id FROM games WHERE slug = ? AND id != ?", (new_slug, game["id"])).fetchone()
            if existing:
                raise HTTPException(409, "Slug already in use")
            conn.execute("UPDATE games SET slug = ? WHERE id = ?", (new_slug, game["id"]))

        fields = []
        params = []
        for key in ("title", "description", "cover_image", "category", "difficulty",
                     "min_weight", "max_weight", "default_mode", "price", "is_premium"):
            if key in data:
                val = data[key]
                if key == "is_premium":
                    val = 1 if val else 0
                fields.append(f"{key} = ?")
                params.append(val)

        if fields:
            params.append(game["id"])
            conn.execute(f"UPDATE games SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()

    return {"ok": True}


@router.delete("/api/games/{slug}")
def delete_game(slug: str, authorization: Optional[str] = Header(None)):
    """Delete a game."""
    _get_admin_token(authorization)
    with get_db() as conn:
        game = conn.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone()
        if not game:
            raise HTTPException(404, "Game not found")

        # Cascade: remove related data
        conn.execute("DELETE FROM reviews WHERE game_id = ?", (game["id"],))
        conn.execute("DELETE FROM scores WHERE game_id = ?", (game["id"],))
        conn.execute("DELETE FROM user_games WHERE game_id = ?", (game["id"],))
        conn.execute("DELETE FROM wishlist WHERE game_id = ?", (game["id"],))
        conn.execute("DELETE FROM games WHERE id = ?", (game["id"],))
        conn.commit()

    return {"ok": True}


# ── User management ─────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    return templates.TemplateResponse(request, "admin/users.html", context={"title": "Manage Users"})


@router.get("/api/users")
def list_admin_users(
    search: str = "",
    tier: str = "",
    authorization: Optional[str] = Header(None)
):
    """List all users for admin."""
    _get_admin_token(authorization)
    with get_db() as conn:
        query = "SELECT * FROM users WHERE 1=1"
        params = []

        if search:
            query += " AND (email LIKE ? OR name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        if tier and tier != "all":
            query += " AND tier = ?"
            params.append(tier)

        query += " ORDER BY created_at DESC"
        users = conn.execute(query, params).fetchall()

    return [dict(u) for u in users]


@router.get("/api/users/{user_id}")
def get_admin_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Get user details."""
    _get_admin_token(authorization)
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        # Get user scores count
        score_count = conn.execute(
            "SELECT COUNT(*) FROM scores WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

        # Get subscription date
        sub_date = conn.execute(
            "SELECT updated_at FROM users WHERE id = ? AND tier != 'free'", (user_id,)
        ).fetchone()

    user_dict = dict(user)
    user_dict["score_count"] = score_count
    user_dict["subscribed_since"] = sub_date["updated_at"] if sub_date else None
    return user_dict


@router.put("/api/users/{user_id}")
def update_user(user_id: str, data: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Update user (tier, name, active status, admin flag)."""
    _get_admin_token(authorization)
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        fields = []
        params = []

        if "tier" in data:
            fields.append("tier = ?")
            params.append(data["tier"])
            fields.append("updated_at = datetime('now')")

        if "name" in data:
            fields.append("name = ?")
            params.append(data["name"])

        if "is_active" in data:
            fields.append("is_active = ?")
            params.append(1 if data["is_active"] else 0)

        if "is_admin" in data:
            fields.append("is_admin = ?")
            params.append(1 if data["is_admin"] else 0)

        if "password" in data and data["password"]:
            fields.append("password_hash = ?")
            params.append(hash_password(data["password"]))

        if fields:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()

    return {"ok": True}


@router.delete("/api/users/{user_id}")
def delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Delete a user and all their data."""
    _get_admin_token(authorization)
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        # Don't allow deleting the last admin
        admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
        if user["is_admin"] and admin_count <= 1:
            raise HTTPException(400, "Cannot delete the last admin user")

        # Cascade delete
        conn.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM scores WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_games WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM wishlist WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    return {"ok": True}


@router.get("/api/me")
def admin_me(authorization: Optional[str] = Header(None)):
    """Get current admin user info."""
    payload = _get_admin_token(authorization)
    with get_db() as conn:
        user = conn.execute("SELECT id, email, name, tier FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    return dict(user)
