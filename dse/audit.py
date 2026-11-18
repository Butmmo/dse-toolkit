"""Is this lead list really the business type you asked for? A sample sheet you label, then a score.

  python dse.py audit my-lists/2026-11-18-stump-grinding-leeds-plus3.csv              writes <name>-audit.csv: about 20 leads, strongest and weakest mixed, with an empty is_right column
  (open it and write y or n in is_right for each: is this a real <business type> with its own website?)
  python dse.py audit my-lists/<name>-audit.csv --score                                prints the precision overall and by how clearly the site says the trade, what to change,
                                                                                         and the web addresses that were wrong more than once

Foursquare's categories are coarser than the app's 512 niches, so a niche search returns a wider category filtered by the words of the niche. This is how you find out,
with real leads and in ten minutes, whether that is good enough for a niche you are about to send to, and what to tighten (--strict, your own --words, or a directory
to add to NOT_A_SITE in dse/places.py). The sample is stratified: every level of `niche_match` is represented, so a small weak group is not hidden by a big strong one.
"""
from __future__ import annotations

import random
import re
import sys
import urllib.parse
from pathlib import Path

from .common import out_path, read_csv, write_csv

LEVELS = ("title", "body", "weak", "thin", "blocked", "unchecked", "unknown")
STRONG = ("title", "body")
YES = {"y", "yes", "1", "true", "right", "good", "ok"}
NO = {"n", "no", "0", "false", "wrong", "bad"}


def host(url: str) -> str:
    h = urllib.parse.urlparse(url if "//" in (url or "") else "https://" + (url or "")).netloc.lower()
    return re.sub(r"^www\.", "", h)


def sample_rows(rows: list[dict], n: int, seed: int = 1) -> list[dict]:
    """About n rows, every level of niche_match present (at least 2 of each when it has them), the rest in proportion. Same seed, same sample."""
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("niche_match") or "unknown", []).append(r)
    take: dict[str, int] = {k: min(len(v), 2) for k, v in groups.items()}
    spare = max(0, n - sum(take.values()))
    total = sum(len(v) - take[k] for k, v in groups.items()) or 1
    for k, v in groups.items():
        take[k] += min(len(v) - take[k], round(spare * (len(v) - take[k]) / total))
    out = []
    for k, v in groups.items():
        out += rng.sample(v, take[k])
    rng.shuffle(out)
    return out[:max(n, len(groups) * 2)]


def make(src: str, sample: int = 20, seed: int = 1, out: str = "") -> str:
    rows = read_csv(src)
    if not rows:
        sys.exit("That list is empty.")
    picked = sample_rows(rows, max(4, sample), seed)
    sheet = [{"business": r.get("business", ""), "website": r.get("website", ""), "site_title": r.get("site_title", ""), "niche_match": r.get("niche_match") or "unknown",
              "category": r.get("category", ""), "search_city": r.get("search_city", ""), "is_right": "", "note": ""} for r in picked]
    dst = out or str(out_path("audit", Path(src).stem))
    write_csv(dst, sheet)
    print(f"{len(sheet)} of {len(rows)} leads -> {dst}")
    print("Open it and write y or n in is_right for each: is it a real business of the type you searched, with its own website? Then: python dse.py audit " + dst + " --score")
    return dst


def label(v: str) -> bool | None:
    s = (v or "").strip().lower()
    return True if s in YES else False if s in NO else None


def score(path: str, show: bool = True) -> dict:
    rows = read_csv(path)
    lab = [(r, label(r.get("is_right", ""))) for r in rows]
    lab = [(r, ok) for r, ok in lab if ok is not None]
    if not lab:
        sys.exit("No is_right answers found. Write y or n in the is_right column for each lead, then run this again.")
    res: dict = {"labelled": len(lab), "right": sum(1 for _, ok in lab if ok)}
    res["precision"] = round(100 * res["right"] / res["labelled"])
    by: dict[str, list[bool]] = {}
    for r, ok in lab:
        by.setdefault(r.get("niche_match") or "unknown", []).append(ok)
    res["by_level"] = {k: {"n": len(v), "precision": round(100 * sum(v) / len(v))} for k, v in sorted(by.items(), key=lambda kv: LEVELS.index(kv[0]) if kv[0] in LEVELS else 99)}
    strong = [ok for r, ok in lab if (r.get("niche_match") or "unknown") in STRONG]
    res["strong_precision"] = round(100 * sum(strong) / len(strong)) if strong else None
    res["strong_share"] = round(100 * len(strong) / len(lab))
    wrong = [r for r, ok in lab if not ok]
    hosts: dict[str, int] = {}
    for r in wrong:
        h = host(r.get("website", ""))
        if h:
            hosts[h] = hosts.get(h, 0) + 1
    res["repeat_wrong_hosts"] = sorted([h for h, c in hosts.items() if c >= 2])
    res["wrong"] = [(r.get("business", ""), host(r.get("website", "")), r.get("site_title", "")[:60], r.get("niche_match") or "unknown") for r in wrong]
    if show:
        print(f"{res['right']} of {res['labelled']} labelled leads are right: precision {res['precision']}%")
        for k, v in res["by_level"].items():
            print(f"  {k:<10} {v['n']:>3} leads  {v['precision']:>3}% right")
        if res["strong_precision"] is not None and res["strong_precision"] > res["precision"]:
            print(f"With --strict (only title or body evidence) precision would be about {res['strong_precision']}% and you would keep about {res['strong_share']}% of the leads.")
        elif res["precision"] >= 90:
            print("Good: this niche is clean enough to send to as it is.")
        if res["repeat_wrong_hosts"]:
            print("Wrong more than once (add to NOT_A_SITE in dse/places.py if they are directories): " + ", ".join(res["repeat_wrong_hosts"]))
        for b, h, t, lvl in res["wrong"][:8]:
            print(f"  wrong: {b} | {h} | {t} | {lvl}")
    return res
