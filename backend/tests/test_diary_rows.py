"""The diary as rows (/diary/entries): one entry at a time, private to its owner, moved from the old document."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from feedforward.api.main import app
from feedforward.db.diary_rows import migrate_state_diaries
from feedforward.db.models import ActivityDayRow, Base, DiaryEntryRow, UserRow
from feedforward.db.repository import save_user_state
from feedforward.db.session import get_engine, reset_engine, session_scope


@pytest.fixture()
def client():
    reset_engine()
    Base.metadata.create_all(get_engine(force=True))
    with TestClient(app) as c:
        yield c
    reset_engine()


def _bearer(client, name: str) -> dict:
    res = client.post("/auth/dev", json={"name": name})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _entry(id_: str, day: str, **kw) -> dict:
    return {"id": id_, "day": day, "meal": "lunch", "kind": "food", "item_id": "ciqual-20532", "grams": 150,
            "name": "Lentils, cooked", "kcal": 174, **kw}


def _get(client, h, start, end):
    return client.get(f"/diary/entries?start={start}&end={end}", headers=h)


def test_entries_round_trip(client):
    h = _bearer(client, "rows-ada")
    posted = client.post("/diary/entries", headers=h, json={"entries": [
        _entry("entry-one-0001", "2026-10-06"), _entry("entry-two-0002", "2026-10-07", meal="dinner")]})
    assert posted.status_code == 200, posted.text
    got = _get(client, h, "2026-10-06", "2026-10-07").json()["entries"]
    assert [e["id"] for e in got] == ["entry-one-0001", "entry-two-0002"]
    assert got[1]["meal"] == "dinner" and got[0]["grams"] == 150
    assert client.delete("/diary/entries/entry-one-0001", headers=h).json() == {"deleted": True}
    assert [e["id"] for e in _get(client, h, "2026-10-06", "2026-10-07").json()["entries"]] == ["entry-two-0002"]


def test_same_entry_twice_is_one_row(client):
    h = _bearer(client, "rows-bea")
    for _ in range(2):
        assert client.post("/diary/entries", headers=h, json={"entries": [_entry("twice-0000001", "2026-10-07")]}).status_code == 200
    assert len(_get(client, h, "2026-10-07", "2026-10-07").json()["entries"]) == 1


def test_people_cannot_touch_each_others_entries(client):
    a, b = _bearer(client, "rows-cleo"), _bearer(client, "rows-dan")
    client.post("/diary/entries", headers=a, json={"entries": [_entry("cleos-entry-01", "2026-10-07")]})
    assert client.post("/diary/entries", headers=b, json={"entries": [_entry("cleos-entry-01", "2026-10-07")]}).status_code == 409
    assert client.delete("/diary/entries/cleos-entry-01", headers=b).status_code == 404
    assert _get(client, b, "2026-10-07", "2026-10-07").json()["entries"] == []
    assert len(_get(client, a, "2026-10-07", "2026-10-07").json()["entries"]) == 1


def test_range_is_inclusive_and_bounded(client):
    h = _bearer(client, "rows-eve")
    client.post("/diary/entries", headers=h, json={"entries": [
        _entry("range-first-01", "2026-10-01"), _entry("range-last-001", "2026-10-03"), _entry("range-out-0001", "2026-10-04")]})
    assert [e["id"] for e in _get(client, h, "2026-10-01", "2026-10-03").json()["entries"]] == ["range-first-01", "range-last-001"]
    assert _get(client, h, "2026-07-01", "2026-10-01").status_code == 422          # 93 days
    assert _get(client, h, "2026-10-03", "2026-10-01").status_code == 422


def test_old_diaries_move_once(client):
    h = _bearer(client, "rows-finn")
    doc = {"onboarded": True, "diary": {"2026-10-05": [
        {"uid": "old-entry-0001", "meal": "breakfast", "kind": "recipe", "id": "porridge-banana-walnut", "servings": 1,
         "name": "Porridge with banana and walnuts", "kcal": 699},
        {"meal": "lunch", "kind": "food", "id": "ciqual-20532", "grams": 150, "name": "Lentils", "kcal": 174, "src": "week"}]}}
    save_user_state("rows-finn@test.local", doc)              # saved before the update, as it sits in the database
    assert migrate_state_diaries() == 2
    got = _get(client, h, "2026-10-05", "2026-10-05").json()["entries"]
    assert [(e["id"], e["kind"], e["item_id"], e["source"]) for e in got][0] == (
        "old-entry-0001", "recipe", "porridge-banana-walnut", "manual")
    assert got[1]["source"] == "week" and got[1]["grams"] == 150
    assert "diary" not in client.get("/me/state", headers=h).json()["data"]
    assert migrate_state_diaries() == 0


def test_logging_marks_the_day(client):
    h = _bearer(client, "rows-gus")
    client.post("/diary/entries", headers=h, json={"entries": [_entry("marks-day-0001", "2026-10-07")]})
    with session_scope() as s:
        uid = s.scalar(select(UserRow.id).where(UserRow.email == "rows-gus@test.local"))
        rows = s.execute(select(ActivityDayRow.day, ActivityDayRow.kind).where(ActivityDayRow.user_id == uid)).all()
    assert [(d, k) for d, k in rows] == [(date(2026, 10, 7), "logged")]


def test_export_and_delete_cover_entries(client):
    h = _bearer(client, "rows-hana")
    client.post("/diary/entries", headers=h, json={"entries": [_entry("export-me-0001", "2026-10-07")]})
    assert [e["id"] for e in client.get("/auth/export", headers=h).json()["diary"]] == ["export-me-0001"]
    with session_scope() as s:
        uid = s.scalar(select(UserRow.id).where(UserRow.email == "rows-hana@test.local"))
    assert client.delete("/auth/me", headers=h).status_code == 200
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(DiaryEntryRow).where(DiaryEntryRow.user_id == uid)) == 0
        assert s.scalar(select(func.count()).select_from(ActivityDayRow).where(ActivityDayRow.user_id == uid)) == 0


# ---- final review fixes

def test_a_removed_entry_is_gone_from_the_database(client):
    """Removing is removing: nothing of the entry stays stored (HANDOFF 4.5, personal data deletable)."""
    h = _bearer(client, "rows-ivo")
    client.post("/diary/entries", headers=h, json={"entries": [_entry("gone-for-good-1", "2026-10-07")]})
    assert client.delete("/diary/entries/gone-for-good-1", headers=h).status_code == 200
    with session_scope() as s:
        assert s.get(DiaryEntryRow, "gone-for-good-1") is None


def test_export_includes_the_days_shown_up(client):
    h = _bearer(client, "rows-jo")
    client.post("/diary/entries", headers=h, json={"entries": [_entry("export-days-001", "2026-10-07")]})
    assert client.get("/auth/export", headers=h).json()["activity"] == [{"day": "2026-10-07", "kind": "logged"}]


def test_a_diary_sent_in_the_saved_document_moves_to_rows(client):
    """A page loaded before the update still saves the diary inside the document: it moves at once."""
    h = _bearer(client, "rows-kai")
    doc = {"onboarded": True, "diary": {"2026-10-06": [
        {"uid": "old-tab-entry-01", "meal": "dinner", "kind": "food", "id": "ciqual-20532", "grams": 150, "name": "Lentils", "kcal": 174}]}}
    assert client.put("/me/state", headers=h, json={"data": doc}).status_code == 200
    assert "diary" not in client.get("/me/state", headers=h).json()["data"]
    assert [e["id"] for e in _get(client, h, "2026-10-06", "2026-10-06").json()["entries"]] == ["old-tab-entry-01"]


def test_same_entry_arriving_twice_at_once_is_one_row(client, monkeypatch):
    """Two requests with one id racing past the existence check: the second answers like the first, not 500."""
    h = _bearer(client, "rows-lea")
    assert client.post("/diary/entries", headers=h, json={"entries": [_entry("racing-entry-01", "2026-10-07")]}).status_code == 200
    from sqlalchemy.orm import Session
    original = Session.get
    calls = {"n": 0}

    def blind_first(self, entity, ident, *a, **kw):           # the first lookup misses, as in a race
        if entity is DiaryEntryRow and ident == "racing-entry-01" and calls["n"] == 0:
            calls["n"] += 1
            return None
        return original(self, entity, ident, *a, **kw)
    monkeypatch.setattr(Session, "get", blind_first)
    res = client.post("/diary/entries", headers=h, json={"entries": [_entry("racing-entry-01", "2026-10-07")]})
    assert res.status_code == 200, res.text
    assert [e["id"] for e in res.json()["entries"]] == ["racing-entry-01"]
    monkeypatch.setattr(Session, "get", original)
    assert len(_get(client, h, "2026-10-07", "2026-10-07").json()["entries"]) == 1