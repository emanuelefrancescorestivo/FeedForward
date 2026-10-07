"""Photos on screen: credited, and served by the app itself."""
from urllib.parse import urlparse

from playwright.sync_api import expect

from .conftest import finish_first_run, sign_in, snap


def test_recipe_sheet_credits_the_photo(server, page):
    hosts = set()
    page.on("request", lambda r: hosts.add(urlparse(r.url).netloc))
    sign_in(page, server, "photos-ada")
    finish_first_run(page)
    page.locator(".slot-actions [data-ideas=lunch]").click()
    page.locator(".idea [data-idea-open]").first.click()
    sheet = page.locator("#recipe-sheet")
    expect(sheet.locator("img").first).to_be_visible(timeout=15_000)
    credit = sheet.get_by_text("Photo: a similar dish")
    expect(credit).to_be_visible()
    assert "commons.wikimedia.org" in credit.locator("a").first.get_attribute("href")
    snap(page, "recipe-sheet")
    assert hosts == {urlparse(server).netloc}, hosts


def test_recipe_credit_links_the_licence_and_says_cropped(server, page):
    sign_in(page, server, "photos-licence")
    finish_first_run(page)
    page.locator(".slot-actions [data-ideas=lunch]").click()
    page.locator(".idea [data-idea-open]").first.click()
    credit = page.locator("#recipe-sheet .rs-credit")
    expect(credit).to_contain_text("cropped", timeout=15_000)
    assert any("creativecommons.org" in (a.get_attribute("href") or "") for a in credit.locator("a").all())


def test_every_photo_is_credited_in_sources_and_licences(server, page):
    """Thumbnails of foods have no room for a credit line: each photo is credited in one list."""
    import json
    from pathlib import Path
    ledger = json.loads((Path(__file__).resolve().parents[2] / "feedforward" / "data" / "photos.json").read_text(encoding="utf-8"))
    sign_in(page, server, "photos-credits")
    finish_first_run(page)
    page.get_by_role("button", name="Profile").last.click()
    page.locator("[data-about]").last.click()
    about = page.locator("#about")
    expect(about).not_to_contain_text("placeholder")
    about.get_by_text("Photo credits").click()
    rows = about.locator(".photo-credits li")
    expect(rows).to_have_count(len(ledger["photos"]))
    expect(rows.first.locator("a[href*='commons.wikimedia.org']")).to_have_count(1)
    expect(about.locator(".photo-credits")).to_contain_text("cropped")


def test_the_app_opens_without_photos(server, page):
    """Photos are a nicety: when they cannot be read, the account still opens."""
    page.route("**/photos", lambda r: r.abort())
    sign_in(page, server, "photos-missing")
    finish_first_run(page)
