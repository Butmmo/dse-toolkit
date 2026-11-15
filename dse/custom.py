"""Make the streamlined tools yours: your own problem-check (a pack), and the shared rules for values you type yourself.

    python dse.py mypack "Wedding photographers" --sells "faster galleries and a booking page" \\
        --checks "online booking, book now, schedule => there is no way to book a session online" \\
        --checks "pricing, packages, investment => the site never shows what a session costs"

The built-in packs (SMB, Voice AI, CareBridge, Ministry ...) are written for one path each. A pack of your own works for any business you sell to:
you say what a good website of that kind shows (words that count as "has it") and what you would say when it does not. A check is a gap
when none of its words appear on the site's own pages. Nothing is invented: the opener is your sentence with the business, the city and the gap filled in.
Packs you make live on your PC (data/custom-packs/) and appear next to the built-in ones in every tool that asks for a pack.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import DATA

PACK_DIR = DATA / "custom-packs"
DASH = chr(0x2014)
DEFAULT_PAGES = ["contact", "about", "services", "book", "booking", "pricing", "packages", "faq"]
DEFAULT_OPENER = "Hi {business} team, I was looking at businesses in {city} and noticed {gap_line}. I help with exactly that: {sells}. Want me to send a short plan for fixing it?"


def slug(text: str, keep: int = 40) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")[:keep]


def pack_ids() -> list[str]:
    return sorted(p.stem for p in PACK_DIR.glob("*.json")) if PACK_DIR.is_dir() else []


def load_custom(name: str) -> dict | None:
    p = PACK_DIR / f"{name}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def parse_checks(items: list[str]) -> list[dict]:
    """'words that count as having it, comma separated => what to say when it is missing' (one per line), up to 8."""
    out = []
    for raw in items:
        for line in re.split(r"[\r\n]+", raw or ""):
            if not line.strip():
                continue
            if "=>" not in line:
                raise ValueError(f"Write each check as: words to look for, separated by commas => what to say if they are missing. Not understood: '{line.strip()[:60]}'")
            left, right = [x.strip() for x in line.split("=>", 1)]
            words = [w.strip().lower() for w in left.split(",") if w.strip()]
            if not 1 <= len(words) <= 10 or any(not 2 <= len(w) <= 40 for w in words):
                raise ValueError(f"Give 1 to 10 words (2 to 40 letters each) before => in: '{line.strip()[:60]}'")
            if not 8 <= len(right) <= 200:
                raise ValueError(f"What to say when it is missing is 8 to 200 characters in: '{line.strip()[:60]}'")
            if "{" in right or "}" in right:
                raise ValueError("Write plain words in the 'what to say' part (no curly brackets).")
            out.append({"words": words, "say": right.rstrip(". ")})
    if not 1 <= len(out) <= 8:
        raise ValueError("Give 1 to 8 checks.")
    return out


def make_pack(name: str, sells: str, checks: list[str], opener: str = "", pages: str = "") -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    sid = "my-" + slug(name, 30)
    if not 3 <= len(name) <= 60 or sid == "my-":
        raise ValueError("Give your check a name of 3 to 60 characters, like 'Wedding photographers'.")
    sells = re.sub(r"\s+", " ", sells or "").strip()
    if not 8 <= len(sells) <= 160:
        raise ValueError("Say in one sentence what you offer (8 to 160 characters), like 'galleries that load fast and a booking page'.")
    if "{" in sells or "}" in sells:
        raise ValueError("Write plain words for what you offer (no curly brackets).")
    parsed = parse_checks(checks)
    if opener:
        opener = re.sub(r"\s+", " ", opener).strip()
        if not 30 <= len(opener) <= 600:
            raise ValueError("Your opener is 30 to 600 characters.")
        try:
            opener.format(business="X", city="Y", gap_line="Z", sells="W")
        except (KeyError, IndexError, ValueError):
            raise ValueError("The opener may only use {business}, {city}, {gap_line} and {sells} in curly brackets.")
        if "{gap_line}" not in opener:
            raise ValueError("The opener must include {gap_line}: that is the specific thing you noticed.")
    pg = [w for w in (slug(x, 20) for x in re.split(r"[,;]", pages or "")) if w] or DEFAULT_PAGES
    checks_out = []
    for i, c in enumerate(parsed, 1):
        checks_out.append({"id": f"c{i}", "label": f"Shows: {c['words'][0]}", "missing": f"No {c['words'][0]}", "type": "present", "weight": max(1, 4 - i),
                           "look_for": [re.escape(w) for w in c["words"]], "gap_line": c["say"]})
    pack = {"label": name + " (my own)", "variant": f"custom-{sid}-v1", "about": f"Your own check for {name}. You offer: {sells}.", "max_pages": 4, "pages": pg[:12], "checks": checks_out,
            "opener": (opener or DEFAULT_OPENER).replace("{sells}", sells)}
    text = json.dumps(pack, indent=1, ensure_ascii=False)
    if DASH in text:
        raise ValueError("Please use a colon or a hyphen instead of the long dash.")
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    (PACK_DIR / f"{sid}.json").write_text(text + "\n", encoding="utf-8")
    lines = [f"# Your own check: {name}", "", f"Saved as the pack '{sid}'. It now appears in the Your path list of the lead and website tools (and in: python dse.py packs).", "", "A website is flagged when none of these words appear on its pages:"]
    for c in checks_out:
        lines.append(f"- {', '.join(x for x in [w.replace(chr(92), '') for w in c['look_for']])}  ->  \"{c['gap_line']}\" (weight {c['weight']})")
    lines += ["", "Opener (the business, city and gap are filled in per lead):", pack["opener"], "",
              f"Use it: python dse.py check {sid} <list.csv>   or   python dse.py list {sid} \"<your business type>\" \"Tampa FL\"", "Nothing is sent."]
    return "\n".join(lines) + "\n"
