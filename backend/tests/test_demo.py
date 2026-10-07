"""The public demo (FEEDFORWARD_ENV=demo): each visitor gets a fresh account of their own; no name sign-in."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from feedforward.api import auth
from feedforward.api.main import app
from feedforward.db.models import Base
from feedforward.db.session import get_engine

client = TestClient(app)        # no lifespan: these routes do not need the engine


@pytest.fixture()
def demo(monkeypatch):
    Base.metadata.create_all(get_engine())
    monkeypatch.setenv("FEEDFORWARD_ENV", "demo")


def test_demo_gives_each_visitor_an_account_of_their_own(demo):
    assert client.get("/auth/config").json()["demo"] is True
    emails = set()
    for _ in range(2):
        token = client.post("/auth/demo").json()["access_token"]
        emails.add(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"])
    assert len(emails) == 2


def test_the_name_sign_in_is_off_in_the_demo(demo):
    """With a name alone, anyone typing "anna" would open Anna's account."""
    assert client.get("/auth/config").json()["dev_login"] is False
    assert client.post("/auth/dev", json={"name": "anna"}).status_code == 404


def test_the_demo_needs_a_real_secret(demo, monkeypatch):
    monkeypatch.delenv("FEEDFORWARD_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        auth.assert_production_secret()


def test_no_demo_accounts_outside_the_demo(monkeypatch):
    monkeypatch.setenv("FEEDFORWARD_ENV", "test")
    assert client.get("/auth/config").json()["demo"] is False
    assert client.post("/auth/demo").status_code == 404


def test_the_demo_link_opens_the_app(demo):
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (302, 307) and res.headers["location"] == "/app"


DEMO = Path(__file__).resolve().parents[2] / "deploy" / "demo"


def test_the_container_runs_the_demo():
    """deploy/demo/Dockerfile: demo mode, on the port the host gives, counting each visitor rather than the proxy."""
    dockerfile = (DEMO / "Dockerfile").read_text(encoding="utf-8")
    assert "FEEDFORWARD_ENV=demo" in dockerfile and "${PORT:-8080}" in dockerfile
    assert "--proxy-headers" in dockerfile
    assert "playwright" in dockerfile                        # test tools are left out of the image
    # the engine is built with the image and loaded at start-up (a free instance has a tenth of a CPU)
    assert "feedforward.engine.cache /home/app/engine.pkl" in dockerfile and "FEEDFORWARD_ENGINE_CACHE=/home/app/engine.pkl" in dockerfile


def test_render_runs_the_demo_free_in_frankfurt():
    """render.yaml: Render's free plan (no card), in the EU, from the demo's Dockerfile, with a secret of its own."""
    blueprint = (DEMO.parents[1] / "render.yaml").read_text(encoding="utf-8")
    for line in ("runtime: docker", "plan: free", "region: frankfurt", "dockerfilePath: ./deploy/demo/Dockerfile",
                 "healthCheckPath: /health", "key: FEEDFORWARD_SECRET", "generateValue: true"):
        assert line in blueprint, line
