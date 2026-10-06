"""Code App Store reviews by theme (EN + FR keyword rules). Prints share of reviews per theme,
split by low (1-2 star) and high (4-5 star) ratings, per app and pooled."""
import json, re, sys, pathlib, collections, random

D = pathlib.Path(sys.argv[1])
THEMES = {
    "price / paywall / subscription": r"paywall|subscri|premium|pay(ing)? for|too expensive|price|\$\d|cost|free (version|trial)|trial|abonnement|payant|cher\b|prix|gratuit|essai",
    "billing / cancel / refund": r"cancel|refund|charged|auto.?renew|résili|rembours|prélev|débit",
    "ads": r"\bads?\b|advert|publicit|\bpubs?\b",
    "logging effort / speed": r"tedious|time.?consuming|takes (too )?long|easy to (log|track|use)|quick to|fast to|simple to|facile|rapide|fastidieu|long à",
    "database accuracy": r"inaccura|wrong (calorie|info|number|data)|database|incorrect|accura|données fausses|base de données|erron|précis",
    "barcode": r"barcode|scann|code.?barre|scanner",
    "AI / photo": r"\bai\b|\bia\b|photo|picture|camera|chatgpt|artificial",
    "bugs / sync / crash": r"\bbug|crash|glitch|sync|freez|won.t load|doesn.t work|ne marche|plante|beug|synchro",
    "recipes / ideas / variety": r"recipe|recette|meal plan|meal idea|variety|variét|idées? de repas|menu",
    "shopping list / groceries / budget": r"grocery|shopping list|liste de courses|courses|budget|save money|économ|supermarch|drive",
    "streak / motivation / habit": r"streak|motivat|habit|accountab|série|motiv|habitude|keeps me on track",
    "community / social / friends": r"friend|communit|social|\bshar(e|ed|ing)\b|partag|\bami(e|s|es)?\b|together|ensemble",
    "health / nutrients / science": r"micronutri|vitamin|mineral|nutrient|science|evidence|nutriment|vitamine|scientif",
    "obsess / guilt / disordered": r"obsess|guilt|anxi|eating disorder|disordered|shame|unhealthy relationship|toxic|culpab|obsession|trouble(s)? alimentaire|tca\b|anorex|boulim",
    "weight loss success": r"lost \d+|lose weight|weight loss|lbs|pounds|kg perdu|perdu \d+|maigr|perte de poids",
    "notifications": r"notification|reminder|rappel|spam",
    "food waste / saving food": r"waste|gaspill|antigaspi|sauv",
}
RX = {k: re.compile(v, re.I) for k, v in THEMES.items()}

rows = []
for f in sorted(D.glob("*_*.json")):
    if f.name == "meta.json": continue
    app, cc = f.stem.rsplit("_", 1)
    for r in json.loads(f.read_text(encoding="utf-8")):
        r.update(app=app.replace("_", " "), cc=cc); rows.append(r)

def share(sub, theme):
    return 100 * sum(1 for r in sub if RX[theme].search(r["title"] + " " + r["text"])) / max(1, len(sub))

print(f"reviews: {len(rows)}   apps: {len(set(r['app'] for r in rows))}")
low = [r for r in rows if r["rating"] <= 2]; high = [r for r in rows if r["rating"] >= 4]
print(f"low (1-2*): {len(low)}  high (4-5*): {len(high)}\n")
print(f"{'theme':38s} {'all':>6s} {'low':>6s} {'high':>6s}  lift(low/high)")
for t in THEMES:
    a, l, h = share(rows, t), share(low, t), share(high, t)
    print(f"{t:38s} {a:6.1f} {l:6.1f} {h:6.1f}  {l / h if h else 0:5.1f}")

print("\nper app: n, mean stars (recent), % low; top low-review themes")
for app in sorted(set(r["app"] for r in rows)):
    sub = [r for r in rows if r["app"] == app]; lo = [r for r in sub if r["rating"] <= 2]
    tops = sorted(((share(lo, t), t) for t in THEMES), reverse=True)[:3] if len(lo) >= 15 else []
    print(f"{app:15s} n={len(sub):4d} mean={sum(r['rating'] for r in sub) / len(sub):.2f} low={100 * len(lo) / len(sub):4.0f}%  "
          + "; ".join(f"{t} {s:.0f}%" for s, t in tops))

print("\nper app: top praise themes in 4-5 star reviews (price and AI left out: mentioned either way)")
for app in sorted(set(r["app"] for r in rows)):
    hi = [r for r in rows if r["app"] == app and r["rating"] >= 4]
    tops = sorted(((share(hi, t), t) for t in THEMES if t not in ("price / paywall / subscription", "AI / photo")), reverse=True)[:3]
    print(f"{app:15s} n={len(hi):4d}  " + "; ".join(f"{t} {s:.0f}%" for s, t in tops))

# a few short examples per key theme for the analyst to read (not for publication)
random.seed(1)
for t in ["obsess / guilt / disordered", "streak / motivation / habit", "community / social / friends", "AI / photo",
          "recipes / ideas / variety", "health / nutrients / science", "shopping list / groceries / budget"]:
    hits = [r for r in rows if RX[t].search(r["title"] + " " + r["text"])]
    print(f"\n== {t} ({len(hits)})")
    for r in random.sample(hits, min(6, len(hits))):
        print(f" [{r['app']} {r['cc']} {r['rating']}*] {(r['title'] + ' | ' + r['text'])[:230]!r}")
