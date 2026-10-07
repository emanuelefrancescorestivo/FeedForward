"""Line icons, not emoji: one drawing style that reads the same in both themes."""
import re

from playwright.sync_api import expect

from .conftest import sign_in

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def _no_emoji(page, where: str) -> None:
    found = EMOJI.findall(page.inner_text("body"))
    assert not found, f"{where}: {''.join(sorted(set(found)))}"


def _next(page, label="Next"):
    page.get_by_role("button", name=label, exact=True).click()


def test_no_emoji_in_the_interface(server, page):
    page.goto(f"{server}/app")
    expect(page.get_by_text("Eat well, at your pace.")).to_be_visible()
    _no_emoji(page, "sign-in")
    sign_in(page, server, "icons-ada")
    _no_emoji(page, "about you")
    page.locator("input[name=age]").fill("21")
    page.locator("input[name=height]").fill("178")
    page.locator("input[name=weight]").fill("70")
    _next(page)
    expect(page.get_by_role("heading", name="What should food help with?")).to_be_visible()
    _no_emoji(page, "goal")
    page.get_by_text("Focus", exact=True).first.click()
    _next(page)
    expect(page.get_by_role("heading", name="Your energy")).to_be_visible(timeout=30_000)
    _no_emoji(page, "energy")
    _next(page)
    expect(page.get_by_role("heading", name="Your day")).to_be_visible()
    _no_emoji(page, "your day")
    _next(page, "Skip")
    expect(page.get_by_role("heading", name="Your food")).to_be_visible()
    _no_emoji(page, "your food")
    _next(page, "Skip")
    expect(page.get_by_role("heading", name="Your plan")).to_be_visible(timeout=30_000)
    _no_emoji(page, "your plan")
    _next(page, "Start")
    expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)
    _no_emoji(page, "today")
    page.locator("[data-log=lunch]").click()
    page.locator("#log-q").fill("lentil")
    expect(page.locator("[data-pick]").first).to_be_visible(timeout=15_000)
    _no_emoji(page, "+ add")
    page.locator("#log-sheet [data-close-sheet]").click()
    page.locator("[data-ideas=dinner]").click()
    expect(page.locator(".idea").first).to_be_visible(timeout=30_000)
    _no_emoji(page, "ideas")
    page.locator("#log-sheet [data-close-sheet]").click()
    page.get_by_role("button", name="Profile").last.click()
    expect(page.get_by_role("heading", name="Profile")).to_be_visible()
    _no_emoji(page, "profile")
