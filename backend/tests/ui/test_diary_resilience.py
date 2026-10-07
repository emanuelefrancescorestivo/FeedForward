"""The diary when the connection fails or a finger taps twice: what is on screen matches what is stored."""
import time
from datetime import datetime

from playwright.sync_api import expect

from .conftest import api, finish_first_run, sign_in
from .test_add_sheet import _food, _seed, _slot
from .test_diary_ui import log_food

POST = lambda r: r.url.endswith("/diary/entries") and r.request.method == "POST"   # noqa: E731


def _stored(page):
    day = page.evaluate("dayISO")
    return api(page, f"/diary/entries?start={day}&end={day}")["entries"]


def _eventually(check, seconds=8.0):
    deadline = time.time() + seconds
    while not check():
        assert time.time() < deadline, "the condition never held"
        time.sleep(0.25)


def test_removing_an_entry_still_saving_leaves_no_ghost(server, page):
    sign_in(page, server, "res-ghost")
    finish_first_run(page)
    held = []
    page.route("**/diary/entries", lambda r: held.append(r) if r.request.method == "POST" else r.continue_())
    log_food(page, "lunch", "apple")
    lunch = _slot(page, "lunch")
    expect(lunch.locator(".entry")).to_have_count(1)
    lunch.locator("[data-unlog]").click()                          # removed while its save is on its way
    expect(lunch.locator(".entry")).to_have_count(0)
    page.wait_for_timeout(300)
    held[0].continue_()                                            # the save arrives after the removal
    page.unroute("**/diary/entries")
    _eventually(lambda: _stored(page) == [])
    page.wait_for_timeout(500)
    assert _stored(page) == []


def test_removing_a_not_saved_entry_removes_it_where_it_was_stored(server, page):
    """The save reached the server but its answer was lost: "Not saved", yet stored. Removing it removes it there."""
    sign_in(page, server, "res-lost")
    finish_first_run(page)

    def stored_but_lost(route):
        if route.request.method != "POST":
            return route.continue_()
        route.fetch()                                              # the server stores it...
        route.abort()                                              # ...and the answer never comes back
    page.route("**/diary/entries", stored_but_lost)
    log_food(page, "lunch", "apple")
    expect(page.get_by_text("Not saved")).to_be_visible()
    page.unroute("**/diary/entries")
    assert len(_stored(page)) == 1
    _slot(page, "lunch").locator("[data-unlog]").click()
    _eventually(lambda: _stored(page) == [])


def test_offline_today_keeps_the_day_and_shows_not_saved(server, page):
    sign_in(page, server, "res-offline")
    finish_first_run(page)
    page.route("**/diary/entries", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    page.route("**/diary/day", lambda r: r.abort())
    log_food(page, "dinner", "apple")
    expect(page.get_by_text("Not saved")).to_be_visible(timeout=15_000)
    expect(page.locator(".energy-card")).to_be_visible()
    expect(page.get_by_text("Could not open this day")).to_have_count(0)
    expect(page.locator(".stale-note")).to_be_visible()
    page.unroute("**/diary/day")
    page.unroute("**/diary/entries")
    page.locator("[data-retry-entry]").first.click()
    expect(page.get_by_text("Not saved")).to_have_count(0)
    expect(page.locator(".stale-note")).to_have_count(0)


def test_a_double_tap_logs_once(server, page):
    sign_in(page, server, "res-double")
    finish_first_run(page)
    page.locator("[data-log=lunch]").click()
    page.locator("#log-q").fill("apple")
    page.locator("[data-pick]").first.click()
    page.locator("#amount-form button[type=submit]").dblclick()
    expect(_slot(page, "lunch").locator(".entry")).to_have_count(1)
    page.wait_for_timeout(800)
    expect(_slot(page, "lunch").locator(".entry")).to_have_count(1)
    assert len(_stored(page)) == 1


def test_ticked_items_survive_a_search(server, page):
    sign_in(page, server, "res-ticks")
    finish_first_run(page)
    yesterday = page.evaluate("shiftDay(dayISO, -1)")
    _seed(page, [_food("tick-apple-001", yesterday, "snack", "apple", "Apple"),
                 _food("tick-banana-01", yesterday, "snack", "banana", "Banana")])
    page.locator("[data-log=lunch]").click()
    checks = page.locator(".pick-check")
    checks.nth(0).check()
    checks.nth(1).check()
    page.locator("#log-q").fill("rice")
    expect(page.locator(".pick-check")).to_have_count(0, timeout=15_000)        # the results replaced Recent
    expect(page.locator("[data-pick]").first).to_be_visible()
    bar = page.locator("[data-add-picked]")
    expect(bar).to_have_text("Add 2 to lunch")
    bar.click()
    expect(_slot(page, "lunch").locator(".entry")).to_have_count(2)


def test_a_week_tick_that_was_not_saved_is_undone(server, page):
    sign_in(page, server, "res-week")
    finish_first_run(page)
    page.evaluate("Object.assign(app.setup, { chain: 'lidl', budget: 70 }); app.weekOn = true; showTab('week')")
    tick = page.locator("[data-eat]").first
    expect(tick).to_be_visible(timeout=90_000)
    expect(tick).to_have_attribute("aria-pressed", "false")
    page.route("**/diary/entries", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    tick.click()
    expect(tick).to_have_attribute("aria-pressed", "false", timeout=10_000)
    expect(page.locator("#tab-week .eaten-line")).to_contain_text("Not saved")
    page.unroute("**/diary/entries")
    with page.expect_response(POST):
        tick.click()
    expect(tick).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#tab-week .eaten-line")).to_contain_text("1 of 3 meals logged")


def _new_person(page, name):
    page.get_by_placeholder("Any name").fill(name)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="About you")).to_be_visible(timeout=30_000)


def test_the_next_person_gets_an_idea_of_their_own(server, page):
    """Signing out forgets the idea: a vegetarian signing in after an omnivore is not offered mackerel."""
    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, 30))
    sign_in(page, server, "res-idea-omni")
    finish_first_run(page)
    expect(page.locator(".inline-idea")).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="Profile").last.click()
    page.locator("[data-signout]").first.click()
    _new_person(page, "res-idea-veg")
    with page.expect_request(lambda r: "/diary/suggest" in r.url and r.post_data_json["diet"] == "vegetarian", timeout=30_000):
        finish_first_run(page, diet="Vegetarian")
    expect(page.locator("body.first-run")).to_have_count(0)


def test_a_new_diet_brings_a_new_idea(server, page):
    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, 30))
    sign_in(page, server, "res-idea-diet")
    finish_first_run(page)
    expect(page.locator(".inline-idea")).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="Profile").last.click()
    page.locator("[data-edit-step=food]").click()
    page.get_by_text("Vegan", exact=True).click()
    page.get_by_role("button", name="Save").click()
    with page.expect_request(lambda r: "/diary/suggest" in r.url and r.post_data_json["diet"] == "vegan", timeout=30_000):
        page.get_by_role("button", name="Today").last.click()
