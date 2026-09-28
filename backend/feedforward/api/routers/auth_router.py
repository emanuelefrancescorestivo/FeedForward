"""Auth router — registration, login, profile, export, deletion."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ...engine.reference import Demographic
from ..auth import authenticate, create_token, create_user, require_user
from ..models import ProfileUpdate, Token, UserCreate, UserOut
from ...db.repository import delete_user, export_user, update_profile

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
    return {"user": exported}


@router.delete("/me")
def delete_me(user=Depends(require_user)):
    if not delete_user(user["sub"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"deleted": True}
