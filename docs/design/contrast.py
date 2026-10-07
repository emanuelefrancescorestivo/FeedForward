"""WCAG contrast of FeedForward's colour tokens, both themes.

Text pairs must reach 4.5:1 (AA, normal text); graphics that carry meaning
(day dots, rings, switches, control outlines) 3:1. Run: python docs/design/contrast.py
"""

THEMES = {
    "light": {
        "bg": "#f5f2ea", "surface": "#fffdf8", "soft": ("#6e6042", .09), "text": "#2b2924", "muted": "#655f53",
        # ring revised from #86a977 (2.60:1 on surface, under the 3:1 for meaningful graphics)
        "control": "#8f887a", "accent": "#45693e", "on-accent": "#ffffff", "accent-soft": "#e3ebd9", "ring": "#6d965e",
        "note": "#8a4f1f", "note-soft": "#f5e7d6",
        # new in the engagement phase
        "gold": "#7a5a10", "gold-soft": "#f4e8cc", "rest": "#6a5d9c", "rest-soft": "#ebe7f5", "danger": "#b3412e",
    },
    "dark": {
        # control revised from #7d796c (2.92:1 on a soft fill)
        "bg": "#161914", "surface": "#20241d", "soft": ("#e2e8d4", .08), "text": "#ece8dc", "muted": "#aba696",
        "control": "#8a8578", "accent": "#a9c99a", "on-accent": "#15200f", "accent-soft": "#2a3725", "ring": "#8fb27f",
        "note": "#e8b78c", "note-soft": "#3a2c1f",
        "gold": "#e6c47c", "gold-soft": "#3a321d", "rest": "#b9addf", "rest-soft": "#2e2a3d", "danger": "#f08a74",
    },
}

TEXT = [("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"), ("accent", "surface"),
        ("accent", "accent-soft"), ("on-accent", "accent"), ("note", "note-soft"), ("note", "surface"),
        ("gold", "gold-soft"), ("gold", "surface"), ("rest", "rest-soft"), ("rest", "surface"), ("danger", "surface"),
        ("text", "soft@surface"), ("muted", "soft@surface"), ("accent", "soft@surface")]
GRAPHIC = [("accent", "surface"), ("ring", "surface"), ("control", "surface"), ("rest", "surface"), ("gold", "surface"),
           ("accent", "bg"), ("control", "soft@surface")]


def rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def blend(fg, alpha, under):
    return "#" + "".join(f"{round(255 * (alpha * a + (1 - alpha) * b)):02x}" for a, b in zip(rgb(fg), rgb(under)))


def lum(h):
    c = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb(h)]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def colour(theme, name):
    if "@" in name:                      # a translucent token over another
        top, under = name.split("@")
        fg, alpha = theme[top]
        return blend(fg, alpha, colour(theme, under))
    return theme[name]


def check():
    failures = []
    for tname, t in THEMES.items():
        print(f"\n{tname}")
        for pairs, need, kind in ((TEXT, 4.5, "text"), (GRAPHIC, 3.0, "graphic")):
            for fg, bg in pairs:
                r = ratio(colour(t, fg), colour(t, bg))
                ok = r >= need
                print(f"  {kind:7s} {fg:>10s} on {bg:<14s} {r:5.2f}  {'ok' if ok else 'FAIL'}")
                if not ok:
                    failures.append((tname, fg, bg, round(r, 2)))
    return failures


if __name__ == "__main__":
    bad = check()
    print("\nall pass" if not bad else f"\nfailures: {bad}")
    raise SystemExit(1 if bad else 0)
