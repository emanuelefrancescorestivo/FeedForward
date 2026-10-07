"""Recipe and food photos from Wikimedia Commons: `python scripts/photos.py` (from backend/).

Reads the ledger, data/photos.json (DECISIONS.md, decision 30). For each photo
without its files yet (all of them with --force), it asks Commons for the
file's current licence and author, refuses any licence outside the ledger's
accepted list, downloads Commons' 800-pixel-wide version and writes two WebP
files to feedforward/web/photos/:

  <id>.webp      800 x 600, centre crop to 4:3 (recipe sheets, ideas)
  <id>-sq.webp   256 x 256, centre crop to a square (thumbnails, 128 px at 2x)

The ledger is updated with the licence URL, the author as Commons states it,
the date and a hash of the downloaded image. Nothing else is fetched, and the
app serves the files itself, so opening it sends nothing to Commons.
`--only id1,id2` limits the run to some photos.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from PIL import Image, ImageOps

BACKEND = Path(__file__).resolve().parent.parent
LEDGER = BACKEND / "feedforward" / "data" / "photos.json"
OUT = BACKEND / "feedforward" / "web" / "photos"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "FeedForward/1.0 (open-source nutrition app; https://github.com/emanuelefrancescorestivo/FeedForward)"}
REFUSED = re.compile(r"\bnc\b|\bnd\b|non-?commercial|no ?deriv|fair use", re.I)
SIZES = {"": (800, 600), "-sq": (256, 256)}


def accepted(licence: str, allowed: list[str]) -> bool:
    lic = licence.strip().lower()
    if REFUSED.search(lic):
        return False
    return any(lic == a.lower() or lic.startswith(a.lower() + " ") for a in allowed)


def commons_info(title: str) -> dict:
    params = {"action": "query", "format": "json", "titles": f"File:{title}", "prop": "imageinfo",
              "iiprop": "url|extmetadata", "iiurlwidth": 800,
              "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist"}
    for attempt in range(4):
        r = requests.get(API, params=params, headers=HEADERS, timeout=30)
        if r.status_code != 429:
            break
        time.sleep(15 * (attempt + 1))
    r.raise_for_status()
    page = next(iter(r.json()["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise LookupError(f"not on Commons: {title}")
    ii = page["imageinfo"][0]
    md = ii.get("extmetadata") or {}
    value = lambda k: re.sub(r"<[^>]+>", "", (md.get(k) or {}).get("value", "")).strip()
    return {"thumb": ii.get("thumburl") or ii["url"], "licence": value("LicenseShortName"),
            "licence_url": value("LicenseUrl"), "author": (value("Artist").splitlines() or [""])[0].strip()}


def write_webp(image: Image.Image, stem: str) -> None:
    image = ImageOps.exif_transpose(image).convert("RGB")      # respect rotation, drop EXIF
    for suffix, size in SIZES.items():
        ImageOps.fit(image, size, Image.Resampling.LANCZOS).save(OUT / f"{stem}{suffix}.webp", "WEBP", quality=80, method=6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="fetch photos that already have files")
    ap.add_argument("--only", default="", help="comma-separated photo ids")
    args = ap.parse_args()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    only = {x for x in args.only.split(",") if x}
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for p in ledger["photos"]:
        if only and p["id"] not in only:
            continue
        if not args.force and all((OUT / f"{p['id']}{s}.webp").exists() for s in SIZES):
            continue
        try:
            info = commons_info(p["file"])
            if not accepted(info["licence"], ledger["accepted_licences"]):
                raise ValueError(f"licence now {info['licence']!r}")
            r = requests.get(info["thumb"], headers=HEADERS, timeout=60)
            r.raise_for_status()
            write_webp(Image.open(io.BytesIO(r.content)), p["id"])
            p.update(licence=info["licence"], licence_url=info["licence_url"], author=info["author"] or p["author"],
                     retrieved=date.today().isoformat(), sha256=hashlib.sha256(r.content).hexdigest())
            print(f"ok    {p['id']:28s} {len(r.content) // 1024:5d} KB  {info['licence']}")
        except Exception as exc:                        # one bad file must not stop the set
            failed.append(p["id"])
            print(f"FAIL  {p['id']:28s} {exc}")
        time.sleep(1.0)                                 # be gentle with Commons
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(failed)} failed{': ' + ', '.join(failed) if failed else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
