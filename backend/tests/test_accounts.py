"""Accounts without passwords: Google sign-in, the local test sign-in, and the saved app data (/me/state)."""
from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from feedforward.api import auth
from feedforward.api.main import app
from feedforward.db.models import Base
from feedforward.db.session import get_engine, reset_engine

CLIENT_ID = "1234-test.apps.googleusercontent.com"


@pytest.fixture()
def client():
    reset_engine()
    Base.metadata.create_all(get_engine(force=True))
    with TestClient(app) as c:
        yield c
    reset_engine()


@pytest.fixture()
def google(monkeypatch):
    """Google as far as the server can tell: a client ID, and a signing key it trusts."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("FEEDFORWARD_GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(auth, "_google_keys", SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))

    def token(signer=key, **claims):
        now = int(time.time())
        body = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1077", "email": "ada@example.com",
                "email_verified": True, "iat": now, "exp": now + 600, **claims}
        return jwt.encode(body, signer, algorithm="RS256")
    return token


def _bearer(res) -> dict:
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_config_says_how_to_sign_in(client, monkeypatch):
    monkeypatch.delenv("FEEDFORWARD_GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/auth/config").json() == {"google_client_id": None, "dev_login": True, "demo": False}
    monkeypatch.setenv("FEEDFORWARD_GOOGLE_CLIENT_ID", CLIENT_ID)
    assert client.get("/auth/config").json()["google_client_id"] == CLIENT_ID


def test_google_sign_in_creates_the_account_once(client, google):
    first = _bearer(client.post("/auth/google", json={"credential": google()}))
    assert client.get("/auth/me", headers=first).json()["email"] == "ada@example.com"
    client.put("/me/state", headers=first, json={"data": {"onboarded": True}})
    again = _bearer(client.post("/auth/google", json={"credential": google()}))
    assert client.get("/me/state", headers=again).json()["data"] == {"onboarded": True}
    # no password works for an account made by Google
    assert client.post("/auth/login", data={"username": "ada@example.com", "password": "!"}).status_code == 401


@pytest.mark.parametrize("claims", [
    {"aud": "someone-else.apps.googleusercontent.com"},
    {"iss": "https://evil.example.com"},
    {"email_verified": False},
    {"exp": int(time.time()) - 10},
])
def test_google_tokens_that_are_not_for_us_are_refused(client, google, claims):
    assert client.post("/auth/google", json={"credential": google(**claims)}).status_code == 401


def test_a_token_signed_by_another_key_is_refused(client, google):
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.post("/auth/google", json={"credential": google(signer=stranger)}).status_code == 401


def test_google_without_a_client_id_is_not_available(client, monkeypatch):
    monkeypatch.delenv("FEEDFORWARD_GOOGLE_CLIENT_ID", raising=False)
    assert client.post("/auth/google", json={"credential": "x" * 40}).status_code == 503


def test_test_sign_in_is_one_account_per_name(client):
    a = _bearer(client.post("/auth/dev", json={"name": "Anna B."}))
    b = _bearer(client.post("/auth/dev", json={"name": "anna b"}))
    assert client.get("/auth/me", headers=a).json()["email"] == client.get("/auth/me", headers=b).json()["email"] == "anna-b@test.local"
    assert client.post("/auth/dev", json={"name": "!!!"}).status_code == 422


def test_test_sign_in_is_off_in_production_and_when_switched_off(client, monkeypatch):
    monkeypatch.setenv("FEEDFORWARD_DEV_LOGIN", "0")
    assert client.post("/auth/dev", json={"name": "Anna"}).status_code == 404
    assert client.get("/auth/config").json()["dev_login"] is False
    monkeypatch.delenv("FEEDFORWARD_DEV_LOGIN")
    monkeypatch.setenv("FEEDFORWARD_ENV", "production")
    assert auth.dev_login_enabled() is False


def test_saved_data_round_trip_export_and_delete(client):
    h = _bearer(client.post("/auth/dev", json={"name": "Bea"}))
    assert client.get("/me/state", headers=h).json() == {"data": {}}
    doc = {"onboarded": True, "setup": {"age": "30"}, "have": ["rice", "lentils"]}    # the diary is in rows
    assert client.put("/me/state", headers=h, json={"data": doc}).json() == {"saved": True}
    assert client.get("/me/state", headers=h).json()["data"] == doc
    assert client.get("/auth/export", headers=h).json()["app"] == doc
    assert client.delete("/auth/me", headers=h).status_code == 200
    assert client.get("/me/state", headers=h).status_code == 401
    # signing in again with the same name starts from nothing
    fresh = _bearer(client.post("/auth/dev", json={"name": "Bea"}))
    assert client.get("/me/state", headers=fresh).json()["data"] == {}


def test_saved_data_is_checked(client):
    h = _bearer(client.post("/auth/dev", json={"name": "Cleo"}))
    assert client.get("/me/state").status_code == 401
    assert client.put("/me/state", headers=h, json={"data": [1, 2]}).status_code == 422
    assert client.put("/me/state", headers=h, content=b"not json").status_code == 422
    big = {"data": {"x": "a" * 1_000_001}}
    assert client.put("/me/state", headers=h, json=big).status_code == 413


def test_each_person_sees_only_their_own_data(client):
    a = _bearer(client.post("/auth/dev", json={"name": "Dan"}))
    b = _bearer(client.post("/auth/dev", json={"name": "Eve"}))
    client.put("/me/state", headers=a, json={"data": {"mine": "dan"}})
    assert client.get("/me/state", headers=b).json()["data"] == {}
