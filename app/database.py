"""Database setup and models."""

import sqlite3
import os
from typing import Optional
from contextlib import contextmanager

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///data/marketplace.db"
).replace("sqlite:///", "data/")


def get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def migrate_db(conn: sqlite3.Connection):
    """Apply column migrations for existing databases."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    if "is_active" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
    conn.commit()


def init_db():
    """Create tables if they don't exist and apply migrations."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                tier TEXT NOT NULL DEFAULT 'free',
                 is_admin INTEGER DEFAULT 0,
                 is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
                );

            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                cover_image TEXT,
                category TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                min_weight INTEGER DEFAULT 5,
                max_weight INTEGER DEFAULT 50,
                default_mode INTEGER DEFAULT 1,
                rating REAL DEFAULT 0,
                reviews_count INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                is_premium INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_games (
                user_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                purchased_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, game_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS scores (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                weight INTEGER,
                score INTEGER NOT NULL,
                reps INTEGER DEFAULT 0,
                meters REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS wishlist (
                user_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                added_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, game_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (game_id) REFERENCES games(id)
            );
        """)
        conn.commit()
        migrate_db(conn)


def seed_admin():
    """Create a default admin user if none exists."""
    import secrets
    from app.auth_utils import hash_password

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE is_admin = 1"
        ).fetchone()
        if existing:
            return

        admin_id = secrets.token_hex(16)
        pw_hash = hash_password("admin")  # Will be changed on first login
        conn.execute(
            """INSERT INTO users (id, email, password_hash, name, tier, is_admin, is_active)
               VALUES (?, ?, ?, ?, 'annual', 1, 1)""",
            (admin_id, "admin@gotone.local", pw_hash, "Administrator"),
        )
        conn.commit()
        return admin_id


def seed_games():
    """Seed the database with sample games."""
    # Check if games already exist
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        if existing > 0:
            return

    games = [
        {
            "id": "dragon-pull",
            "slug": "dragon-pull",
            "title": "Dragon Pull",
            "description": "Feed and strengthen your dragon by pulling the rope! Each pull feeds your dragon and increases its fire power. Chain pulls to trigger special attacks.",
            "cover_image": "/static/dragon-pull.png",
            "category": "strength",
            "difficulty": 1,
            "min_weight": 8,
            "max_weight": 50,
            "default_mode": 1,
            "price": 4.99,
            "is_premium": 1,
        },
        {
            "id": "rhythm-pull",
            "slug": "rhythm-pull",
            "title": "Rhythm Pull",
            "description": "Sync your pulls to the beat! Timing matters more than force — match your rhythm to the music and collect combo points for high scores.",
            "cover_image": "/static/rhythm-pull.png",
            "category": "cardio",
            "difficulty": 2,
            "min_weight": 10,
            "max_weight": 40,
            "default_mode": 2,
            "price": 0,
            "is_premium": 0,
        },
        {
            "id": "chain-reaction",
            "slug": "chain-reaction",
            "title": "Chain Reaction",
            "description": "Use Iron Chain mode to build resistance as you progress. Every rep increases the challenge — maintain your streak or watch your combo crumble.",
            "cover_image": "/static/chain-reaction.png",
            "category": "strength",
            "difficulty": 3,
            "min_weight": 15,
            "max_weight": 60,
            "default_mode": 5,
            "price": 9.99,
            "is_premium": 1,
        },
        {
            "id": "rowing-race",
            "slug": "rowing-race",
            "title": "Rowing Race",
            "description": "Compete against AI opponents in real-time rowing races. Measure your speed and endurance as you sprint through Olympic-style courses.",
            "cover_image": "/static/rowing-race.png",
            "category": "cardio",
            "difficulty": 2,
            "min_weight": 12,
            "max_weight": 45,
            "default_mode": 4,
            "price": 7.99,
            "is_premium": 1,
        },
        {
            "id": "power-hitter",
            "slug": "power-hitter",
            "title": "Power Hitter",
            "description": "Test your maximum power output! Quick max-effort pulls measured by telemetry velocity. How many explosive reps can you chain together?",
            "cover_image": "/static/power-hitter.png",
            "category": "strength",
            "difficulty": 3,
            "min_weight": 20,
            "max_weight": 66,
            "default_mode": 3,
            "price": 5.99,
            "is_premium": 1,
        },
        {
            "id": "endurance-mode",
            "slug": "endurance-mode",
            "title": "Endurance Mode",
            "description": "Long low-intensity sessions that test your mental fortitude. Navigate through terrains while maintaining steady rhythm and steady resistance.",
            "cover_image": "/static/endurance.png",
            "category": "cardio",
            "difficulty": 1,
            "min_weight": 5,
            "max_weight": 30,
            "default_mode": 6,
            "price": 0,
            "is_premium": 0,
        },
        {
            "id": "eccentric-games",
            "slug": "eccentric-games",
            "title": "Eccentric Gauntlet",
            "description": "Master controlled resistance through the eccentric phase. Lower the weight with precision and rack up points for perfect form.",
            "cover_image": "/static/eccentric.png",
            "category": "flexibility",
            "difficulty": 2,
            "min_weight": 5,
            "max_weight": 55,
            "default_mode": 2,
            "price": 6.99,
            "is_premium": 1,
        },
        {
            "id": "full-body-battle",
            "slug": "full-body-battle",
            "title": "Full Body Battle",
            "description": "The ultimate workout combining all exercise modes. Each level challenges you with a different mode — from standard to rowing to iron chain.",
            "cover_image": "/static/full-body.png",
            "category": "full_body",
            "difficulty": 2,
            "min_weight": 8,
            "max_weight": 55,
            "default_mode": 1,
            "price": 12.99,
            "is_premium": 1,
        },
    ]

    with get_db() as conn:
        for game in games:
            conn.execute(
                "INSERT INTO games (id, slug, title, description, cover_image, category, difficulty, min_weight, max_weight, default_mode, price, is_premium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    game["id"],
                    game["slug"],
                    game["title"],
                    game["description"],
                    game["cover_image"],
                    game["category"],
                    game["difficulty"],
                    game["min_weight"],
                    game["max_weight"],
                    game["default_mode"],
                    game["price"],
                    game["is_premium"],
                ),
            )
        conn.commit()
