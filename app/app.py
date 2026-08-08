"""Web server — FastAPI app + HTML routing template."""

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db, get_db, seed_games
from app.api_routes import router as api_router
from app.auth_utils import decode_token

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Go-Tone Marketplace", version="0.1.0")

# Serve static files
static_dir = Path(__file__).parent / "templates" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Root router (pages, HTML)
pages = APIRouter()


def auth_user(request: Request) -> Optional[dict]:
    """Try to extract user from cookie or Authorization header.

    In production we'd read a session cookie. Here we accept
    ``?token=...`` query param for quick testing and also check
    ``Authorization: Bearer <token>`` headers.
    """
    token = request.query_params.get("token")
    auth = request.headers.get("authorization", "")

    if not token and auth.startswith("bearer "):
        token = auth[7:]

    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None
    return payload


# ╔═══════════════════════════════════════════╗
# ║  TEMPORARY DEMO MODE                       ║
# ║  We serve HTML pages from the server       ║
# ║  so the app works without a separate SPA.  ║
# ║  (Frontend will eventually be a React     ║
# ║   SPA; backend is FastAPI only.)           ║
# ╚═══════════════════════════════════════════╝


@pages.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page — store."""
    return templates.TemplateResponse(request, "index.html", context={"title": "Go-Tone Games"})


@pages.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(request, "login.html", context={"title": "Login"})


@pages.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse(request, "register.html", context={"title": "Register"})


@pages.get("/games", response_class=HTMLResponse)
async def games(request: Request):
    """Browse store."""
    return templates.TemplateResponse(request, "games.html", context={"title": "Browse Games"})


@pages.get("/game/{slug}", response_class=HTMLResponse)
async def game_detail(request: Request, slug: str):
    """Game detail page."""
    return templates.TemplateResponse(request, "game_detail.html", context={"title": f"Game — {slug}", "slug": slug})


@pages.get("/library", response_class=HTMLResponse)
async def library(request: Request):
    """User's game library."""
    return templates.TemplateResponse(request, "library.html", context={"title": "My Library"})


@pages.get("/subscribe", response_class=HTMLResponse)
async def subscribe(request: Request):
    return templates.TemplateResponse(request, "subscribe.html", context={"title": "Get Go-Tone — $9.99/mo"})


# ── Startup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    seed_games()


# ── Mount routers ─────────────────────────────────────────────────────────

app.include_router(pages)
app.include_router(api_router)


# ── 404 Handler ──

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Serve a styled 404 page for all missing routes."""
    return HTMLResponse(
        status_code=404,
        content=Path(__file__).parent.joinpath("templates", "404.html").read_text(),
    )


# ── CLI launch ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
