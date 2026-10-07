"""
The diary as rows: what a person logged, one entry at a time (DECISIONS.md, decision 24).

The app writes entries one by one with ids it made, so a request sent twice
stores one row, and two devices no longer overwrite each other's diary.
Logging also marks the day in ``activity_days`` (what the food-week streak will
count). Diaries saved in the old per-account document are moved here once, at
start-up, by ``migrate_state_diaries``.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from .models import ActivityDayRow, DiaryEntryRow, UserRow, UserStateRow
from .session import session_scope

FIELDS = ("id", "day", "meal", "kind", "item_id", "servings", "grams", "name", "kcal", "source", "estimate")
ID = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
MEALS = {"breakfast", "lunch", "dinner", "snack"}
KINDS = {"recipe", "food", "preset"}


class IdTaken(ValueError):
    """An entry id already stored for another person."""


def _user_id(s, email: str) -> int | None:
    return s.scalar(select(UserRow.id).where(UserRow.email == email.strip().lower()))


def _as_dict(row: DiaryEntryRow) -> dict:
    return {f: getattr(row, f) for f in FIELDS}


def list_entries(email: str, start: date, end: date) -> list[dict] | None:
    """Entries from ``start`` to ``end``, both included, removed ones left out. None for no such user."""
    with session_scope() as s:
        uid = _user_id(s, email)
        if uid is None:
            return None
        rows = s.scalars(select(DiaryEntryRow).where(
            DiaryEntryRow.user_id == uid, DiaryEntryRow.day >= start, DiaryEntryRow.day <= end,
            DiaryEntryRow.deleted_at.is_(None)).order_by(DiaryEntryRow.day, DiaryEntryRow.created_at)).all()
        return [_as_dict(r) for r in rows]


def _mark(s, uid: int, day: date, kind: str) -> None:
    if s.get(ActivityDayRow, (uid, day, kind)) is None:
        s.add(ActivityDayRow(user_id=uid, day=day, kind=kind))


def add_entries(email: str, entries: list[dict]) -> list[dict] | None:
    """Store new entries; an id already stored for this person is left as it is. Raises IdTaken when an id
    belongs to someone else. None for no such user."""
    with session_scope() as s:
        uid = _user_id(s, email)
        if uid is None:
            return None
        out = []
        for e in entries:
            row = s.get(DiaryEntryRow, e["id"])
            if row is not None and row.user_id != uid:
                raise IdTaken(e["id"])
            if row is None:
                row = DiaryEntryRow(user_id=uid, **{f: e[f] for f in FIELDS if f in e})
                s.add(row)
                s.flush()
                _mark(s, uid, row.day, "logged")
            out.append(_as_dict(row))
        return out


def delete_entry(email: str, entry_id: str) -> bool:
    """Mark one of this person's entries removed. False when it is not theirs or does not exist."""
    with session_scope() as s:
        uid = _user_id(s, email)
        row = s.get(DiaryEntryRow, entry_id)
        if uid is None or row is None or row.user_id != uid or row.deleted_at is not None:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        return True


def entries_for_export(email: str) -> list[dict]:
    """Every entry the person keeps (for "Download my data"), oldest first."""
    with session_scope() as s:
        uid = _user_id(s, email)
        if uid is None:
            return []
        rows = s.scalars(select(DiaryEntryRow).where(DiaryEntryRow.user_id == uid, DiaryEntryRow.deleted_at.is_(None))
                         .order_by(DiaryEntryRow.day, DiaryEntryRow.created_at)).all()
        return [{**_as_dict(r), "day": r.day.isoformat()} for r in rows]


def delete_all(s, uid: int) -> None:
    """Remove a person's entries and activity days (account deletion; SQLite does not cascade without a pragma)."""
    s.query(DiaryEntryRow).filter(DiaryEntryRow.user_id == uid).delete()
    s.query(ActivityDayRow).filter(ActivityDayRow.user_id == uid).delete()


def _number(value, default: float, low: float, high: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if low <= x <= high else default


def migrate_state_diaries() -> int:
    """Move every diary still kept in a saved document into rows, then drop it from the document. Entries
    that cannot be read are left out. Returns the number moved; a second run moves nothing."""
    moved = 0
    with session_scope() as s:
        for state in s.scalars(select(UserStateRow)).all():
            try:
                doc = json.loads(state.data or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(doc, dict) or not isinstance(doc.get("diary"), dict):
                continue
            for iso, items in doc["diary"].items():
                try:
                    day = date.fromisoformat(iso)
                except ValueError:
                    continue
                for index, e in enumerate(items if isinstance(items, list) else []):
                    if not isinstance(e, dict) or e.get("meal") not in MEALS or e.get("kind") not in KINDS or not e.get("id"):
                        continue
                    entry_id = str(e.get("uid") or "")
                    taken = s.get(DiaryEntryRow, entry_id) if ID.match(entry_id) else None
                    if not ID.match(entry_id) or (taken is not None and taken.user_id != state.user_id):
                        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{state.user_id}/{iso}/{index}"))
                    if s.get(DiaryEntryRow, entry_id) is not None:
                        continue
                    s.add(DiaryEntryRow(
                        id=entry_id, user_id=state.user_id, day=day, meal=e["meal"], kind=e["kind"],
                        item_id=str(e["id"])[:80], servings=_number(e.get("servings"), 1.0, 0.01, 10),
                        grams=_number(e.get("grams"), 0.0, 0, 3000), name=str(e.get("name") or "")[:200],
                        kcal=_number(e.get("kcal"), 0.0, 0, 10000), source="week" if e.get("src") == "week" else "manual"))
                    s.flush()
                    _mark(s, state.user_id, day, "logged")
                    moved += 1
            del doc["diary"]
            state.data = json.dumps(doc)
            state.updated_at = datetime.now(timezone.utc)
    return moved
