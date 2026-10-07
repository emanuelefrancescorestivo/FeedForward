"""Photos on screen: credited, and served by the app itself."""
from urllib.parse import urlparse

from playwright.sync_api import expect

from .conftest import finish_first_run, sign_in, snap


def test_recipe_sheet_credits_the_photo(server, page):
    hosts = set()
    page.on("request", lambda r: hosts.add(urlparse(r.url).netloc))
    sign_in(page, server, "photos-ada")
    finish_first_run(page)
    page.locator("[data-ideas=lunch]").click()
    page.locator(".idea [data-idea-open]").first.click()
    sheet = page.locator("#recipe-sheet")
    expect(sheet.locator("img").first).to_be_visible(timeout=15_000)
    credit = sheet.get_by_text("Photo: a similar dish")
    expect(credit).to_be_visible()
    assert "commons.wikimedia.org" in credit.locator("a").get_attribute("href")
    snap(page, "recipe-sheet")
    assert hosts == {urlparse(server).netloc}, hosts
