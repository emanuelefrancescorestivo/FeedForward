"""The browser harness itself: a server, a phone-sized page, the sign-in page."""
from playwright.sync_api import expect

from .conftest import api, finish_first_run, sign_in


def test_app_opens_on_sign_in(server, page):
    page.goto(f"{server}/app")
    expect(page.get_by_text("Eat well, at your pace.")).to_be_visible()


def test_helpers_reach_today_and_call_the_api(server, page):
    sign_in(page, server, "harness-ada")
    finish_first_run(page, diet="Vegetarian")
    state = api(page, "/me/state")["data"]
    assert state["onboarded"] is True and state["setup"]["diet"] == "vegetarian"
