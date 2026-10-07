"""
The built engine saved to a file, so a container starts in about a second
instead of fifteen (DECISIONS.md, decision 31).

The image builds it once:

    python -m feedforward.engine.cache /path/engine.pkl

and sets ``FEEDFORWARD_ENGINE_CACHE`` to that path; ``load_engine()`` then
loads it instead of building the graph and the food x goal scores. The file
records a fingerprint of the engine's code and data: a file made from other
code or data is ignored and the engine is built as usual. Only a file this
image made is read, never one a person supplies (loading a pickle runs code).
"""
from __future__ import annotations

import hashlib
import pickle
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]                  # feedforward/
RUNTIME_CACHES = {"wikipedia_cache.json", "pubmed_cache.json"}  # written while the app runs, not read by the engine
FINGERPRINTED = sorted(p.name for p in (PACKAGE / "data").glob("*.json") if p.name not in RUNTIME_CACHES)


def fingerprint() -> str:
    """The engine's code and its data files, hashed."""
    h = hashlib.sha256()
    files = sorted((PACKAGE / "engine").rglob("*.py")) + [PACKAGE / "data" / name for name in FINGERPRINTED]
    for f in files:
        h.update(f.relative_to(PACKAGE).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def save(engine, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump({"fingerprint": fingerprint(), "engine": engine}, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(path: Path):
    """The saved engine, or None when the file is missing, unreadable, or made from other code or data."""
    try:
        with Path(path).open("rb") as f:
            saved = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None
    if not isinstance(saved, dict) or saved.get("fingerprint") != fingerprint():
        return None
    return saved.get("engine")


if __name__ == "__main__":
    from . import build_engine
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "engine.pkl")
    save(build_engine(use_pubmed=False), target)
    print(f"engine saved to {target} ({target.stat().st_size / 2**20:.1f} MB)")
