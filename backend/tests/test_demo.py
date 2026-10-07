"""The public demo (FEEDFORWARD_ENV=demo): each visitor gets a fresh account of their own; no name sign-in."""
import importlib.util
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
    """deploy/demo/Dockerfile: demo mode, on the port Cloud Run gives, counting each visitor rather than the proxy."""
    dockerfile = (DEMO / "Dockerfile").read_text(encoding="utf-8")
    assert "FEEDFORWARD_ENV=demo" in dockerfile and "${PORT:-8080}" in dockerfile
    assert "--proxy-headers" in dockerfile
    assert "playwright" in dockerfile                        # test tools are left out of the image


def test_the_demo_runs_as_one_instance_in_paris():
    """One instance: the demo's database lives inside it, so a second one would not know the first one's visitors."""
    spec = importlib.util.spec_from_file_location("deploy_demo", DEMO / "deploy.py")
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    args = deploy.deploy_args("feedforward-demo", "/tmp/stage", "s" * 64)
    flag = lambda name: args[args.index(name) + 1]           # noqa: E731
    assert args[:3] == ["run", "deploy", "feedforward-demo"]
    assert flag("--region") == "europe-west9" and flag("--max-instances") == "1" and flag("--min-instances") == "0"
    assert "--allow-unauthenticated" in args and flag("--memory") == "1Gi"
    assert flag("--set-env-vars") == "FEEDFORWARD_SECRET=" + "s" * 64
