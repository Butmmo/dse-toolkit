"""Podcast leads for The Broadcast Engine, from Apple Podcasts' free public search and each show's own feed.

  python dse.py podcasts "marketing; startup; sales" [--max 60] [--genre business]

Genre-locked on purpose (Business & Entrepreneurship by default: hosts who understand marketing ROI and have
budget). For each show it reads the public RSS feed and works out:
  - days since the last episode, and how regular the schedule is
  - whether there is a video version (video files or a YouTube link)
  - how thin the show notes are
  - the owner's contact email when the feed publishes it (podcast feeds often do, for directories)
Shows silent for more than --max-silent days (default 180) are dropped: they're not producing.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import email.utils
import re
import statistics
import time
import xml.etree.ElementTree as ET

import requests

from .common import UA, log, out_path, write_csv

GENRES = {"business": 1321, "entrepreneurship": 1493, "marketing": 1496, "management": 1491, "careers": 1410,
          "investing": 1412, "non-profit": 1494, "technology": 1318, "health": 1512, "education": 1304}
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "content": "http://purl.org/rss/1.0/modules/content/"}


def search(term: str, genre_id: int, limit: int = 200) -> list[dict]:
    r = requests.get("https://itunes.apple.com/search",
                     params={"media": "podcast", "term": term, "genreId": genre_id, "limit": limit, "country": "US"},
                     headers=UA, timeout=30)
    r.raise_for_status()
    time.sleep(3.2)                                # Apple asks for about 20 searches a minute at most
    return r.json().get("results", [])


def _date(s: str) -> dt.datetime | None:
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def read_feed(url: str) -> dict:
    out = {"feed_ok": "no"}
    try:
        r = requests.get(url, headers=UA, timeout=25)
        root = ET.fromstring(r.content)
    except Exception as e:
        out["feed_note"] = f"feed didn't open ({type(e).__name__})"
        return out
    ch = root.find("channel")
    if ch is None:
        return out
    items = ch.findall("item")
    dates = sorted((d for d in (_date(i.findtext("pubDate") or "") for i in items) if d), reverse=True)
    now = dt.datetime.now(dt.timezone.utc)
    gaps = [(a - b).days for a, b in zip(dates[:12], dates[1:13])]
    notes = [len(re.sub(r"<[^>]+>", " ", (i.findtext("description") or i.findtext("content:encoded", namespaces=NS) or "")).strip())
             for i in items[:10]]
    enc_types = [(i.find("enclosure").get("type") or "") for i in items[:10] if i.find("enclosure") is not None]
    blob = (ET.tostring(ch, encoding="unicode") if len(items) < 400 else "")[:400000].lower()
    owner = ch.find("itunes:owner", NS)
    out.update({
        "feed_ok": "yes",
        "episodes": len(items),
        "last_episode": dates[0].date().isoformat() if dates else "",
        "days_since_last": (now - dates[0]).days if dates else "",
        "typical_gap_days": int(statistics.median(gaps)) if gaps else "",
        "irregular": "yes" if len(gaps) >= 4 and statistics.mean(gaps) > 0 and statistics.pstdev(gaps) / statistics.mean(gaps) > 0.6 else "no",
        "has_video": "yes" if any(t.startswith("video") for t in enc_types) or "youtube.com" in blob or "youtu.be" in blob else "no",
        "show_notes_chars": int(statistics.median(notes)) if notes else 0,
        "website": (ch.findtext("link") or "").strip(),
        "email": (owner.findtext("itunes:email", namespaces=NS) or "").strip() if owner is not None else "",
        "host": (owner.findtext("itunes:name", namespaces=NS) or "").strip() if owner is not None else "",
    })
    return out


def gaps_for(s: dict) -> list[tuple[int, str]]:
    g = []
    d = s.get("days_since_last")
    typical = s.get("typical_gap_days") or 7
    if isinstance(d, int) and d > max(30, 2 * typical):
        g.append((3, f"the last episode went out {d} days ago, after a steady run of {s['episodes']} episodes"))
    if s.get("irregular") == "yes":
        g.append((2, "episodes come out on an irregular schedule, which makes it hard for listeners to build a habit"))
    if s.get("has_video") == "no":
        g.append((2, "there's no video version of the show, so it's missing YouTube and short-clip reach"))
    if isinstance(s.get("show_notes_chars"), int) and s["show_notes_chars"] < 250:
        g.append((1, "the show notes are a line or two, so episodes are hard to find in search"))
    return sorted(g, reverse=True)


OPENER = ("Hi {host}, I came across {show} while looking at {genre} podcasts. One thing I noticed: {gap_line}. "
          "I edit and produce podcasts like yours, and I put together a short plan for fixing that without adding to your week. Want me to send it?")


def find(terms: str, genre: str = "business", cap: int = 60, max_silent: int = 180, out: str = "") -> str:
    genre = re.sub(r"\s+", " ", genre or "business").strip()[:40] or "business"
    gid = GENRES.get(genre.lower())          # a genre of your own (not in the list) searches Apple Podcasts by your topics without a genre filter
    shows, seen = [], set()
    for term in [t.strip() for t in re.split(r"[;|]", terms) if t.strip()]:
        hits = search(term, gid)
        log(f"  '{term}': {len(hits)} shows from Apple Podcasts")
        for h in hits:
            if h.get("feedUrl") and h["collectionId"] not in seen and (not gid or str(gid) in [str(x) for x in h.get("genreIds", [])]):
                seen.add(h["collectionId"])
                shows.append(h)
    log(f"Reading {len(shows)} feeds...")
    with cf.ThreadPoolExecutor(12) as ex:
        feeds = list(ex.map(lambda h: read_feed(h["feedUrl"]), shows))
    rows = []
    for h, f in zip(shows, feeds):
        if f.get("feed_ok") != "yes" or not isinstance(f.get("days_since_last"), int) or f["days_since_last"] > max_silent:
            continue
        if f.get("episodes", 0) < 10:
            continue                                 # too new to judge, and rarely has budget yet
        g = gaps_for(f)
        row = {"business": h.get("collectionName", ""), "host": f.get("host") or h.get("artistName", ""),
               "email": f.get("email", ""), "website": f.get("website", ""), "apple_url": h.get("collectionViewUrl", ""),
               "feed_url": h["feedUrl"], "episodes": f["episodes"], "last_episode": f["last_episode"],
               "days_since_last": f["days_since_last"], "typical_gap_days": f["typical_gap_days"], "irregular": f["irregular"],
               "has_video": f["has_video"], "show_notes_chars": f["show_notes_chars"], "category": h.get("primaryGenreName", ""),
               "gap_count": len(g), "gaps_found": "; ".join(x for _, x in g), "gap_used": g[0][1] if g else "",
               "source": f"Apple Podcasts search + public RSS feed, {time.strftime('%Y-%m-%d')}"}
        row["opener"] = OPENER.format(host=(row["host"].split(" ")[0] or "there"), show=row["business"], genre=genre.lower(), gap_line=row["gap_used"]) if g else ""
        row["variant"] = "broadcast-gap-v1" if g else ""
        rows.append(row)
    rows.sort(key=lambda r: (-r["gap_count"], r["email"] == ""))
    rows = rows[:cap]
    dst = out or str(out_path("podcasts", genre, terms.split(";")[0]))
    write_csv(dst, rows)
    print(f"{len(rows)} active {genre} podcasts ({sum(1 for r in rows if r['email'])} with a public email) -> {dst}")
    return dst
