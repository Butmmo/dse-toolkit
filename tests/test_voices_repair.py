"""Tests for the Voices fix-it button (voices repair), entirely offline.   python tests/test_voices_repair.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import doctor, voices as V  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="zz-vrepair-"))
V.STORE = TMP / "voices"
V.PAUSE = 0
roster_file = TMP / "roster.json"
RAW = {"figures": [
    {"id": "marcus", "name": "Marcus Aurelius", "strata": ["wisdom"], "paths": [], "known_for": "x", "era": "ancient",
     "sources": [{"type": "gutenberg", "search": "Zzz Nothing", "title": "Zzz Nothing"}, {"type": "wikiquote", "page": "Wrong"},
                 {"type": "feed", "home": "https://ex.com/home"}, {"type": "links", "urls": {"home": "https://ex.com"}}]},
    {"id": "other", "name": "Other Person", "strata": [], "paths": [], "known_for": "y", "era": "living",
     "sources": [{"type": "youtube", "handle": "@nobody"}]}]}
roster_file.write_text(json.dumps(RAW), encoding="utf-8")
before = roster_file.read_text(encoding="utf-8")
V.ROSTER = roster_file

PG = "Title: Meditations\nAuthor: Marcus Aurelius\nLanguage: English\n\n*** START OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***\n\nBOOK I\n\n" + ("Of my grandfather I have learned to be gentle and meek and to refrain from anger. " * 40) + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***\n"
WQ = "== Quotes ==\n" + "\n".join(f"* Sourced line number {i} that is long enough to be kept as a real quotation here.\n** Book {i}" for i in range(5)) + "\n"
RSS = '<?xml version="1.0"?><rss version="2.0"><channel><item><title>Post</title><link>https://ex.com/1</link></item></channel></rss>'
FAKE = [
    ("action=opensearch", (200, json.dumps(["x", ["Marcus Aurelius"]]))),
    ("page=Marcus_Aurelius", (200, json.dumps({"parse": {"wikitext": {"*": WQ}}}))),
    ("cache/epub/55/pg55.txt", (200, PG)),
    ("gutenberg.org/ebooks/search", (200, '<ul><li class="booklink"><a href="/ebooks/55"><span class="title">Meditations</span></a></li></ul>')),
    ("ex.com/news.xml", (200, RSS)),
    ("https://ex.com/home", (404, "")),
    ("ex.com", (200, '<html><head><link rel="alternate" type="application/rss+xml" href="/news.xml"></head></html>')),
]


def fake_get(url, timeout=20, browser=False):
    for k, v in FAKE:
        if k in url:
            return v
    return 404, ""


V.http_get = fake_get

fl = V.failing()
check("never-checked sources are listed (links are not)", len(fl) == 4 and not any(x["type"] == "links" for x in fl), str(fl))
check("recorded_only lists nothing before any check", V.failing(recorded_only=True) == [])
V.verify()
fl = V.failing(recorded_only=True)
check("after a check the three bad sources are listed with a reason", len(fl) == 4 and all(x["detail"] for x in fl), str(fl))
check("each carries a figure:index value for the picker", {x["value"] for x in fl} == {"marcus:0", "marcus:1", "marcus:2", "other:0"})

out = V.repair("marcus")
check("the book, the page and the feed are all fixed", "3 source(s) fixed, 0 still failing" in out, out)
check("the report says a different book was used, plainly", "different public-domain book" in out and "Project Gutenberg #55" in out, out)
check("repairs are kept apart from the roster, which is untouched", roster_file.read_text(encoding="utf-8") == before and V.fixes_path().exists())
check("the next roster load applies them", V.figure("marcus")["sources"][1]["page"] == "Marcus Aurelius" and V.figure("marcus")["sources"][2]["url"].endswith("/news.xml"))
check("only the unrelated one is still failing", [x["value"] for x in V.failing()] == ["other:0"])
check("what became lawful to keep was downloaded", len(V.load_index("marcus")) >= 3, str(len(V.load_index("marcus"))))

out = V.repair("other:0")
check("an unfixable source is reported plainly, not hidden", "STILL FAILING" in out and "follow the channel by hand" in out, out)
check("it is remembered as tried", V.failing()[0]["tried"] is True)
check("nothing left to repair says so", "Nothing to repair" in V.repair("marcus"))

items = doctor.check_local(0)
line = next((i for i in items if i["name"] == "Voices sources that fail their check"), None)
check("the System check shows a tried-and-failing source as optional, not as a fix", line is not None and line["state"] == "optional", str(line))
st = V.load_state()
st["repaired"] = {}
V.save_state(st)
line = next((i for i in doctor.check_local(0) if i["name"] == "Voices sources that fail their check"), None)
check("an untried failing source is a fix that names the button", line is not None and line["state"] == "fix" and "repair" in line["fix"].lower(), str(line))

src = (ROOT / "dse" / "voices.py").read_text(encoding="utf-8")
check("no em dash in voices.py", chr(0x2014) not in src)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
