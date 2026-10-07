"""The signed-in person's saved app data: profile answers, preferences, shopping list.

One JSON document per account, read and replaced whole by the app. The diary
lives in rows (/diary/entries); a diary sent here by a page loaded before that
change is moved into rows and left out of the document. The server
keeps it as it is given (an object, at most MAX_BYTES); what it means is
checked where it is used: the answers by the engine when a plan or a day is
computed. Account export (/auth/export) includes it and account deletion
(/auth/me) removes it.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import require_user
from ...db.diary_rows import move_document_diary
from ...db.repository import get_user_state, save_user_state

router = APIRouter(prefix="/me", tags=["me"])

MAX_BYTES = 1_000_000      # about ten years of a food diary


@router.get("/state")
def read_state(user=Depends(require_user)):
    data = get_user_state(user["sub"])
    if data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return {"data": data}


@router.put("/state")
async def write_state(request: Request, user=Depends(require_user)):
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Saved data is too large")   # the constant was renamed across Starlette versions
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body must be JSON")
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'Body must be {"data": {...}}')
    if "diary" in data:                     # a page loaded before the diary moved to rows (decision 24)
        move_document_diary(user["sub"], data.pop("diary"))
    if not save_user_state(user["sub"], data):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return {"saved": True}
