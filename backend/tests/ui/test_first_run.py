"""The first run: two screens to Today; every other answer stays reachable from Profile."""
from playwright.sync_api import expect

from .conftest import api, finish_first_run, sign_in, snap


def test_first_run_has_two_screens(server, page):
    titles = []
    sign_in(page, server, "first-two")
    titles.append(page.locator("h1").first.inner_text())
    page.locator("input[name=age]").fill("21")
    page.locator("input[name=height]").fill("178")
    page.locator("input[name=weight]").fill("70")
    page.get_by_role("button", name="Next", exact=True).click()                          # submit 1
    expect(page.get_by_role("heading", name="What should food help with?")).to_be_visible()
    titles.append(page.locator("h1").first.inner_text())
    page.get_by_text("Focus", exact=True).first.click()
    page.get_by_text("Vegetarian", exact=True).click()
    snap(page, "first-run-goal")
    with page.expect_response(lambda r: r.url.endswith("/me/state") and r.request.method == "PUT"):
        page.get_by_role("button", name="Start", exact=True).click()                     # submit 2
    expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)
    assert "Your energy" not in titles
    state = api(page, "/me/state")["data"]
    assert state["onboarded"] is True and state["setup"]["diet"] == "vegetarian" and state["setup"]["goal"] == "cognitive_function"


def test_tab_bar_hidden_during_first_run(server, page):
    sign_in(page, server, "first-tabbar")
    expect(page.locator(".tabbar")).to_be_hidden()


def test_profile_still_opens_every_screen(server, page):
    sign_in(page, server, "first-profile")
    finish_first_run(page)
    expect(page.locator(".tabbar")).to_be_visible()
    for step, title in [("energy", "Your energy"), ("day", "Your day"), ("food", "Your food"), ("plan", "Your plan")]:
        page.get_by_role("button", name="Profile").last.click()
        page.locator(f"[data-edit-step={step}]").click()
        expect(page.get_by_role("heading", name=title)).to_be_visible(timeout=30_000)
        page.locator("[data-onb-cancel]").first.click()
