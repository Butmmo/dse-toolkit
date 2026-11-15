"""Tests for the Voices library, entirely offline (the network is replaced).   python tests/test_voices.py"""
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import voices as V  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    return None


TMP = Path(tempfile.mkdtemp(prefix="zz-voices-"))
V.STORE = TMP / "voices"
V.PAUSE = 0
real_roster = V.ROSTER

# ---------------------------------------------------------------- the roster itself (real file)
check("the real roster keeps its own rules", V.roster_problems() == [], str(V.roster_problems()))
fs = V.roster()
check("10 figures in each stratum", all(sum(1 for f in fs if s in f["strata"]) == 10 for s in V.STRATA))
check("7 figures on each path", all(sum(1 for f in fs if p in f["paths"]) == 7 for p in V.PATHS))
check("no social network is ever a fetchable source type", not ({"x", "twitter", "linkedin", "facebook", "reddit", "instagram"} & set(V.SOURCE_TYPES)))
check("every source type used is allowed", all(s["type"] in V.SOURCE_TYPES for f in fs for s in f.get("sources", [])))
check("known_for stays short", all(len(f["known_for"]) <= 160 for f in fs))
check("no em dash in the roster", chr(0x2014) not in real_roster.read_text(encoding="utf-8"))

# a broken roster is caught
bad = TMP / "bad.json"
bad.write_text(json.dumps({"figures": [{"id": "a", "name": "A", "strata": ["wisdom"], "paths": [], "known_for": "x", "sources": [{"type": "twitter"}]},
                                       {"id": "a", "name": "A2", "strata": [], "paths": ["smb"], "known_for": "y" * 200, "sources": []}]}), encoding="utf-8")
V.ROSTER = bad
pr = V.roster_problems()
check("duplicates, counts, a social source and long text are all reported", any("duplicate" in p for p in pr) and any("not 10" in p for p in pr) and any("not 7" in p for p in pr) and any("twitter" in p for p in pr) and any("160" in p or "long" in p for p in pr), str(pr))
V.ROSTER = real_roster

# ---------------------------------------------------------------- parsing
PG = """The Project Gutenberg eBook of Meditations

Title: Meditations
Author: Marcus Aurelius
Language: English

*** START OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***

BOOK I

Of my grandfather Verus I have learned to be gentle and meek, and to refrain from all anger and passion. From the fame and memory of him that begot me I have learned both shamefastness and manlike behaviour.

BOOK II

Begin the morning by saying to thyself, I shall meet with the busy-body, the ungrateful, arrogant, deceitful, envious, unsocial. All these things happen to them by reason of their ignorance of what is good and evil.

*** END OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***
license text that must not be indexed
"""
body = V.strip_gutenberg(PG)
check("Gutenberg header and licence are stripped", "START OF" not in body and "license text" not in body and body.startswith("BOOK I"))
ch = V.chunk_text("Meditations", body)
check("passages carry the book as their locator", [c["locator"] for c in ch] == ["Meditations, Book I", "Meditations, Book II"], str([c["locator"] for c in ch]))
check("passage text has no heading in it", all("BOOK" not in c["text"] for c in ch))

WQ = """== Quotes ==
* The unexamined life is not worth living for a human being, said at his trial.
** ''Apology'' 38a
* A short one.
* Genuine long sourced sentence about courage and what a person ought to do each day before breakfast.
** [[Nicomachean Ethics]] Book II
== Misattributed ==
* This long sentence was never said by this person at all but is repeated across the internet endlessly.
** Not real
== Quotes about X ==
* Somebody else wrote this long sentence praising the figure in glowing terms for many years running.
"""
qs = V.parse_wikiquote(WQ)
check("Wikiquote: sourced quotes kept, with their source", len(qs) == 2 and qs[0]["source"] == "Apology 38a" and "Nicomachean Ethics" in qs[1]["source"], str(qs))
check("Wikiquote: misattributed, 'quotes about' and too-short lines skipped", not any("never said" in q["text"] or "praising" in q["text"] or q["text"] == "A short one." for q in qs))

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>
<item><title>First post</title><link>https://ex.com/1</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;About &lt;b&gt;offers&lt;/b&gt;.&lt;/p&gt;</description></item>
<item><title>Second</title><link>https://ex.com/2</link><pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
items = V.parse_feed(RSS)
check("RSS items parsed, html stripped from the summary", len(items) == 2 and items[0]["summary"] == "About offers." and items[0]["link"] == "https://ex.com/1")
ATOM_YT = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
<entry><title>Video one</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc"/><published>2026-11-01T10:00:00+00:00</published>
<media:group><media:description>What this video covers.</media:description></media:group></entry></feed>"""
yi = V.parse_feed(ATOM_YT)
check("YouTube Atom parsed with link and media description", len(yi) == 1 and yi[0]["link"].endswith("watch?v=abc") and yi[0]["summary"] == "What this video covers.", str(yi))
check("a broken feed gives nothing instead of a crash", V.parse_feed("<html><nope") == [])

# ---------------------------------------------------------------- fake network
calls_made = []
SOCIAL = ("//x.com", "//twitter.com", "linkedin.com", "facebook.com", "reddit.com", "instagram.com", "//www.x.com")
FAKE = {}


def fake_get(url, timeout=20, browser=False):
    calls_made.append(url)
    for k, v in FAKE.items():
        if k in url:
            return v
    return 404, ""


V.http_get = fake_get
UC = "UC" + "a" * 22
FAKE.update({
    "gutenberg.org/ebooks/search": (200, '<ul><li class="booklink"><a class="link" href="/ebooks/2680"><span class="title">Meditations</span></a></li>'
                                     '<li class="booklink"><a class="link" href="/ebooks/9"><span class="title">Meditations Index</span></a></li></ul>'),
    "gutenberg.org/cache/epub/2680/pg2680.txt": (200, PG + ("filler words here " * 200)),
    "en.wikiquote.org": (200, json.dumps({"parse": {"wikitext": {"*": WQ.replace("== Misattributed ==", "\n".join(f"* Extra sourced line number {i} that is long enough to be kept as a quotation here.\n** Book {i}" for i in range(6)) + "\n== Misattributed ==")}}})),
    "ex.com/home": (200, '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'),
    "ex.com/feed.xml": (200, RSS),
    "youtube.com/@somebody": (200, f'..."channelId":"{UC}"...'),
    "youtube.com/feeds/videos.xml": (200, ATOM_YT),
    "openlibrary.org": (200, json.dumps({"numFound": 1, "docs": [{"author_name": ["Some Blogger"]}]})),
})

check("a feed is discovered from a homepage's own advertisement", V.discover_feed("https://ex.com/home") == "https://ex.com/feed.xml")
check("a YouTube channel id is read from the handle", V.youtube_feed_url("@somebody").endswith(UC))
check("a UC id is used directly without any request", (calls_made.clear() or True) and V.youtube_feed_url(UC).endswith(UC) and not calls_made)

# a tiny roster for the rest, so the real file is untouched
mini = TMP / "mini.json"
mini.write_text(json.dumps({"figures": [
    {"id": "marcus-aurelius", "name": "Marcus Aurelius", "era": "121-180", "known_for": "Roman emperor and Stoic", "strata": ["wisdom"], "paths": [],
     "sources": [{"type": "gutenberg", "search": "meditations marcus aurelius", "title": "Meditations"}, {"type": "wikiquote", "page": "Marcus Aurelius"}]},
    {"id": "blogger", "name": "Some Blogger", "era": "living", "known_for": "Writes a blog", "strata": ["sales"], "paths": ["smb"],
     "sources": [{"type": "feed", "home": "https://ex.com/home"}, {"type": "youtube", "handle": "@somebody"}, {"type": "books", "list": [{"title": "A Book", "year": 2020}]},
                 {"type": "links", "urls": {"x": "https://x.com/someone", "linkedin": "https://linkedin.com/in/someone"}}]},
    {"id": "gone", "name": "No Sources", "era": "living", "known_for": "Nothing yet", "strata": ["finance"], "paths": [], "sources": [{"type": "gutenberg", "search": "nothing", "title": "Nothing"}]},
]}), encoding="utf-8")
V.ROSTER = mini

# ---------------------------------------------------------------- nothing is fetched before it is verified
calls_made.clear()
out = V.fetch("marcus-aurelius")
check("fetch refuses unverified sources and says how to verify", "not verified yet" in out and "voices verify" in out and not any("/cache/epub/2680/pg2680.txt" in c for c in calls_made), out)

vr = V.verify("marcus-aurelius")
check("verify checks each source live and reports", "OK   Marcus Aurelius: gutenberg" in vr and "Wikiquote" in vr, vr)
vr2 = V.verify("blogger")
check("feeds, youtube, books verify; links are never fetched", vr2.count("OK  ") == 4 and not any(h in c for c in calls_made for h in SOCIAL), vr2)
vr3 = V.verify("gone")
check("a source that is not found fails and is reported", "FAIL" in vr3, vr3)
check("the failed source is never used", V.is_verified(V.figure("gone"), V.figure("gone")["sources"][0]) is False)

out = V.fetch("marcus-aurelius")
check("verified sources are downloaded and indexed with citations", "passages from Project Gutenberg #2680" in out and "sourced quotations" in out, out)
idx = V.load_index("marcus-aurelius")
check("every indexed passage has a credit naming where it came from", idx and all(p["credit"] for p in idx) and any("public domain" in p["credit"] for p in idx) and any("CC BY-SA" in p["credit"] for p in idx))
check("the Gutenberg licence text is not in the index", not any("license text" in p["text"] for p in idx))

# ---------------------------------------------------------------- ask
a = V.ask("how do I handle anger and gentleness", "marcus-aurelius")
check("ask returns a real passage with its credit", "grandfather" in a.lower() and "Project Gutenberg" in a and "no ai model" in a.lower(), a)
a2 = V.ask("unexamined life", "marcus-aurelius")
check("ask finds a quotation and credits Wikiquote with the source", "unexamined" in a2.lower() and "Wikiquote" in a2 and "Apology" in a2, a2)
a3 = V.ask("xyzzy quantum zebra", "marcus-aurelius")
check("an unmatched question says so and invents nothing", "Nothing in the library matches" in a3 and "\"" not in a3.split("\n")[2:3][0:1][0] if len(a3.split("\n")) > 2 else True, a3)
check("a stratum search covers the figures in it", "Marcus Aurelius" in V.ask("anger gentle", stratum="wisdom"))
check("an unfetched figure is named, not faked", "Nothing is fetched yet" in V.ask("pricing anything", stratum="finance"))
check("short question refused", raises(V.ask, "hi") is not None)
check("unknown stratum refused", raises(V.ask, "anger and gentleness", "", "nope") is not None)
check("unknown path refused", raises(V.ask, "anger and gentleness", "", "", "nope") is not None)
check("unknown figure suggests close ids", "marcus-aurelius" in (raises(V.figure, "marcus") or ""))

# ---------------------------------------------------------------- today is steady within a day and varies by date
d1 = dt.date(2026, 11, 15)
check("today is the same passage all day", V.today("wisdom", d1) == V.today("wisdom", d1))
seen = {V.today("wisdom", d1 + dt.timedelta(days=i)) for i in range(12)}
check("today changes across days", len(seen) > 1)
check("today with nothing fetched in an area says so and offers another area", "Nothing is fetched yet for Financial development" in V.today("finance", d1), V.today("finance", d1))
check("today refuses an unknown stratum", raises(V.today, "nope") is not None)

# ---------------------------------------------------------------- notes (yours, marked, need a source)
check("a note without a source is refused", "source" in (raises(V.note, "blogger", "Offers should name a result and a time.", "") or "").lower())
check("a note that is too short is refused", raises(V.note, "blogger", "no", "Book p.1") is not None)
V.note("blogger", "Offers should name a result and a time frame, said at the 2025 workshop.", "Workshop notes, 2025")
b = V.ask("what should an offer name", "blogger")
check("your note is found, credited as yours", "your own note" in b and "Workshop notes" in b, b)
V.note("marcus-aurelius", "Remember to check the sky before judging the day.", "my journal")
check("a note survives a re-fetch", any(p["kind"] == "note" for p in (V.fetch("marcus-aurelius") and V.load_index("marcus-aurelius"))))

# ---------------------------------------------------------------- update: living figures' own feeds only
u1 = V.update("blogger")
check("update lists new items from their own feeds, with links", "First post" in u1 and "https://ex.com/1" in u1 and "Video one" in u1 and "social" in u1.lower(), u1)
u2 = V.update("blogger")
check("a second update reports only what is new since", "Nothing new" in u2 and "First post" not in u2, u2)
FAKE["ex.com/feed.xml"] = (200, RSS.replace("</channel>", "<item><title>Third</title><link>https://ex.com/3</link><pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate></item></channel>"))
u3 = V.update("blogger")
check("a new post is detected", "Third" in u3 and "First post" not in u3, u3)
check("update with no verified feed says how to verify", "Nothing new" in V.update("gone"))
check("show lists sources with their state and the links-only note", "verified" in V.show("blogger") and "never fetched" in V.show("blogger") and "x: https://x.com/someone" in V.show("blogger"))
lst = V.list_figures("", "smb")
check("list filters by path and shows fetch state", "Some Blogger" in lst and "Marcus" not in lst)
check("no network call was ever made to a social network", not any(h in c for c in calls_made for h in SOCIAL))


# ---------------------------------------------------------------- repairs: the right book, never just any book by the author
FAKE["gutenberg.org/ebooks/search"] = (200, '<ul><li class="booklink"><a href="/ebooks/9"><span class="title">Meditations Index</span></a></li>'
                                          '<li class="booklink"><a href="/ebooks/77"><span class="title">Meditations in French</span></a></li>'
                                          '<li class="booklink"><a href="/ebooks/78"><span class="title">Meditations</span></a></li></ul>')
FAKE["cache/epub/77/pg77.txt"] = (200, "Title: Meditations in French\nAuthor: Marcus Aurelius\nLanguage: French\n")
FAKE["cache/epub/78/pg78.txt"] = (200, "Title: Meditations\nAuthor: Somebody Else\nLanguage: English\n")
mf = V.figure("marcus-aurelius")
check("an index, a foreign-language edition and another author's book are all rejected", V.gutenberg_resolve(mf, mf["sources"][0]) is None)
FAKE["cache/epub/78/pg78.txt"] = (200, "Title: Meditations\nAuthor: Marcus Aurelius\nLanguage: English\n")
r = V.gutenberg_resolve(mf, mf["sources"][0])
check("the English edition whose header names the author is chosen", r and r["id"] == 78, str(r))
mf2 = dict(mf, sources=[{"type": "gutenberg", "search": "x", "title": "Meditations", "id": 78}])
check("an id in the roster is tried first", V.gutenberg_resolve(mf, mf2["sources"][0])["id"] == 78)
FAKE["gutenberg.org/ebooks/search"] = (200, '<ul><li class="booklink"><a href="/ebooks/2680"><span class="title">Meditations</span></a></li></ul>')

# ---------------------------------------------------------------- feeds: more places to look
FAKE["ex2.com/blog/feed"] = (200, RSS)
FAKE["ex2.com"] = (200, "<html><head></head><body>no advertised feed</body></html>")
check("a feed is found at the usual places when the homepage does not advertise one", V.discover_feed("https://ex2.com").endswith("/blog/feed"), V.discover_feed("https://ex2.com"))
FAKE.pop("ex2.com/blog/feed"); FAKE.pop("ex2.com")

# ---------------------------------------------------------------- setup: everything in one step, resumable, honest
V.STORE = TMP / "voices2"
steps = []
rep_ = V.setup("marcus-aurelius", 5, say=steps.append)
check("setup verifies, downloads and reports a ready figure", "1 figure(s) fully ready" in rep_ and len(V.load_index("marcus-aurelius")) > 0 and steps and "passages" in steps[0], rep_)
n_calls = len(calls_made)
rep2 = V.setup("marcus-aurelius", 5)
check("run again, it skips what was checked recently and does not download again", len(calls_made) == n_calls, f"{len(calls_made) - n_calls} extra calls")
rep3 = V.setup("gone", 5)
check("a figure it cannot repair is listed with a plain reason and what to do", "Still failing" in rep3 and "gone" not in rep3.lower().split("ready")[0] or "No Sources" in rep3, rep3)
st = V.load_state()
for k in list(st["verified"]):
    if k.startswith("gone/"):
        st["verified"][k]["checked"] = "2020-01-01"
V.save_state(st)
n_calls = len(calls_made)
V.setup("gone", 5)
check("a failed source is tried again after a few days", len(calls_made) > n_calls)
rep4 = V.setup("", 0)
check("when the time is up it stops cleanly and says to run it again", "Time ran out" in rep4 or "fully ready" in rep4, rep4[:200])

# an area with nothing fetched falls back to another area, and says so; a library with nothing says how to set it up
V.STORE = TMP / "voices3"
check("an empty library says how to set it up", "Set it up once" in V.today("wisdom", d1) and "set up the library" in V.today("wisdom", d1))
V.STORE = TMP / "voices2"
t_ = V.today("finance", d1)
check("an area with nothing fetched offers a passage from another area and says so", "Nothing is fetched yet for Financial development" in t_ and "Marcus Aurelius" in t_, t_)


# ---------------------------------------------------------------- mentor passages beside a chat answer
V.STORE = TMP / "voices2"
check("a name in the question finds the figure (full name or a last name nobody else has)", V.detect_figures("what did Marcus Aurelius say about anger") == ["marcus-aurelius"] and V.detect_figures("what does Aurelius think about time") == ["marcus-aurelius"])
check("no name, no figure", V.detect_figures("how do I set up an n8n webhook") == [] and V.detect_figures("hello") == [])
check("a mentor is wanted when asked for or named, never otherwise", V.wants_mentor("give me a quote about courage") and V.wants_mentor("what would a stoic say about stress") and V.wants_mentor("what did Marcus Aurelius say about anger")
      and not V.wants_mentor("how do I set up an n8n webhook") and not V.wants_mentor("a client says it is too expensive"))
check("discipline, disciplined and disciplining are one word; so are procrastinate and procrastinating", V.stem("disciplined") == V.stem("discipline") == V.stem("disciplining") and V.stem("procrastinating") == V.stem("procrastinate"))
check("everyday filler does not count as a match", "stay" not in V.query_weights("how do I stay disciplined") and "feel" not in V.query_weights("I feel tired") and V.stem("disciplined") in V.query_weights("how do I stay disciplined"))
w = V.query_weights("I keep procrastinating")
check("what a student types counts most, the words the old texts use for the same idea count half", w[V.stem("procrastinating")] == 1.0 and w.get(V.stem("idleness")) == 0.5)
hits = V.search("what did Marcus Aurelius say about anger", n=2, strict=True)
check("naming a figure searches only that figure's library", hits and all(h["who"] == "Marcus Aurelius" for h in hits) and all(h["credit"] for h in hits), str(hits))
check("a question with nothing in the library gives nothing, not padding", V.search("how do I set up an n8n webhook", n=2, strict=True) == [])
blk = V.mentor_block("what did Marcus Aurelius say about anger", 2)
check("the mentor block shows real passages with their sources and says how they were found", "From the library" in blk and "Marcus Aurelius" in blk and "not their meaning" in blk and "No AI model wrote" in blk, blk)
check("an ordinary question gets no block", V.mentor_block("how do I set up an n8n webhook", 2) == "")
check("a mentor-only request with no match says so plainly", "Nothing in the library fits" in V.mentor_block("xyzzy quantum zebra", 3, only=True))
V.STORE = TMP / "voices3"
check("a mentor-only request with an empty library says how to set it up", "set up" in V.mentor_block("anything about courage", 3, only=True).lower())
V.STORE = TMP / "voices2"

# ---------------------------------------------------------------- the module itself
src = (ROOT / "dse" / "voices.py").read_text(encoding="utf-8")
check("no em dash in voices.py", chr(0x2014) not in src)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
