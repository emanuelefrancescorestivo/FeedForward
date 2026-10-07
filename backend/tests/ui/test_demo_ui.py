"""The public demo in the browser: one tap to try, a reminder to use made-up details."""
from playwright.sync_api import expect


def test_try_the_demo_in_one_tap(server, page, monkeypatch):
    monkeypatch.setenv("FEEDFORWARD_ENV", "demo")
    page.goto(f"{server}/app")
    expect(page.get_by_placeholder("Any name")).to_have_count(0, timeout=30_000)
    expect(page.locator("#gate")).to_contain_text("made-up details")
    page.get_by_role("button", name="Try the demo").click()
    expect(page.get_by_role("heading", name="About you")).to_be_visible(timeout=30_000)
    expect(page.locator("#demo-strip")).to_be_visible()
    expect(page.locator("#demo-strip")).to_contain_text("made-up details")
