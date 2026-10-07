"""What a person logged, one entry at a time (DECISIONS.md, decision 24).

The app reads a range of days and adds or removes single entries. Entry ids are
made by the app, so a request sent twice (a retry, a double tap) stores one row.
The engine's day totals still come from /diary/day, with the entries the app sends.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth import require_user
from ...db.diary_rows import IdTaken, add_entries, delete_entry, list_entries

router = APIRouter(prefix="/diary/entries", tags=["diary"])

MAX_DAYS = 92


class EntryStored(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,40}$")
    day: date
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    kind: Literal["recipe", "food", "preset"]
    item_id: str = Field(min_length=1, max_length=80)
    servings: float = Field(1.0, gt=0, le=10)
    grams: float = Field(0.0, ge=0, le=3000)
    name: str = Field("", max_length=200)
    kcal: float = Field(0.0, ge=0, le=10000)
    source: Literal["manual", "idea", "repeat", "preset", "week", "describe"] = "manual"
    estimate: bool = False


class EntriesIn(BaseModel):
    entries: list[EntryStored] = Field(min_length=1, max_length=30)


@router.get("")
def read_entries(start: date = Query(...), end: date = Query(...), user=Depends(require_user)):
    """Entries from start to end, both included (at most 92 days)."""
    if end < start or (end - start).days >= MAX_DAYS:
        raise HTTPException(422, f"A range of 1 to {MAX_DAYS} days")   # the constant was renamed across Starlette versions
    entries = list_entries(user["sub"], start, end)
    if entries is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return {"entries": entries}


@router.post("")
def write_entries(body: EntriesIn, user=Depends(require_user)):
    """Store entries; one already stored with the same id is left as it is."""
    try:
        stored = add_entries(user["sub"], [e.model_dump() for e in body.entries])
    except IdTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry id is already in use")
    if stored is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return {"entries": stored}


@router.delete("/{entry_id}")
def remove_entry(entry_id: str, user=Depends(require_user)):
    if not delete_entry(user["sub"], entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry")
    return {"deleted": True}
