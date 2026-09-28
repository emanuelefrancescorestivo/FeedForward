"""
Wikipedia summaries for the food dictionary.

A food's description comes from the English Wikipedia REST summary of the
best-matching article (CC BY-SA 4.0, attributed with a link). The match is
automatic, so the entry always shows WHICH article it used; a wrong match is
visible, not hidden. Results are cached in data/wikipedia_cache.json so the
dictionary works offline once built and every description is reviewable.

Images are Wikimedia Commons files with their own licences: the entry links
the file page, where the licence is stated.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import quote

_CACHE = Path(__file__).resolve().parent.parent / "data" / "wikipedia_cache.json"
_LOCK = threading.Lock()
_API = "https://en.wikipedia.org"
_HEADERS = {"User-Agent": "FeedForward/1.0 (nutrition research; food dictionary)"}


def _load() -> dict:
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_cache: dict = _load()


def _save() -> None:
    try:
        _CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def search_terms(name: str) -> list[str]:
    """
    Candidate article titles from a food name, most specific first:
    a synonym in parentheses ("Balsam-pear (bitter gourd)" -> "bitter gourd"),
    then the first descriptive part, skipping generic USDA heads.
    """
    terms = []
    for paren in re.findall(r"\(([^()]+)\)", name):
        if not re.search(r"alaska|includes|usda|native|indian|glandless", paren, re.I):
            terms.append(paren.strip())
    parts = [p.strip() for p in re.sub(r"\([^()]*\)", "", name).split(",") if p.strip()]
    generic = {"fish", "mollusks", "crustaceans", "beverages", "cereals", "game meat", "spices",
               "seeds", "nuts", "snacks", "cereals ready-to-eat"}
    if parts and parts[0].lower() in generic and len(parts) > 1:
        parts = parts[1:]
    if parts:
        terms.append(parts[0])
        head = parts[0].split()[0]
        if head != parts[0] and len(head) > 3:
            terms.append(head)          # "Chrysanthemum leaves" -> "Chrysanthemum"
    return [t for i, t in enumerate(terms) if t and t not in terms[:i]]


def _fetch_summary(term: str, timeout: float) -> dict | None:  # pragma: no cover - network
    import requests
    found = requests.get(f"{_API}/w/api.php", params={
        "action": "opensearch", "search": term, "limit": 1, "namespace": 0, "format": "json"},
        headers=_HEADERS, timeout=timeout).json()
    if len(found) < 2 or not found[1]:
        return None
    title = found[1][0]
    data = requests.get(f"{_API}/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
                        headers=_HEADERS, timeout=timeout).json()
    if data.get("type") != "standard" or not data.get("extract"):
        return None
    thumb = (data.get("thumbnail") or {}).get("source", "")
    original = (data.get("originalimage") or {}).get("source", "")
    # ".../thumb/9/9d/Emu_1.jpg/3840px-Emu_1.jpg?utm..." -> "Emu_1.jpg"
    file_name = re.sub(r"^\d+px-", "", original.split("?")[0].rsplit("/", 1)[-1]) if original else ""
    return {
        "title": data.get("title", title),
        "extract": data["extract"],
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
        "thumbnail": thumb.split("?")[0] if thumb else "",
        "image_page": f"https://commons.wikimedia.org/wiki/File:{file_name}" if file_name else "",
        "search_term": term,
    }


def lookup(name: str, *, timeout: float = 6.0, network: bool = True) -> dict | None:
    """Summary for a food name, from the cache or Wikipedia. None if nothing fits."""
    for term in search_terms(name):
        key = term.lower()
        if key in _cache:
            if _cache[key]:
                return _cache[key]
            continue
        if not network:
            continue
        try:
            result = _fetch_summary(term, timeout)
        except Exception:
            return None      # offline or rate-limited: do not cache a failure
        with _LOCK:
            _cache[key] = result
            _save()
        if result:
            return result
    return None
