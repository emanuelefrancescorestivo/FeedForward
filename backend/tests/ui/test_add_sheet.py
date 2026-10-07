"""+ Add, faster: repeat an earlier meal, the CROUS meal as an estimate, several recent items at once."""
import json
from pathlib import Path

from playwright.sync_api import expect

from .conftest import api, finish_first_run, sign_in, snap

INGREDIENTS = {i["id"]: i for i in json.loads(
    (Path(__file__).resolve().parents[2] / "feedforward" / "data" / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]}


def _food(entry_id, day, meal, ingredient, name, grams=150, kcal=80):
    return {"id": entry_id, "day": day, "meal": meal, "kind": "food", "item_id": f"ciqual-{INGREDIENTS[ingredient]['ciqual']}",
            "grams": grams, "name": name, "kcal": kcal}


def _seed(page, entries):
    api(page, "/diary/entries", {"entries": entries})
    page.reload()
    expect(page.locator(".energy-card")).to_be_visible(timeout=30_000)


def _slot(page, meal):
    return page.locator(".slot", has=page.locator(f"[data-log={meal}]"))


def test_repeat_a_meal_in_two_taps(server, page):
    sign_in(page, server, "add-repeat")
    finish_first_run(page)
    yesterday = page.evaluate("shiftDay(dayISO, -1)")
    _seed(page, [_food("rep-apple-0001", yesterday, "breakfast", "apple", "Apple"),
                 _food("rep-banana-001", yesterday, "breakfast", "banana", "Banana")])
    page.locator("[data-log=breakfast]").click()                                   # tap 1
    again = page.locator("[data-again]")
    expect(again).to_contain_text("Same as yesterday's breakfast")
    again.click()                                                                   # tap 2
    expect(_slot(page, "breakfast").locator(".entry")).to_have_count(2)
    expect(_slot(page, "breakfast")).to_contain_text("Apple")
    expect(_slot(page, "breakfast")).to_contain_text("Banana")


def test_crous_lunch_is_an_estimate(server, page):
    sign_in(page, server, "add-crous")
    finish_first_run(page)
    page.locator("[data-log=lunch]").click()
    page.locator("[data-preset=crous-meal]").click()
    expect(page.locator("#amount-form input[name=amt][value='1']")).to_be_checked()
    snap(page, "add-sheet-crous")
    page.locator("#amount-form button[type=submit]").click()
    lunch = _slot(page, "lunch")
    expect(lunch.locator(".entry")).to_have_count(1)
    expect(lunch).to_contain_text("CROUS meal")
    expect(lunch.locator(".est")).to_have_text("≈")


def test_add_several_recent_items_at_once(server, page):
    sign_in(page, server, "add-several")
    finish_first_run(page)
    yesterday = page.evaluate("shiftDay(dayISO, -1)")
    _seed(page, [_food("sev-apple-0001", yesterday, "lunch", "apple", "Apple"),
                 _food("sev-banana-001", yesterday, "lunch", "banana", "Banana"),
                 _food("sev-carrot-001", yesterday, "lunch", "carrot", "Carrot", grams=80, kcal=30)])
    page.locator("[data-log=dinner]").click()
    expect(page.get_by_text("Recent · tap to select several")).to_be_visible()
    page.get_by_role("checkbox", name="Select Apple").check()
    page.get_by_role("checkbox", name="Select Carrot").check()
    snap(page, "add-sheet")
    page.get_by_role("button", name="Add 2 to dinner").click()
    dinner = _slot(page, "dinner")
    expect(dinner.locator(".entry")).to_have_count(2)
    expect(dinner).to_contain_text("Apple")
    expect(dinner).to_contain_text("Carrot")


def test_crous_plate_follows_the_diet(server, page):
    sign_in(page, server, "add-crous-vegan")
    finish_first_run(page, diet="Vegan")
    page.locator("[data-log=lunch]").click()
    expect(page.locator("[data-preset]")).to_have_count(1)
    expect(page.locator("[data-preset=crous-meal-vegan]")).to_contain_text("CROUS meal")
