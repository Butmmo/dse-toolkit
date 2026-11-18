"""Tests for Presence trends: headlines for your market from a public news feed (dse/presence_trends.py). No network.   python tests/test_presence_trends.py"""
import datetime as dt
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import presence_trends as T  # noqa: E402

fails = 0


def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        fails += 1


today = dt.date(2026, 11, 18)
def item(title, pub, days, src=True):
    d = (today - dt.timedelta(days=days)).strftime("%a, %d %b %Y 10:00:00 GMT")
    return f"<item><title>{title}</title><link>https://example.test/a</link><pubDate>{d}</pubDate>" + (f"<source url='https://x.test'>{pub}</source>" if src else "") + "</item>"
XML = "<rss><channel><title>x</title>" + "".join([
    item("Dental groups grow - Dentistry Today", "Dentistry Today", 1), item("Dental groups grow - Dentistry Today", "Dentistry Today", 1),
    item("Reviews now drive patient choice - DrBicuspid", "DrBicuspid", 0), item("Old story - Somewhere", "Somewhere", 12),
    item("No publisher at all", "", 2, src=False), item("Texting patients - Practice Weekly", "", 3, src=False), item("A &amp; B Dental opens - Local News", "Local News", 2),
]) + "</channel></rss>"

items = T.parse_feed(XML, today)
heads = [i["headline"] for i in items]
ok("headlines are newest first, split from the publisher, one per headline, from the last 7 days only", heads[0] == "Reviews now drive patient choice" and heads.count("Dental groups grow") == 1 and "Old story" not in heads and items == sorted(items, key=lambda x: x["date"], reverse=True))
ok("a title without a source tag is split on its last ' - ', and one with no publisher at all is dropped", "Texting patients" in heads and [i for i in items if i["headline"] == "Texting patients"][0]["publisher"] == "Practice Weekly" and "No publisher at all" not in heads)
ok("entities are read as text and every item has a headline, a publisher and a date", "A & B Dental opens" in heads and all(i["headline"] and i["publisher"] and len(i["date"]) == 10 for i in items))
ok("a broken feed gives nothing, and at most ten headlines are kept", T.parse_feed("<rss><", today) == [] and T.parse_feed("", today) == [] and len(T.parse_feed("<rss><channel>" + "".join(item(f"Story {i} - P", "P", 1) for i in range(30)) + "</channel></rss>", today)) == 10)
ok("long headlines are cut", len(T.parse_feed("<rss><channel>" + item("x" * 400 + " - P", "P", 1) + "</channel></rss>", today)[0]["headline"]) == 160)

ok("the feed address is Google News search for the words and the last 7 days, in the chosen region", "news.google.com/rss/search" in T.feed_url("dentists marketing", "uk") and "when%3A7d" in T.feed_url("dentists marketing", "uk") and "gl=GB" in T.feed_url("x y z", "uk") and "gl=US" in T.feed_url("x y z", "us"))
td = Path(tempfile.mkdtemp()); T.LISTS = td
out = []
ok("the words are checked, an unknown region is refused, and nothing is fetched for them", (lambda calls: T.run("a;b", "us", lambda u: calls.append(u) or "", today, out.append) == 1 and T.run("dentists", "mars", lambda u: calls.append(u) or "", today, out.append) == 1 and T.run("ab", "us", lambda u: calls.append(u) or "", today, out.append) == 1 and calls == [])([]))
out = []
code = T.run("Dentists Marketing", "us", lambda u: XML, today, out.append)
f = td / "dentists-marketing-trends.json"
j = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
ok("a run writes the headlines with where they came from, and only headlines, publishers and dates", code == 0 and j.get("kind") == "presence-trends" and j["v"] == 1 and j["source"] == "Google News public RSS feed" and j["query"] == "Dentists Marketing" and all(set(i) == {"headline", "publisher", "date"} for i in j["items"]) and len(j["items"]) >= 4)
def offline(u): raise urllib.error.URLError("no network")
out = []
ok("no internet, or no headlines, is said in plain words and writes no file", T.run("dentists", "us", offline, today, out.append) == 1 and "internet" in out[0] and T.run("zzz qqq", "us", lambda u: "<rss><channel></channel></rss>", today, out.append) == 1 and "No headlines" in out[-1])
src = Path(T.__file__).read_text(encoding="utf-8")
ok("it reads one public feed only: no social network, no article page, no posting", src.count("urlopen(") == 1 and "instagram" not in src.lower() and "facebook" not in src.lower() and ".post(" not in src)
ok("no em dash in the file", chr(0x2014) not in src)
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
ok("the tool is in the catalog, takes the words and a region, and uploads the file", "dse.presence_trends" in cat and {f["name"] for f in cat["dse.presence_trends"]["fields"]} == {"query", "region"} and any(o["glob"] == "my-lists/*-trends.json" and o["upload"] for o in cat["dse.presence_trends"]["outputs"]))
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
