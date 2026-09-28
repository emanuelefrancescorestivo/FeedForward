"""
FeedForward scientific engine.

Public entry point: ``load_engine()`` builds the graph and returns a ready
Recommender, cached so repeated calls (e.g. across API requests) are free.
"""
from __future__ import annotations

from functools import lru_cache

from .build import load_foods, load_goal_edges, build_graph
from .recommender import Recommender
from . import taxonomy

__all__ = ["load_engine", "Recommender", "taxonomy", "build_engine"]


def build_engine(use_pubmed: bool = False, *, whole_foods_only: bool = False,
                 include_whole_foods: bool = True, source: str | None = None) -> Recommender:
    """
    Build the recommendation engine.

    By default the graph merges the curated whole-foods reference corpus, the
    USDA bulk corpus (when ``usda_corpus.json`` is present) and the
    OpenFoodFacts file with micronutrients range-gated. Pass
    ``whole_foods_only=True`` for the hand-checked reference set alone.
    ``source="db"`` reads a seeded database instead of the JSON files. The
    call-site contract (``foods_for_goal``, ``explain``, ``analyze_meal``) is
    unchanged either way.
    """
    foods = load_foods(include_whole_foods=include_whole_foods,
                       whole_foods_only=whole_foods_only, source=source)
    edges = load_goal_edges(source=source)
    graph, meta = build_graph(foods, edges, use_pubmed=use_pubmed)
    return Recommender(graph, foods, meta)


@lru_cache(maxsize=1)
def load_engine() -> Recommender:
    """
    Cached engine for the API (built once per process).

    If the database has been seeded, that is the source — adding a food is a
    row, not a JSON edit. An empty database falls back to the versioned JSON
    seed so the API still starts before the first seed run.
    """
    from ..db.models import Base
    from ..db.repository import corpus_is_seeded
    from ..db.session import get_engine
    get_engine()
    Base.metadata.create_all(get_engine())
    if corpus_is_seeded():
        return build_engine(use_pubmed=False, source="db")
    return build_engine(use_pubmed=False)
