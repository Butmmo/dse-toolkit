"""Presence tools: research for content, graphics and video (the HQ half of Citadel's Presence page).

  python dse.py presence insights <list.csv>     turn a checked or enriched list into what to talk about (counts only, no business names)
  python dse.py presence graphic ...             a picture for a post (Pillow)                   (added below)
  python dse.py presence video ...               a video from pictures, voiceover and captions (ffmpeg)

INSIGHTS. A list your HQ tools built (Foursquare Open Source Places, then the website problem check and the enrichment) says what a whole market is like: how many have no online booking, no text
or chat, an old site; which social platforms they link to. This turns those counts into content ideas, each with the real numbers behind it and where the numbers came from, so the student can say
"4 of 6 dentists I checked in Orlando cannot be texted from their website" and mean it. The result is aggregate only: no business name, address, phone or email leaves the list. Small samples are
labelled small. Nothing is posted or sent anywhere. Stdlib only for insights.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from .common import LISTS, read_csv, slug

MIN_SAMPLE_NOTE = 10          # under this many rows a result is called a small sample
SOCIAL = ("instagram", "facebook", "linkedin", "twitter", "tiktok", "youtube")
YESNO = {  # column -> (what a "no" means, plain label)
    "online_booking": "cannot book or request a quote online from their website",
    "text_chat": "cannot be texted or chatted with from their website",
    "review_link": "have no link on their website to leave a review",
    "reviews_shown": "show no reviews on their website",
    "fresh_site": "have a website that looks out of date",
}

# gap label (lowercase, as found in gaps_found) -> (what it means, content idea)
GAP_IDEAS: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"text|chat"), {"pillar": "teach", "topic": "Why people message before they call, and 3 ways {who} can answer a text in a minute", "also": "help"}),
    (re.compile(r"book|quote|appointment"), {"pillar": "help", "topic": "The 3 things that make a new customer finish an online booking form: a check of how {who} do it", "also": "teach"}),
    (re.compile(r"copyright|outdated|old |fresh|dated"), {"pillar": "teach", "topic": "How a website tells a new customer whether {who} are still open and caring, and a 5-minute refresh", "also": "help"}),
    (re.compile(r"review"), {"pillar": "teach", "topic": "How {who} can ask for reviews without it feeling awkward", "also": "help"}),
    (re.compile(r"email|contact form|phone"), {"pillar": "teach", "topic": "The contact details a new customer looks for first on a website, and where to put them", "also": "help"}),
]


def _yes(v: str) -> bool:
    return str(v or "").strip().lower().startswith(("yes", "y", "true", "1"))


def _no(v: str) -> bool:
    return str(v or "").strip().lower().startswith(("no", "n ", "false", "0"))


def _plural(cat: str) -> str:
    c = (cat or "businesses").strip().lower()
    return c if c.endswith("s") else c + "s"


def insights(rows: list[dict], list_name: str = "", today: dt.date | None = None) -> dict:
    """Counts and content ideas from a list's rows. Pure: tested without any file."""
    today = today or dt.date.today()
    n = len(rows)
    cat = Counter((r.get("category") or "").strip() for r in rows if (r.get("category") or "").strip()).most_common(1)
    category = cat[0][0] if cat else ""
    city_c = Counter((r.get("search_city") or r.get("city") or "").strip() for r in rows if (r.get("search_city") or r.get("city") or "").strip()).most_common(1)
    city = city_c[0][0] if city_c else ""
    who = _plural(category)
    checked = [r for r in rows if any(k in r for k in YESNO)]
    social = {p: sum(1 for r in rows if (r.get(p) or "").strip()) for p in SOCIAL if any(p in r for r in rows)}
    with_site = sum(1 for r in rows if (r.get("website") or "").strip())
    gaps: Counter = Counter()
    for r in rows:
        for g in str(r.get("gaps_found") or "").split(";"):
            g = g.strip()
            if g and not g.lower().startswith("check by hand"):
                gaps[g] += 1
    yn = []
    for col, meaning in YESNO.items():
        have = [r for r in rows if (r.get(col) or "").strip()]
        if have:
            k = sum(1 for r in have if _no(r.get(col)))
            yn.append({"key": col, "label": meaning, "count": k, "of": len(have)})
    where = f"{who} in {city}" if city else who
    src = f"HQ list of {n} {where}, checked on {today.isoformat()}" + (" (Foursquare Open Source Places, then the website problem check)" if checked else " (Foursquare Open Source Places)")
    note = "Small sample: say 'of the ones I checked', never 'most'." if n < MIN_SAMPLE_NOTE else ""
    ideas: list[dict] = []
    used = set()
    for row in sorted(yn, key=lambda x: -x["count"] / max(1, x["of"])):
        if row["count"] == 0:
            continue
        for rx, spec in GAP_IDEAS:
            probe = {"online_booking": "book quote", "text_chat": "text chat", "review_link": "review", "reviews_shown": "review", "fresh_site": "copyright dated"}[row["key"]]
            if rx.search(probe) and spec["topic"] not in used:
                used.add(spec["topic"])
                ideas.append({"id": f"i{len(ideas) + 1}", "pillar": spec["pillar"], "topic": spec["topic"].format(who=who),
                              "facts": [{"text": f"{row['count']} of {row['of']} {where} I checked {row['label']}.", "source": src}], "platforms": []})
                break
    for label, k in gaps.most_common(6):
        for rx, spec in GAP_IDEAS:
            if rx.search(label.lower()) and spec["topic"] not in used and k > 0:
                used.add(spec["topic"])
                ideas.append({"id": f"i{len(ideas) + 1}", "pillar": spec["pillar"], "topic": spec["topic"].format(who=who),
                              "facts": [{"text": f"{k} of {n} {where} I checked: \"{label}\".", "source": src}], "platforms": []})
                break
    if social and n:
        best = sorted(social.items(), key=lambda x: -x[1])
        top = [p for p, k in best if k >= max(1, n // 2)]
        facts = [{"text": f"{k} of {n} {where} link to {p.capitalize()} from their website.", "source": src} for p, k in best[:3] if k > 0]
        ideas.append({"id": f"i{len(ideas) + 1}", "pillar": "ecosystem", "topic": f"Where {who} already are online, and who is doing it well", "facts": facts, "platforms": top[:3]})
        low = [p for p in ("instagram", "facebook", "linkedin") if p in social and social[p] * 2 < n]
        if low:
            ideas.append({"id": f"i{len(ideas) + 1}", "pillar": "teach", "topic": f"Most {who} I looked at have no {low[0].capitalize()} presence yet: what a first month could look like",
                          "facts": [{"text": f"Only {social[low[0]]} of {n} {where} I checked link to {low[0].capitalize()}.", "source": src}], "platforms": [low[0]]})
    return {
        "v": 1, "kind": "presence-insights", "made": today.isoformat(), "list": slug(list_name, 60), "category": category, "city": city, "n": n,
        "with_website": with_site, "checked": len(checked), "social": social, "problems": yn, "gaps": [{"label": g, "count": k, "of": n} for g, k in gaps.most_common(8)],
        "source": src, "sample_note": note, "ideas": ideas[:8],
    }


def to_markdown(r: dict) -> str:
    out = [f"# What to talk about: {r['category'] or 'your list'} {('in ' + r['city']) if r['city'] else ''}", "", f"Source: {r['source']}", ""]
    if r["sample_note"]:
        out += [f"**{r['sample_note']}**", ""]
    out += ["## What the check found"]
    for p in r["problems"]:
        out.append(f"- {p['count']} of {p['of']} {p['label']}")
    if r["social"]:
        out += ["", "## Social platforms linked from their websites"] + [f"- {p.capitalize()}: {k} of {r['n']}" for p, k in sorted(r["social"].items(), key=lambda x: -x[1])]
    out += ["", "## Content ideas, each with its evidence"]
    for i in r["ideas"]:
        out += [f"- **{i['pillar'].capitalize()}**: {i['topic']}"] + [f"  - {f['text']} (source: {f['source']})" for f in i["facts"]]
    return "\n".join(out) + "\n"


def run_insights(csv_path: str, out=print) -> int:
    p = Path(csv_path)
    if not p.exists():
        cand = LISTS / csv_path
        p = cand if cand.exists() else p
    if not p.exists():
        out(f"I could not find {csv_path}. Pick a list from my-lists.")
        return 1
    rows = read_csv(p)
    if not rows:
        out("That list is empty.")
        return 1
    r = insights(rows, p.stem)
    base = p.with_name(p.stem + "-insights")
    base.with_suffix(".json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(r), encoding="utf-8")
    out(f"{r['n']} rows read: {len(r['ideas'])} content ideas, counts only (no business names). Saved {base.with_suffix('.json').name} and .md next to the list.")
    for i in r["ideas"]:
        out(f"  {i['pillar']:9} {i['topic']}")
    return 0


def cli(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "insights":
        if not rest:
            print("python dse.py presence insights <list.csv>")
            return 1
        return run_insights(rest[0])
    if cmd in ("graphic", "video", "carousel", "voice-setup"):
        from . import presence_make
        return presence_make.cli([cmd] + rest)
    if cmd == "context":
        from . import presence_context
        return presence_context.cli(rest)
    if cmd == "trends":
        from . import presence_trends
        return presence_trends.cli(rest)
    if cmd == "publish":
        from . import publish
        return publish.run_cli(rest)
    print(f"Unknown command '{cmd}'. Try: insights, trends, context, graphic, video, carousel, voice-setup, publish")
    return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
