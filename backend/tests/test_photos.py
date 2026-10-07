"""Recipe and food photos: the ledger is complete and open-licensed, and the app serves only the photo files."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from feedforward.api.main import app

DATA = Path(__file__).resolve().parents[1] / "feedforward" / "data"
PHOTOS = Path(__file__).resolve().parents[1] / "feedforward" / "web" / "photos"
LEDGER = json.loads((DATA / "photos.json").read_text(encoding="utf-8"))
client = TestClient(app)


def test_every_photo_has_both_files_and_is_small():
    for p in LEDGER["photos"]:
        for name in (f"{p['id']}.webp", f"{p['id']}-sq.webp"):
            path = PHOTOS / name
            assert path.is_file(), name
            assert path.stat().st_size < 200_000, name


def test_every_recipe_has_a_photo_or_is_listed():
    covered = {ref for p in LEDGER["photos"] for ref in p["for"]} | set(LEDGER["none"])
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    assert [r["id"] for r in recipes if f"recipe:{r['id']}" not in covered] == []


def test_licences_are_open():
    accepted = tuple(a.lower() for a in LEDGER["accepted_licences"])
    for p in LEDGER["photos"]:
        lic = p["licence"].lower()
        assert lic.startswith(accepted), (p["id"], p["licence"])
        assert not re.search(r"\bnc\b|\bnd\b", lic), (p["id"], p["licence"])


def test_photos_endpoint():
    body = client.get("/photos").json()
    assert "lentil-salad" in body["recipes"]
    assert "ciqual-32140" in body["foods"]                      # rolled oats
    assert body["ingredients"]["oats"] == body["foods"]["ciqual-32140"]   # shopping-list items name ingredients
    for photo in [*body["recipes"].values(), *body["foods"].values()]:
        assert photo["src"].startswith("/app/photos/") and photo["thumb"].startswith("/app/photos/")
        assert photo["author"] and photo["licence"] and photo["page"].startswith("https://commons.wikimedia.org/")


def test_every_photo_has_a_credit_with_its_changes():
    """Food thumbnails have no room for a credit line: the app lists every photo's credit in one place."""
    credits = client.get("/photos").json()["credits"]
    ledger = json.loads((DATA / "photos.json").read_text(encoding="utf-8"))["photos"]
    assert len(credits) == len(ledger)
    for c in credits:
        assert c["shows"] and c["author"] and c["licence"] and c["page"].startswith("https://commons.wikimedia.org/")
        assert "cropped" in c["changes"]


def test_photo_route_serves_only_photos():
    res = client.get("/app/photos/lentil-salad.webp")
    assert res.status_code == 200 and res.headers["content-type"] == "image/webp"
    assert "immutable" in res.headers["cache-control"]
    for bad in ("nope.webp", "..%2Findex.html", "photos.json", "lentil-salad.png"):
        assert client.get(f"/app/photos/{bad}").status_code == 404, bad
