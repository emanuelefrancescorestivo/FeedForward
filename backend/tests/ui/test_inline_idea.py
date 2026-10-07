"""Day one is not empty: the meal of the moment shows one idea, in the person's diet."""
import re
from datetime import datetime

from playwright.sync_api import expect

from .conftest import finish_first_run, sign_in, snap


def _lunch(page):
    return page.locator(".slot", has=page.locator("[data-log=lunch]"))


def test_day_one_shows_an_idea_for_the_current_meal(server, page):
    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, 30))
    sign_in(page, server, "inline-lunch")
    finish_first_run(page)
    idea = _lunch(page).locator(".inline-idea")
    expect(idea).to_contain_text("An idea for lunch", timeout=30_000)
    expect(page.get_by_text("Your day starts empty")).to_have_count(0)
    # shares of 200 % and more read as "12×", as on the goal card, not "1245%"
    assert not re.search(r"\d{3,}%", idea.locator(".reasons").inner_text())
    snap(page, "today-day-one")
    idea.get_by_role("button", name="I'll have this").click()
    expect(_lunch(page).locator(".entry")).to_have_count(1, timeout=30_000)
    expect(page.locator(".inline-idea")).to_have_count(0)


def test_first_idea_respects_the_diet(server, page):
    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, 30))
    sign_in(page, server, "inline-veg")
    with page.expect_request(lambda r: "/diary/suggest" in r.url, timeout=60_000) as request:
        finish_first_run(page, diet="Vegetarian")
    body = request.value.post_data_json
    assert body["diet"] == "vegetarian" and body["meal"] == "lunch" and body["k"] == 1
