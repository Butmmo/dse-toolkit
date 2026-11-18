"""The app's whole niche list (512 business types) as built-in business types for the lead finder.

The data is dse/niche_catalog.json, generated from the app's niche list by tools/build_niche_catalog.py (read that file for how each niche is mapped).
Each niche has the 1 to 4 nearest Foursquare categories and words from its own name that a real business website uses. A few niches are the same as one of
the hand-made types in places.KINDS ("same_as"): they point at it. Pure data and lookups: no network, no other dse imports.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CATALOG_FILE = Path(__file__).with_name("niche_catalog.json")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def load() -> list[dict]:
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


CATALOG: list[dict] = load()
NAME_INDEX: dict[str, str] = {}          # lower-cased niche name -> built-in type id
TERM_INDEX: dict[str, str] = {}          # the plain word the app gives the finder ("tree service") -> built-in type id
for _e in CATALOG:
    _kind = _e.get("same_as") or _e["id"]
    NAME_INDEX[_norm(_e["name"])] = _kind
    TERM_INDEX.setdefault(_norm(_e["term"]), _kind)


def entries() -> list[dict]:
    """The niches that get a built-in type of their own (not the ones that point at a hand-made type)."""
    return [e for e in CATALOG if "fsq" in e]


def lookup(text: str) -> str | None:
    """A built-in type id for what the app (or you) typed: the niche's exact name or its finder term. None when it is neither."""
    t = _norm(text)
    return NAME_INDEX.get(t) or TERM_INDEX.get(t)


def term_for(kind: str) -> str | None:
    """The plain finder term of a niche's built-in type id ('stump-grinding' -> 'stump grinding'), or None for any other id."""
    for e in CATALOG:
        if e["id"] == kind:
            return e["term"]
    return None


def by_category() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in CATALOG:
        out.setdefault(e["category"], []).append(e)
    return out
