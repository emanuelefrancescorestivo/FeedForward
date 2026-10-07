"""Fetch recent App Store reviews (public RSS JSON feed) for competitor apps, FR + US stores."""
import json, sys, time, pathlib, urllib.request, urllib.parse

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
APPS = {  # search term -> expected name fragment
    "myfitnesspal": "MyFitnessPal", "yazio": "YAZIO", "lifesum": "Lifesum",
    "cronometer": "Cronometer", "noom": "Noom", "mealime": "Mealime",
    "eat this much": "Eat This Much", "jow": "Jow", "yuka": "Yuka",
    "foodvisor": "Foodvisor", "too good to go": "Too Good To Go",
    "macrofactor": "MacroFactor", "cal ai": "Cal AI",
}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

meta = {}
for term, frag in APPS.items():
    s = get("https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": term, "entity": "software", "country": "us", "limit": 10}))
    hit = next((x for x in s["results"] if frag.lower() in x["trackName"].lower()), None)
    if not hit:
        print("no match", term); continue
    meta[frag] = {"id": hit["trackId"], "name": hit["trackName"], "rating": hit.get("averageUserRating"),
                  "count": hit.get("userRatingCount"), "price": hit.get("formattedPrice")}
    for cc in ("fr", "us"):
        reviews = []
        for page in range(1, 11):
            try:
                d = get(f"https://itunes.apple.com/{cc}/rss/customerreviews/page={page}/id={hit['trackId']}/sortby=mostrecent/json")
            except Exception as e:
                break
            entries = d.get("feed", {}).get("entry", [])
            if isinstance(entries, dict): entries = [entries]
            entries = [e for e in entries if "im:rating" in e]
            if not entries: break
            for e in entries:
                reviews.append({"rating": int(e["im:rating"]["label"]), "title": e["title"]["label"],
                                "text": e["content"]["label"], "date": e.get("updated", {}).get("label", "")})
            time.sleep(0.3)
        (OUT / f"{frag.replace(' ', '_')}_{cc}.json").write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")
        print(frag, cc, len(reviews))
(OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print(json.dumps(meta, indent=1))
