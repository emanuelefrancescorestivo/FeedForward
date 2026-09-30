"""The README's figures, computed by the engine: `python scripts/figures.py` (from backend/).

Writes three SVGs to docs/figures/ and prints every number they show:

  week_coverage.svg   the README's example week at Lidl and at Naturalia, same budget
  minimum_budget.svg  the cheapest week with enough energy at each chain, same student and goal
  evidence_path.svg   why the top vegetarian food for iron ranks first: every route, with its strength

With FIGURE_PREVIEW=<folder> set, PNG copies are written there too, to look at them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from feedforward.engine import load_engine  # noqa: E402
from feedforward.engine import week_planner as wp  # noqa: E402
from feedforward.engine.needs import Profile  # noqa: E402

OUT = BACKEND.parent / "docs" / "figures"
PREVIEW = Path(os.environ["FIGURE_PREVIEW"]) if os.environ.get("FIGURE_PREVIEW") else None
STUDENT = Profile(24, "male", 72, 178, "light")   # the README's example
GOAL, BUDGET = "cognitive_function", 50

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.spines.top": False,
    "axes.spines.right": False, "axes.spines.left": False, "font.size": 10,
    "axes.axisbelow": True, "svg.hashsalt": "feedforward",
})


def title(ax, text: str, sub: str) -> None:
    ax.set_title(text, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom")


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, bbox_inches="tight", metadata={"Date": None})
    if PREVIEW:
        fig.savefig(PREVIEW / name.replace(".svg", ".png"), bbox_inches="tight", dpi=110)
    plt.close(fig)
    print("wrote", OUT / name)


def week_coverage(rec) -> None:
    plans = {c: wp.plan_week(rec, STUDENT, goal=GOAL, budget=BUDGET, chain=c) for c in ("lidl", "naturalia")}
    names = {n: rec.graph.display_name(n) for p in plans.values() for n in p["coverage"]}
    for c, p in plans.items():
        print(f"{c}: €{p['total_cost']}, {p['energy']['planned_per_day']} kcal/day,",
              {names[n]: v for n, v in sorted(p["coverage"].items(), key=lambda kv: kv[1])})
    # The story is below 100 %: the twelve nutrients closest to falling short at either shop.
    low = sorted(plans["lidl"]["coverage"], key=lambda n: min(p["coverage"][n] for p in plans.values()))[:12]
    order = low[::-1]
    cap = 250
    fig, ax = plt.subplots(figsize=(9, 0.34 * len(order) + 1.6))
    for i, n in enumerate(order):
        a, b = (min(plans[c]["coverage"][n], cap) for c in ("lidl", "naturalia"))
        ax.plot([a, b], [i, i], color=GRID, linewidth=2, zorder=1)
    for c, colour, label in (("lidl", BLUE, "Lidl"), ("naturalia", ORANGE, "Naturalia")):
        p = plans[c]
        ax.scatter([min(p["coverage"][n], cap) for n in order], range(len(order)), s=52, color=colour,
                   edgecolor=SURFACE, linewidth=1.5, zorder=3,
                   label=f"{label}: €{p['total_cost']:.2f} spent of €{BUDGET}")
    ax.axvline(100, color=INK2, linewidth=1, linestyle=(0, (3, 3)), zorder=2)
    ax.set_yticks(range(len(order)), [names[n] for n in order])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(0, cap + 5)
    ax.set_xticks([0, 50, 100, 150, 200, 250], ["0", "50", "100 % of need", "150", "200", "250+"])
    ax.set_xlabel("share of the week's need covered (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.13), ncol=2)
    title(ax, "Same student, same €50, two shops",
          "The twelve nutrients closest to falling short. At Naturalia fewer fish meals fit the budget.")
    save(fig, "week_coverage.svg")


def minimum_budget(rec) -> None:
    rows = []
    for c in wp.chains():
        m = wp._minimum_budget(rec, STUDENT, GOAL, c["id"], None, 7, None)
        rows.append((c["label"], m, c["price_index"]))
        print(f"{c['label']}: cheapest week with enough energy €{m} (price index {c['price_index']})")
    rows = sorted((r for r in rows if r[1] is not None), key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(9, 0.36 * len(rows) + 1.2))
    y = range(len(rows))[::-1]
    ax.barh(list(y), [r[1] for r in rows], height=0.62, color=BLUE)
    for yi, (label, m, idx) in zip(y, rows):
        ax.text(m + 0.6, yi, f"€{m}", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(list(y), [r[0] for r in rows])
    ax.set_xlabel("cheapest week with enough energy (90–115 % of need) under the WHO limits (€)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(r[1] for r in rows) * 1.12)
    title(ax, "The cheapest week that feeds you enough, shop by shop",
          "Same student and goal. Vitamins and minerals are not guaranteed at this floor; "
          "the budget above it buys them")
    save(fig, "minimum_budget.svg")


def evidence_path(rec) -> None:
    r = rec.foods_for_goal("iron_support", constraints=["vegetarian"], k=1)[0]
    e = r.explanation
    routes = e.contributions[:4]
    print(r.food_name, "score", r.match, [(c["name"], c["percent_of_need"], c["strength"]) for c in routes])
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.9, len(routes) - 0.4)
    ax.axis("off")
    mid = (len(routes) - 1) / 2
    for i, c in enumerate(routes):
        yi = len(routes) - 1 - i
        w = 1 + 7 * c["strength"]
        colour = BLUE if i == 0 else MUTED
        ax.plot([2.35, 4.2], [mid, yi], color=colour, linewidth=w, solid_capstyle="butt", zorder=1)
        ax.plot([7.8, 10.05], [yi, mid], color=colour, linewidth=w, solid_capstyle="butt", zorder=1)
        absorb = f", absorbed ×{c['relative_bioavailability']:.2f}" if c["relative_bioavailability"] < 1 else ""
        ax.text(6, yi, f"{c['name']}  ·  evidence {c['evidence']}\n"
                       f"{c['percent_of_need']:.0f}% of daily need{absorb}",
                ha="center", va="center", fontsize=9, linespacing=1.5, zorder=3)
        ax.add_patch(FancyBboxPatch((4.2, yi - 0.34), 3.6, 0.68, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc=SURFACE, ec=colour, lw=1.2, zorder=2))
    for x, text in ((1.2, f"{r.food_name}\n{e.portion_g:.0f} g portion"),
                    (10.8, rec.graph.display_name("iron_support"))):
        ax.text(x, mid, text, ha="center", va="center", fontsize=10.5, fontweight="bold", zorder=3,
                bbox=dict(boxstyle="round,pad=0.5", fc=SURFACE, ec=INK, lw=1.2))
    ax.text(3.4, len(routes) - 0.55, "food → nutrient: one portion, absorption", ha="center", color=INK2, fontsize=9)
    ax.text(8.6, len(routes) - 0.55, "nutrient → goal: evidence grade", ha="center", color=INK2, fontsize=9)
    ax.legend(handles=[Line2D([], [], color=BLUE, lw=4, label="strongest route (Dijkstra on −log strength); width = strength"),
                       Line2D([], [], color=MUTED, lw=4, label="next routes (counted at weight 0.3)")],
              frameon=False, loc="lower center", ncol=2, fontsize=9)
    ax.set_title(f"Why \u201c{r.food_name}\u201d ranks first for iron on a vegetarian diet",
                 loc="left", fontsize=12, fontweight="bold", color=INK)
    save(fig, "evidence_path.svg")


if __name__ == "__main__":
    engine = load_engine()
    week_coverage(engine)
    minimum_budget(engine)
    evidence_path(engine)
