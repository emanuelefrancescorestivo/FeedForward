"""The diary in the app: each log is saved on its own, follows the account, and a failed save stays visible."""
from playwright.sync_api import expect

from .conftest import PHONE, api, finish_first_run, sign_in


def log_food(page, meal: str, query: str) -> None:
    page.locator(f"[data-log={meal}]").click()
    page.locator("#log-q").fill(query)
    page.locator("[data-pick]").first.click()
    page.locator("#amount-form button[type=submit]").click()


def test_logged_meal_follows_the_account(server, page, browser):
    sign_in(page, server, "diary-follows")
    finish_first_run(page)
    with page.expect_response(lambda r: "/diary/entries" in r.url and r.request.method == "POST"):
        log_food(page, "breakfast", "apple")
    other = browser.new_context(viewport=PHONE).new_page()
    other.goto(f"{server}/app")
    other.get_by_placeholder("Any name").fill("diary-follows")
    other.keyboard.press("Enter")
    expect(other.locator(".slot").first.locator(".entry")).to_have_count(1, timeout=30_000)
    other.context.close()


def test_failed_save_is_visible_and_retried(server, page):
    sign_in(page, server, "diary-retry")
    finish_first_run(page)
    page.route("**/diary/entries", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    log_food(page, "lunch", "apple")
    expect(page.get_by_text("Not saved")).to_be_visible()
    page.unroute("**/diary/entries")
    page.locator("[data-retry-entry]").first.click()
    expect(page.get_by_text("Not saved")).to_have_count(0)
    day = page.evaluate("dayISO")
    assert len(api(page, f"/diary/entries?start={day}&end={day}")["entries"]) == 1
