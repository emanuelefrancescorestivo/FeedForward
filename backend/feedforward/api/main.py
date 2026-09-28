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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from ..db.models import Base
from ..db.session import assert_production_database, get_engine
from ..engine import load_engine
from .auth import assert_production_secret
from .routers import goals, recommend, auth_router, analysis, dictionary, plan
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
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
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


@app.get("/", tags=["meta"])
def root():
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
    return FileResponse(_WEB)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
