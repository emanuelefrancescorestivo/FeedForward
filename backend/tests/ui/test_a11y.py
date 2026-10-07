"""Accessibility checks a person would notice: controls that work by keyboard."""
from .conftest import sign_in


def test_onboarding_choices_work_by_keyboard(server, page):
    sign_in(page, server, "a11y-keyboard")
    page.locator("input[name=weight]").focus()
    page.keyboard.press("Tab")
    focused = page.evaluate("() => [document.activeElement.type, document.activeElement.name]")
    assert focused == ["radio", "sex"]
    page.keyboard.press("ArrowRight")
    assert page.locator("input[name=sex][value=male]").is_checked()
