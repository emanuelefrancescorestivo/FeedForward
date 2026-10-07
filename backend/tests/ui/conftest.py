"""Drive the web app in a real browser (Playwright, Chromium) against a live server.

The server runs in a thread of the test process, on a free port, with the
temporary SQLite database `tests/conftest.py` set up. Each test gets a fresh,
phone-sized browser context. Without Playwright or its Chromium, the whole
package is skipped (`python -m playwright install chromium` installs it).
"""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

import uvicorn  # noqa: E402

import feedforward.api.main as main_module  # noqa: E402
from feedforward.api.main import app  # noqa: E402
from feedforward.db.models import Base  # noqa: E402
from feedforward.db.session import get_engine  # noqa: E402

PHONE = {"width": 390, "height": 844}
SHOTS = Path(__file__).resolve().parents[3] / "docs" / "screenshots" / "release-1"


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/ui/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.ui)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    # every test browses from 127.0.0.1: the per-address limit (120 a minute) would refuse the later tests
    main_module._LIMIT = 1_000_000
    Base.metadata.create_all(get_engine())
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120                       # the engine loads at start-up
    while not srv.started:
        if time.time() > deadline or not thread.is_alive():
            pytest.fail("the test server did not start")
        time.sleep(0.2)
    yield base
    srv.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser():
    pw = sync_api.sync_playwright().start()
    try:
        chromium = pw.chromium.launch()
    except sync_api.Error as exc:
        pw.stop()
        pytest.skip(f"Chromium for Playwright is not installed ({exc.message.splitlines()[0]})")
    yield chromium
    chromium.close()
    pw.stop()


@pytest.fixture()
def page(browser):
    context = browser.new_context(viewport=PHONE)
    pg = context.new_page()
    yield pg
    context.close()


def sign_in(page, server: str, name: str) -> None:
    """The local test sign-in; waits for the first onboarding screen."""
    page.goto(f"{server}/app")
    page.get_by_placeholder("Any name").fill(name)
    page.keyboard.press("Enter")
    sync_api.expect(page.get_by_role("heading", name="About you")).to_be_visible(timeout=30_000)


def _next(page, label: str = "Next") -> None:
    page.get_by_role("button", name=label, exact=True).click()


def finish_first_run(page, *, goal: str = "Focus", diet: str = "Anything") -> None:
    """Answer the first run (21, 178 cm, 70 kg, male, moderate, the goal, the diet) and wait for Today."""
    page.locator("input[name=age]").fill("21")
    page.locator("input[name=height]").fill("178")
    page.locator("input[name=weight]").fill("70")
    page.get_by_text("Male", exact=True).click()
    page.get_by_text("Moderate", exact=True).click()
    _next(page)
    page.get_by_text(goal, exact=True).first.click()
    if diet != "Anything":
        page.get_by_text(diet, exact=True).click()
    with page.expect_response(lambda r: r.url.endswith("/me/state") and r.request.method == "PUT"):
        _next(page, "Start")                            # the answers are saved a moment after Start
    sync_api.expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)


def api(page, path: str, body=None, method: str | None = None) -> dict:
    """Call the API from the page with its stored token; fails the test on an error status."""
    res = page.evaluate("""async ([path, body, method]) => {
        const token = localStorage.getItem("feedforward.token");
        const r = await fetch(path, { method: method || (body === null ? "GET" : "POST"),
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: body === null ? undefined : JSON.stringify(body) });
        return { status: r.status, json: await r.json().catch(() => null) };
    }""", [path, body, method])
    assert res["status"] < 400, f"{path}: {res['status']} {res['json']}"
    return res["json"]


def snap(page, name: str) -> None:
    """A screenshot for the docs, only when FF_SCREENSHOTS=1."""
    if os.environ.get("FF_SCREENSHOTS") == "1":
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))
