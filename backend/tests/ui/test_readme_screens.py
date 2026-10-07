"""The README's screenshots of the planned week, taken from the running app.

Only with FF_SCREENSHOTS=1 (planning a week takes a while):
    FF_SCREENSHOTS=1 python -m pytest tests/ui/test_readme_screens.py tests/ui -q
The student is the README's example: 24, man, 178 cm, 72 kg, light activity,
goal focus, €50 at Lidl, on Monday 5 October 2026.
"""
import os
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import expect

from .conftest import sign_in

pytestmark = pytest.mark.skipif(os.environ.get("FF_SCREENSHOTS") != "1", reason="takes the README's screenshots (FF_SCREENSHOTS=1)")

DOCS = Path(__file__).resolve().parents[3] / "docs" / "screenshots"
MONDAY = datetime(2026, 10, 5, 8, 0)
DESKTOP, PHONE = {"width": 1280, "height": 1000}, {"width": 390, "height": 844}


def _week(page, server, name):
    """The README's student, through the first run, then a week for €50 at Lidl."""
    page.clock.set_fixed_time(MONDAY)
    sign_in(page, server, name)
    page.locator("input[name=age]").fill("24")
    page.locator("input[name=height]").fill("178")
    page.locator("input[name=weight]").fill("72")
    page.get_by_text("Male", exact=True).click()
    page.get_by_text("Light", exact=True).click()
    page.get_by_role("button", name="Next", exact=True).click()
    page.get_by_text("Focus", exact=True).first.click()
    with page.expect_response(lambda r: r.url.endswith("/me/state") and r.request.method == "PUT"):
        page.get_by_role("button", name="Start", exact=True).click()
    expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)
    page.locator(".plan-week").click()
    page.locator("select[name=chain]").select_option("lidl")
    page.locator("input[name=budget]").fill("50")
    page.get_by_role("button", name="Plan my week").click()
    expect(page.locator("#tab-week [data-eat]").first).to_be_visible(timeout=120_000)
    page.wait_for_timeout(1200)                               # the rings finish drawing
    page.evaluate("window.scrollTo(0, 0)")


def _show_tabs(page):
    """Scroll the recipe sheet past the photo, so its tabs and what they show fill the screen."""
    page.locator("#rs-tabs").evaluate("el => el.scrollIntoView({ block: 'start' })")
    page.wait_for_timeout(500)


def _sheet_shot(page, path):
    _show_tabs(page)
    page.screenshot(path=str(path), clip=page.locator("#recipe-sheet").bounding_box())


def _context(browser, viewport, scheme="light"):
    return browser.new_context(viewport=viewport, device_scale_factor=2, color_scheme=scheme)


def test_week_on_a_laptop_light_and_dark(server, browser):
    for scheme, name in (("light", "week-desktop"), ("dark", "week-dark")):
        ctx = _context(browser, DESKTOP, scheme)
        page = ctx.new_page()
        _week(page, server, f"readme-desk-{scheme}")
        page.screenshot(path=str(DOCS / f"{name}.png"))
        if scheme == "light":                                  # why this meal: the day's dinner
            page.locator("#tab-week [data-recipe][data-slot$='|dinner']").first.click()
            sheet = page.locator("#recipe-sheet")
            sheet.locator("[data-rs-tab=why]").click()
            expect(sheet.locator("#rs-body .loading")).to_have_count(0, timeout=30_000)
            _sheet_shot(page, DOCS / "why-this-meal.png")
        ctx.close()


def test_week_on_a_phone(server, browser):
    ctx = _context(browser, PHONE)
    page = ctx.new_page()
    _week(page, server, "anna")
    page.screenshot(path=str(DOCS / "week-phone.png"))

    food_first = page.locator("#tab-week details.food-first")
    food_first.locator("summary").click()
    food_first.evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 70)")
    page.wait_for_timeout(400)
    page.screenshot(path=str(DOCS / "food-first-phone.png"))

    page.evaluate("window.scrollTo(0, 0)")
    page.locator("#tab-week [data-recipe][data-slot$='|dinner']").first.click()
    sheet = page.locator("#recipe-sheet")
    sheet.locator("[data-rs-tab=swap]").click()
    expect(sheet.get_by_role("button", name="Choose").first).to_be_visible(timeout=30_000)
    _show_tabs(page)
    page.screenshot(path=str(DOCS / "swap-phone.png"))
    sheet.locator("[data-rs-close]").click()
    expect(sheet).to_be_hidden()

    page.get_by_role("button", name="List").last.click()
    page.locator("#tab-list [data-week-to-list]").click()                 # the week's shopping onto the list
    expect(page.locator("#tab-list .shop-row").first).to_be_visible(timeout=30_000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(DOCS / "list-phone.png"))

    page.get_by_role("button", name="Profile").last.click()
    expect(page.locator("#tab-profile [data-signout]")).to_be_attached(timeout=30_000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    page.screenshot(path=str(DOCS / "profile-phone.png"))
    ctx.close()
