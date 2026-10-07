"""Auth router — registration, login, profile, export, deletion."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ...engine.reference import Demographic
import re
import secrets

from ..auth import (authenticate, create_token, create_user, demo_mode, dev_login_enabled, google_client_id,
                    require_user, user_for_email, verify_google)
from ..models import DevLogin, GoogleLogin, ProfileUpdate, Token, UserCreate, UserOut
from ...db.repository import delete_user, export_user, get_user_state, update_profile

router = APIRouter(prefix="/auth", tags=["auth"])


def _token(user) -> Token:
    return Token(access_token=create_token(user), tier=user.tier)


@router.post("/register", response_model=Token)
def register(payload: UserCreate):
    user = create_user(payload.email, payload.password, payload.tier)
    return _token(user)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Incorrect email or password")
    return _token(user)


@router.get("/config")
def config():
    """How this server lets people sign in: the Google client ID (public; empty when not set up),
    whether the local test sign-in is on (never in production), and whether this is the public demo."""
    return {"google_client_id": google_client_id() or None, "dev_login": dev_login_enabled(), "demo": demo_mode()}


@router.post("/google", response_model=Token)
def google(payload: GoogleLogin):
    """Sign in with the ID token Google's button returns. The account is created on first sign-in."""
    claims = verify_google(payload.credential)
    return _token(user_for_email(claims["email"]))


@router.post("/dev", response_model=Token)
def dev(payload: DevLogin):
    """Test sign-in for a developer's machine: a name, no password, as if it were a new person.
    The same name is the same account. Off in production (FEEDFORWARD_ENV=production)."""
    if not dev_login_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    slug = re.sub(r"[^a-z0-9]+", "-", payload.name.strip().lower()).strip("-")
    if not slug:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type a name")
    return _token(user_for_email(f"{slug[:40]}@test.local"))


@router.post("/demo", response_model=Token)
def demo():
    """The public demo: a fresh account for each visitor, no name or password, shared with no one.
    Only when FEEDFORWARD_ENV=demo."""
    if not demo_mode():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _token(user_for_email(f"demo-{secrets.token_hex(8)}@demo.local"))


@router.get("/me", response_model=UserOut)
def me(user=Depends(require_user)):
    exported = export_user(user["sub"])
    if not exported:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return UserOut(**exported)


@router.patch("/profile", response_model=Token)
def update_me(payload: ProfileUpdate, user=Depends(require_user)):
    """
    Persist demographic and diet, and optionally the account tier.

    Tier is an account flag the citation gate reads from the database. It is
    not a payment. Changing it reissues the token so the client cannot show
    professional citations with a stale consumer token, or the reverse.
    """
    if payload.demographic is not None:
        try:
            Demographic(payload.demographic)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Unknown demographic")
    if payload.tier is not None and payload.tier not in ("consumer", "professional"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown tier")
    updated = update_profile(
        user["sub"],
        demographic=payload.demographic,
        dietary_restrictions=payload.dietary_restrictions,
        tier=payload.tier,
    )
    if updated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    from ..auth import User
    fresh = User(email=updated.email, password_hash=updated.password_hash,
                 tier=updated.tier, demographic=updated.demographic,
                 dietary_restrictions=updated.dietary_restrictions)
    return _token(fresh)


@router.get("/export")
def export_me(user=Depends(require_user)):
    exported = export_user(user["sub"])
    if not exported:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    from ...db.diary_rows import activity_for_export, entries_for_export
    return {"user": exported, "app": get_user_state(user["sub"]) or {}, "diary": entries_for_export(user["sub"]),
            "activity": activity_for_export(user["sub"])}


@router.delete("/me")
def delete_me(user=Depends(require_user)):
    if not delete_user(user["sub"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"deleted": True}
