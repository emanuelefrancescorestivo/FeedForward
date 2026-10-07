"""Render docs/design/screens.html: one PNG per section and the components board.

Run from the repository root: python docs/design/render.py docs/design/screens.html docs/design/png
(needs Playwright: pip install playwright && python -m playwright install chromium)
"""
import sys, pathlib
from playwright.sync_api import sync_playwright

src = pathlib.Path(sys.argv[1]).resolve(); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=1.5)
    errors = []
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(src.as_uri()); pg.wait_for_timeout(800)
    pg.locator(".board").screenshot(path=str(out / "00-system.png"))
    for i, row in enumerate(pg.locator(".row-phones").all(), 1):
        row.screenshot(path=str(out / f"{i:02d}-section.png"))
    # overflow check: any phone whose content is cut at the bottom by more than the tab bar
    over = pg.evaluate("""() => [...document.querySelectorAll('.phone')].map((ph, i) => {
        const sc = ph.querySelector('.scroll'); return sc ? [i, sc.scrollHeight - sc.clientHeight] : [i, 0]; })""")
    print("errors:", errors)
    print("scroll overflow per phone (px beyond the visible area):", over)
    b.close()
