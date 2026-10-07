"""The optional questions arrive on Today one at a time, each showing what its answer turns on."""
from playwright.sync_api import expect

from .conftest import api, finish_first_run, sign_in, snap


def _answer(page, choice: str) -> None:
    card = page.locator(".qcard")
    card.get_by_role("button", name=choice, exact=True).click()
    expect(card.get_by_role("button", name="Next question")).to_be_visible(timeout=30_000)


def test_one_question_card_at_a_time(server, page):
    sign_in(page, server, "cards-one")
    finish_first_run(page)
    card = page.locator(".qcard")
    expect(card).to_have_count(1)
    expect(card).to_contain_text("How long can you spend cooking a meal?")
    expect(card).to_contain_text("1 of 10 questions · all optional")
    snap(page, "question-card")
    _answer(page, "20 min")
    card.get_by_role("button", name="Next question").click()
    expect(page.locator(".qcard")).to_contain_text("How many days a week do you train?", timeout=30_000)


def test_an_answer_shows_what_it_turns_on(server, page):
    sign_in(page, server, "cards-evidence")
    finish_first_run(page)
    card = page.locator(".qcard")
    _answer(page, "20 min")
    card.get_by_role("button", name="Next question").click()
    _answer(page, "None")
    card.get_by_role("button", name="Next question").click()
    expect(card).to_contain_text("Do you take long to fall asleep?", timeout=30_000)
    _answer(page, "Sometimes")
    row = card.locator(".strat", has_text="No caffeine at dinner")
    expect(row.locator(".grade")).to_have_text("B")
    switch = row.locator("input[type=checkbox]")
    expect(switch).to_be_checked()
    strategy = switch.get_attribute("data-q-strat")
    with page.expect_response(lambda r: r.url.endswith("/me/state") and r.request.method == "PUT"):
        switch.uncheck()
    assert strategy in api(page, "/me/state")["data"]["declined"]


def test_not_now_hides_the_card_for_the_day(server, page):
    sign_in(page, server, "cards-later")
    finish_first_run(page)
    with page.expect_response(lambda r: r.url.endswith("/me/state") and r.request.method == "PUT"):
        page.locator(".qcard").get_by_role("button", name="Not now").click()
    expect(page.locator(".qcard")).to_have_count(0)
    page.reload()
    expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)
    expect(page.locator(".qcard")).to_have_count(0)
