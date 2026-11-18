"""Tests for Presence > Earlier plan: finding an existing social media plan in an engine's folders and asking how to use it (dse/presence_context.py).   python tests/test_presence_context.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import engines as E  # noqa: E402
from dse import presence_context as C  # noqa: E402

fails = 0


def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        fails += 1


td = Path(tempfile.mkdtemp())
E.ENGINES = td / "engines"
C.engine_dir = E.engine_dir
C.LISTS = td / "lists"
eng = E.ENGINES / "orlando-dentists"; eng.mkdir(parents=True)
old = td / "work" / "old-ai-plan"; old.mkdir(parents=True)
(old / "instagram-content-plan.md").write_text("""# Social media plan for Orlando Smiles

Audience: busy parents in Orlando who put off dental visits.
Goal: get 20 new patient inquiries a month from Instagram and 500 followers by March.
Brand voice: warm, plain-spoken and a little funny, never salesy.

## Content pillars
- Tooth care myths busted
- Meet the team
- Patient smile stories (with permission)
- What happens at a first visit

We post 4 times a week on Instagram and once a week on LinkedIn. Our account is @orlando.smiles and the LinkedIn page is https://www.linkedin.com/company/orlando-smiles-dental .
Use hashtags like #orlandodentist #smilemakeover #dentaltips. Reels do best. Also try Threads and Snapchat later.
Facebook can repeat the Instagram posts. Captions should be short, with a question at the end. Instagram carousels get saved a lot.
""", encoding="utf-8")
(old / "calendar.csv").write_text("date,platform,topic\n2026-11-02,instagram,Myth: you should brush right after eating\n2026-11-04,linkedin,How we cut no-shows with text reminders\n2026-11-06,instagram,Meet Dr Lee and the front desk team\n", encoding="utf-8")
(old / "README.md").write_text("# Old folder\nThis folder holds invoices and the lease. Nothing about marketing here at all, just paperwork and boring admin notes for the accountant.\n", encoding="utf-8")
(old / "api-notes.md").write_text("Instagram caption helper notes. The hashtags to use: #dentalcare. My key is sk-ant-abcdefghijklmnopqrstuvwxyz123456 for the caption bot. Posting on instagram daily would be good, social media tips.\n", encoding="utf-8")
(old / "secrets.txt").write_text("instagram password hunter2 social media plan content calendar", encoding="utf-8")
(old / ".env").write_text("INSTAGRAM_TOKEN=abc123456789 social media", encoding="utf-8")
(old / "_private-keys").mkdir(); (old / "_private-keys" / "instagram-plan.md").write_text("social media content plan instagram linkedin hashtags captions", encoding="utf-8")
(old / "archive.zip").write_bytes(b"PK")
(eng / "engine.json").write_text(json.dumps({"context_folders": [{"path": str(old)}], "title": "Orlando dentists"}), encoding="utf-8")
(eng / "drafts").mkdir(); (eng / "drafts" / "social-posts.csv").write_text("topic\nthis is a send draft that must not be read as a plan\n", encoding="utf-8")
(eng / "social-notes.md").write_text("Engine notes about the social media plan: post on LinkedIn twice a week about reviews, Instagram stories on Fridays.\n", encoding="utf-8")

fol = C.inherited_folders("orlando-dentists")
ok("a Function inherits the engine's attached folders and the engine's own folder", old.resolve() in fol and eng.resolve() in fol and len(fol) == 2)
(E.ENGINES / "x1").mkdir(); (E.ENGINES / "x1" / "engine.json").write_text(json.dumps({"context_folders": [{"path": str(Path.home())}]}), encoding="utf-8")
ok("a folder that is unsafe (too broad) is not inherited", all(p == (E.ENGINES / "x1").resolve() for p in C.inherited_folders("x1")))

paths = [rel for root in fol for rel, _k, _t in C.walk_texts(root)]
ok("reading follows the engine context rules: no secrets or key files, no .env, no archives, no key folders, no send drafts", all("secrets" not in p and ".env" not in p and "_private-keys" not in p and ".zip" not in p and "drafts/" not in p for p in paths) and any(p.endswith("instagram-content-plan.md") for p in paths))
out = []
code = C.run_context("orlando-dentists", out.append)
f = C.LISTS / "orlando-dentists-presence-context.json"
j = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
fi = j.get("findings", {})
ok("it finds the social media files, ranks the strongest, and leaves out the unrelated one", code == 0 and j["kind"] == "presence-context" and j["v"] == 1 and any("instagram-content-plan.md" in s["path"] for s in j["sources"]) and not any("README" in s["path"] for s in j["sources"]) and j["sources"][0]["score"] >= j["sources"][-1]["score"])
ok("platforms are ranked by how much the plan talks about them", fi["platforms"][0]["key"] == "instagram" and any(p["key"] == "linkedin" for p in fi["platforms"]) and fi["platforms"][0]["mentions"] > fi["platforms"][1]["mentions"])
ok("account handles are found, from @names and from profile addresses, with the platform they belong to", any(h["platform"] == "instagram" and h["handle"] == "orlando.smiles" for h in fi["handles"]) and any(h["platform"] == "linkedin" and "orlando-smiles" in h["handle"] for h in fi["handles"]))
ok("the posting rhythm, voice, goal and audience the plan asked for are kept as short quotes", any("4 times a week" in c for c in fi["cadence"]) and any("warm, plain-spoken" in v for v in fi["voice"]) and any("20 new patient inquiries" in g for g in fi["goals"]) and any("busy parents" in a for a in fi["audience"]))
ok("content themes are read from the pillars list, and hashtags are collected", fi["themes"][:2] == ["Tooth care myths busted", "Meet the team"] and len(fi["themes"]) == 4 and "orlandodentist" in fi["hashtags"] and "dentalcare" in fi["hashtags"])
ok("a content calendar's rows become post ideas with the platform and the file they came from, and drafts are counted", fi["drafts"] == 3 and any(t["text"].startswith("Myth: you should brush") and t["platform"] == "instagram" and t["file"].endswith("calendar.csv") for t in fi["topics"]) and any(t["platform"] == "linkedin" for t in fi["topics"]))
ok("other platforms Presence does not plan for are named, not ignored", "threads" in fi["others"] and "snapchat" in fi["others"])
raw = f.read_text(encoding="utf-8")
ok("nothing that looks like a key, token or password reaches the result, and no whole file is copied into it", "sk-ant-" not in raw and "hunter2" not in raw and "abc123456789" not in raw and "invoices and the lease" not in raw and len(raw) < 20000)
q = {x["id"]: x for x in j["questions"]}
ok("it asks about the platforms, the handles, the rhythm, the themes, the voice, the ideas, the hashtags, the goals and the other platforms, one question each, with fixed options",
   {"platforms", "handle:instagram", "cadence", "themes", "voice", "topics", "hashtags", "goals", "others"} <= set(q) and all(len(x["options"]) >= 2 and x["text"].endswith("?") for x in j["questions"]) and len({x["id"] for x in j["questions"]}) == len(j["questions"]))
two = C.questions_for({"handles": [{"platform": "instagram", "handle": "a_one", "mentions": 2}, {"platform": "instagram", "handle": "b_two", "mentions": 1}]})
ok("a single handle asks yes or no, and two handles ask which one", q["handle:instagram"]["options"][0]["value"] == "yes" and two[0]["id"] == "handle:instagram" and two[0]["options"][0]["value"] == "a_one" and two[0]["options"][-1]["value"] == "none")
(E.ENGINES / "empty-eng").mkdir(); (E.ENGINES / "empty-eng" / "engine.json").write_text("{}", encoding="utf-8")
o2 = []
ok("nothing found means no questions and no file, with a plain pointer on how to attach a folder", C.run_context("empty-eng", o2.append) == 0 and "found no social media plan" in o2[0] and "--add" in o2[0] and not (C.LISTS / "empty-eng-presence-context.json").exists())
o3 = []
try:
    rc = C.run_context("nope-engine", o3.append)
except SystemExit as e:
    rc, o3 = 1, [str(e)]
ok("an engine that does not exist is said plainly", rc == 1 and "No engine" in o3[0])
ok("nothing in the folders was changed, moved or deleted", sorted(p.name for p in old.iterdir()) == sorted([".env", "README.md", "_private-keys", "api-notes.md", "archive.zip", "calendar.csv", "instagram-content-plan.md", "secrets.txt"]) and "hunter2" in (old / "secrets.txt").read_text(encoding="utf-8"))
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]["dse.presence_context"]
ok("the tool is in the catalog, takes one engine, and uploads only the short findings file", [f["name"] for f in cat["fields"]] == ["engine"] and cat["fields"][0]["choices_from"] == "engines" and cat["outputs"] == [{"glob": "my-lists/*-presence-context.json", "upload": True}])
src = Path(C.__file__).read_text(encoding="utf-8")
ok("it only reads: one write (its own result file), no delete, move or network call", src.count(".write_text(") == 1 and "unlink" not in src and "rename" not in src and "shutil" not in src and "urlopen" not in src and "requests" not in src)
ok("no em dash in the file", chr(0x2014) not in src)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
