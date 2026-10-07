"""The app's colour tokens are the ones docs/design/contrast.py checks, and they pass WCAG AA."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "backend" / "feedforward" / "web" / "index.html").read_text(encoding="utf-8")
NEW = ("gold", "gold-soft", "rest", "rest-soft")


def _contrast():
    spec = importlib.util.spec_from_file_location("contrast", ROOT / "docs" / "design" / "contrast.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _block(opening: str) -> dict[str, str]:
    start = PAGE.index(opening) + len(opening)
    body = PAGE[start:PAGE.index("}", start)]
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b", body))


def _themes() -> dict[str, dict[str, str]]:
    return {"light": _block(":root {"), "dark": _block(':root[data-theme="dark"] {')}


def test_app_tokens_match_the_checked_palette():
    checked = _contrast().THEMES
    for theme, tokens in _themes().items():
        for name, value in checked[theme].items():
            if isinstance(value, str) and name in tokens:
                assert tokens[name].lower() == value.lower(), (theme, name)
        assert all(n in tokens for n in NEW), (theme, [n for n in NEW if n not in tokens])


def test_dark_blocks_agree():
    media = _block(':root:not([data-theme="light"]) {')
    assert media == _themes()["dark"]


def test_palette_passes_contrast():
    assert _contrast().check() == []
