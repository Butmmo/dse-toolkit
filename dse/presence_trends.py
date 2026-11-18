"""Presence: what is in the news for your market this week (a trend prompt for your content), from a public news feed.

    python dse.py presence trends "dentists marketing" [us|uk|ca|au]

It reads ONE public RSS feed (Google News search, the feed Google publishes for exactly this) for the words you give, keeps the newest headlines of the last 7 days with their publisher and date, and
writes my-lists/<words>-trends.json for Presence > Research. Only headlines, publishers and dates are kept (no article is opened, no website or social account is read). Use them as prompts: react
with your own useful view, and say where the news came from. Nothing is posted anywhere. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .common import LISTS, slug

REGIONS = {"us": ("US", "en-US", "US:en"), "uk": ("GB", "en-GB", "GB:en"), "ca": ("CA", "en-CA", "CA:en"), "au": ("AU", "en-AU", "AU:en")}
QUERY_RE = re.compile(r"^[A-Za-z0-9 ,.'&/-]{3,80}\Z")
MAX_ITEMS = 10
MAX_BYTES = 600_000
FEED = "https://news.google.com/rss/search"


def feed_url(query: str, region: str = "us") -> str:
    gl, hl, ceid = REGIONS[region]
    return FEED + "?" + urllib.parse.urlencode({"q": f"{query} when:7d", "hl": hl, "gl": gl, "ceid": ceid})


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DSEToolkit/1.0; market news)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(MAX_BYTES).decode("utf-8", "replace")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def parse_feed(xml_text: str, today: dt.date | None = None) -> list[dict]:
    """Headlines from an RSS feed: newest first, at most 10, one per headline, from the last 7 days. The feed's own "Headline - Publisher" title is split."""
    today = today or dt.date.today()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out, seen = [], set()
    for it in root.iter("item"):
        title = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
        pub = re.sub(r"\s+", " ", (it.findtext("source") or "")).strip()
        if pub and title.endswith(" - " + pub):
            title = title[: -len(pub) - 3].strip()
        elif not pub and " - " in title:
            title, pub = title.rsplit(" - ", 1)
        try:
            d = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            continue
        if not title or not pub or (today - d).days > 7 or (today - d).days < -1 or _norm(title) in seen:
            continue
        seen.add(_norm(title))
        out.append({"headline": title[:160], "publisher": pub[:60], "date": d.isoformat()})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:MAX_ITEMS]


def build(query: str, region: str, items: list[dict], today: dt.date | None = None) -> dict:
    return {"v": 1, "kind": "presence-trends", "made": (today or dt.date.today()).isoformat(), "query": query, "region": region, "source": "Google News public RSS feed", "items": items}


def run(query: str, region: str = "us", fetcher=fetch, today: dt.date | None = None, out=print) -> int:
    query = (query or "").strip()
    if not QUERY_RE.match(query):
        out("Give 3 to 80 plain words for your market, for example: dentists marketing")
        return 1
    if region not in REGIONS:
        out(f"Region must be one of {', '.join(REGIONS)}.")
        return 1
    try:
        xml_text = fetcher(feed_url(query, region))
    except (urllib.error.URLError, TimeoutError, OSError):
        out("Could not reach the news feed: check your internet and try again.")
        return 1
    items = parse_feed(xml_text, today)
    if not items:
        out("No headlines from the last 7 days for those words. Try broader words (for example the trade plus 'news').")
        return 1
    LISTS.mkdir(parents=True, exist_ok=True)
    p = LISTS / f"{slug(query)}-trends.json"
    p.write_text(json.dumps(build(query, region, items, today), indent=2, ensure_ascii=False), encoding="utf-8")
    out(f"{len(items)} headlines for '{query}' ({region.upper()}), last 7 days. Saved {p.name} for Presence > Research.")
    for i in items:
        out(f"  {i['date']}  {i['headline']}  ({i['publisher']})")
    return 0


def cli(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 2
    return run(args[0], args[1] if len(args) > 1 else "us")


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
