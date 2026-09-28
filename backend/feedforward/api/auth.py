"""
api/auth.py
===========
Authentication and access tiers.

FeedForward has two tiers:
  * consumer      — free; plain-language evidence labels, core features.
  * professional  — paid; full evidence grades, citations, ICD-10 refs,
                    patient-profile features.

This module implements JWT issuance/verification and a dependency that gates
professional-only endpoints. Passwords are hashed here; the rows live in the
database (``db/repository.py``), not in a process-local dict. A deleted user
stops authenticating immediately because the token is checked against the
users table, not trusted on its own after the signature check.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

_DEV_SECRET = "dev-secret-change-in-production"
_PLACEHOLDERS = {_DEV_SECRET, "replace-with-a-long-random-string"}   # .env.example
SECRET_KEY = os.getenv("FEEDFORWARD_SECRET", _DEV_SECRET)
MIN_SECRET_LENGTH = 32


def assert_production_secret() -> None:
    """Deployments must not sign tokens with the public development secret."""
    if os.getenv("FEEDFORWARD_ENV", "").lower() != "production":
        return
    secret = os.getenv("FEEDFORWARD_SECRET", "")
    if not secret or secret in _PLACEHOLDERS or len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            "FEEDFORWARD_ENV=production requires FEEDFORWARD_SECRET: a random "
            f"string of at least {MIN_SECRET_LENGTH} characters "
            "(e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2 — no external deps beyond stdlib)
# ---------------------------------------------------------------------------
def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


# ---------------------------------------------------------------------------
# User record. Storage is the database; this dataclass is the detached copy
# the JWT layer holds after the session closes.
# ---------------------------------------------------------------------------
@dataclass
class User:
    email: str
    password_hash: str
    tier: str = "consumer"
    id: int | None = None
    demographic: str | None = None
    dietary_restrictions: list[str] | None = None


def _from_stored(stored) -> User:
    return User(
        email=stored.email, password_hash=stored.password_hash, tier=stored.tier,
        id=stored.id, demographic=stored.demographic,
        dietary_restrictions=list(stored.dietary_restrictions),
    )


def create_user(email: str, password: str, tier: str = "consumer") -> User:
    from ..db.repository import create_stored_user
    if tier not in ("consumer", "professional"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown tier")
    try:
        stored = create_stored_user(email, hash_password(password), tier)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    return _from_stored(stored)


def authenticate(email: str, password: str) -> User | None:
    from ..db.repository import get_user as load_user
    stored = load_user(email)
    if stored and verify_password(password, stored.password_hash):
        return _from_stored(stored)
    return None


def load_user(email: str) -> User | None:
    from ..db.repository import get_user as fetch
    stored = fetch(email)
    return _from_stored(stored) if stored else None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user: User) -> str:
    now = int(time.time())
    payload = {"sub": user.email, "tier": user.tier,
               "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def current_user_optional(token: str | None = Depends(oauth2_scheme)) -> dict | None:
    """Returns the token payload if present, valid, and the user still exists."""
    if not token:
        return None
    payload = decode_token(token)
    # A valid signature is not enough after account deletion (GDPR).
    user = load_user(payload.get("sub", ""))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    payload["tier"] = user.tier
    payload["demographic"] = user.demographic
    payload["dietary_restrictions"] = user.dietary_restrictions or []
    return payload


def require_user(payload: dict | None = Depends(current_user_optional)) -> dict:
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return payload


def require_professional(payload: dict | None = Depends(current_user_optional)) -> dict:
    """Gate for professional-only features (full citations, patient tools)."""
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    if payload.get("tier") != "professional":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Professional tier required for this feature")
    return payload
