"""
api/main.py
===========
FeedForward API — FastAPI application.

Wraps the scientific engine in a REST API with three surfaces in mind:
consumer app, professional dashboard, and partner integrations. The engine is
warmed up on startup so the first request is fast.

Run locally:
    uvicorn feedforward.api.main:app --reload
Interactive docs:
    http://localhost:8000/docs
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pathlib import Path

from ..db.diary_rows import migrate_state_diaries
from ..db.models import Base
from ..db.session import assert_production_database, get_engine
from ..engine import load_engine
from .auth import assert_production_secret, demo_mode
from .routers import goals, recommend, auth_router, analysis, dictionary, plan, me, diary, entries, photos
from . import __doc__ as _pkg_doc  # noqa


def _cors_origins() -> list[str]:
    raw = os.getenv("FEEDFORWARD_CORS_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [part.strip() for part in raw.split(",") if part.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables exist before the first auth call. Postgres deployments should
    # also run Alembic; create_all is idempotent for the initial schema.
    assert_production_database()
    assert_production_secret()
    Base.metadata.create_all(get_engine())
    migrate_state_diaries()                       # diaries still in the saved document move to rows, once
    engine = load_engine()
    app.state.engine_summary = engine.graph.summary()
    yield


app = FastAPI(
    title="FeedForward API",
    version="1.0.0",
    description=("Explainable nutritional knowledge graph. Trace the chain "
                 "food → nutrient → health goal, with bioavailability-adjusted "
                 "recommendations and evidence-graded associations."),
    lifespan=lifespan,
)

_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single-process limit. A multi-instance deployment needs a shared store
# (Redis). This process does not pretend to have one.
_HITS: dict[str, list[float]] = defaultdict(list)
_LIMIT = int(os.getenv("FEEDFORWARD_RATE_LIMIT", "120"))
_WINDOW = 60.0


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if path in ("/health", "/docs", "/openapi.json", "/app") or path.startswith("/app/"):
        return await call_next(request)          # the page, its font and photos are files, not API work
    key = request.client.host if request.client else "local"
    now = time.time()
    hits = [t for t in _HITS[key] if now - t < _WINDOW]
    if len(hits) >= _LIMIT:
        return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    hits.append(now)
    _HITS[key] = hits
    return await call_next(request)

app.include_router(auth_router.router)
app.include_router(goals.router)
app.include_router(recommend.router)
app.include_router(analysis.router)
app.include_router(dictionary.router)
app.include_router(plan.router)
app.include_router(me.router)
app.include_router(diary.router)
app.include_router(entries.router)
app.include_router(photos.router)


@app.get("/", tags=["meta"])
def root():
    if demo_mode():                               # the demo's link opens the app, not this description
        return RedirectResponse("/app")
    return {
        "name": "FeedForward API",
        "version": "1.0.0",
        "docs": "/docs",
        "graph": getattr(app.state, "engine_summary", None),
    }


_WEB = Path(__file__).resolve().parent.parent / "web" / "index.html"


@app.get("/app", include_in_schema=False)
def explorer():
    """Local exploration UI (single page, talks to this API)."""
    # Revalidate on every load (the ETag makes it cheap); without this, browsers
    # cache heuristically and keep showing an old interface after an update.
    return FileResponse(_WEB, headers={"Cache-Control": "no-cache"})


_FONTS = (_WEB.parent / "fonts").resolve()


@app.get("/app/fonts/{name}", include_in_schema=False)
def explorer_font(name: str):
    """The UI typeface (Inter, SIL OFL 1.1, see web/fonts/OFL.txt). Served from
    here, not from a font CDN, so opening the app sends nothing to a third party."""
    path = (_FONTS / name).resolve()
    if path.suffix != ".woff2" or path.parent != _FONTS or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="font/woff2",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


_PHOTOS = (_WEB.parent / "photos").resolve()


@app.get("/app/photos/{name}", include_in_schema=False)
def explorer_photo(name: str):
    """Recipe and food photos (data/photos.json lists each one's source, author and licence). Served from
    here, like the typeface, so showing a photo sends nothing to a third party."""
    path = (_PHOTOS / name).resolve()
    if path.suffix != ".webp" or path.parent != _PHOTOS or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
