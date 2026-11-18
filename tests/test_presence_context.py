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
ok("the tool is in the catalog, takes one engine, and uploads only the short findings file", [f["name"] for f in cat["fields"]] == ["engine", "ai"] and cat["fields"][0]["choices_from"] == "engines" and cat["outputs"] == [{"glob": "my-lists/*-presence-context.json", "upload": True}])

# ---- the optional local AI reading
raw_ok = 'Sure. {"summary": "A plan to win new patients through Instagram, aimed at busy parents, using short reels and a weekly LinkedIn post.", "questions": ["Is the 4 posts a week still realistic with your current team?", "Should LinkedIn be aimed at patients or at referring dentists?", "x?", "Which of the four content pillars has worked best so far?", "A fourth real question that gets cut away?"]}'
ai = C.parse_ai(raw_ok)
ok("the model's reply is read into a short summary and at most three real questions (too short ones are dropped)", ai and ai["summary"].startswith("A plan to win new patients") and len(ai["questions"]) == 3 and all(q.endswith("?") and len(q) >= 12 for q in ai["questions"]))
ok("hostile or odd replies are made safe or refused: tags and control characters removed, long text cut, no JSON or the wrong shape gives nothing", (lambda h: "<" not in h["summary"] and ">" not in h["summary"] and len(h["summary"]) <= 500 and all("<" not in q for q in h["questions"]))(C.parse_ai('{"summary": "<script>alert(1)</script> ' + "a" * 900 + '", "questions": ["<b>Is this a real question for you</b>?"]}')) and C.parse_ai("no json here") is None and C.parse_ai("[1,2]") is None and C.parse_ai('{"summary": "x", "questions": "not a list"}') is None and C.parse_ai('{"summary": "", "questions": []}') is None)
dg = C.ai_digest([("a/plan.md", "Key: sk-ant-abcdefghijklmnopqrstuvwxyz123456 " + "word " * 600), ("b/other.md", "second file text " * 100), ("c/third.md", "third file " * 300)])
ok("what the model sees is short, redacted and starts with the strongest files", len(dg) <= C.AI_BUDGET + 300 and "sk-ant-" not in dg and dg.index("a/plan.md") < dg.index("b/other.md"))
seen = []
def stub(model, system, user, timeout=150): seen.append((model, system, user)); return raw_ok
out4 = []
code = C.run_context("orlando-dentists", out4.append, ai=True, chat=stub, installed=lambda: ["gemma3:4b"])
j4 = json.loads((C.LISTS / "orlando-dentists-presence-context.json").read_text(encoding="utf-8"))
ok("with the AI on, the file gets the model's summary and its questions as open questions, after the rule-based ones; nothing leaves this PC but through the model call", code == 0 and j4["ai"]["model"] == "gemma3:4b" and j4["ai"]["summary"].startswith("A plan to win") and [q["id"] for q in j4["questions"]][-3:] == ["open:1", "open:2", "open:3"] and all(q["kind"] == "open" and q["options"] == [] for q in j4["questions"][-3:]) and len(seen) == 1 and seen[0][0] == "gemma3:4b" and "sk-ant-" not in seen[0][2] and "hunter2" not in seen[0][2] and any("My PC's AI" in x for x in out4))
ok("the model is only shown files that read like social media work", "invoices and the lease" not in seen[0][2] and "instagram-content-plan" in seen[0][2])
out5 = []
C.run_context("orlando-dentists", out5.append, ai=False, chat=stub)
j5 = json.loads((C.LISTS / "orlando-dentists-presence-context.json").read_text(encoding="utf-8"))
ok("with the AI off the model is never called and the file has no AI part", "ai" not in j5 and len(seen) == 1 and not any(q["kind"] == "open" for q in j5["questions"]))
def boom(*a, **k): raise OSError("Ollama is off")
out6 = []
code6 = C.run_context("orlando-dentists", out6.append, ai=True, chat=boom, installed=lambda: ["gemma3:4b"])
j6 = json.loads((C.LISTS / "orlando-dentists-presence-context.json").read_text(encoding="utf-8"))
ok("when Ollama is off or the model answers badly, the reading by rules still stands and the PC says so", code6 == 0 and "ai" not in j6 and any("rules only" in x for x in out6) and len(j6["questions"]) >= 7 and C.run_context("orlando-dentists", [].append, ai=True, chat=lambda *a, **k: "nonsense", installed=lambda: ["m"]) == 0 and C.run_context("orlando-dentists", [].append, ai=True, chat=stub, installed=lambda: []) == 0)
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]["dse.presence_context"]
ok("the tool offers the AI reading as a switch that is on by default", any(f["name"] == "ai" and f["type"] == "bool" and f.get("default") is True for f in cat["fields"]) and {"flag": "--ai", "field": "ai"} in cat["args"])

# ---- second review fixes
sec = td / "work" / "secret-plan"; sec.mkdir(parents=True)
(sec / "content-ideas.md").write_text("""# Content ideas for social media
- Webhook for posting alerts: https://discord.com/api/webhooks/123456789012345678/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
- LinkedIn access token AQXdSP1234567890abcdefghijklmnopqrstuvwxyz
- Password for Instagram login is Hunter2Hunter2!
- Five myths about whitening that patients believe
- A tour of the front desk and how we answer texts
Follow https://www.instagram.com/reel/Cx123abc/ and https://www.youtube.com/watch?v=abc123 and https://www.instagram.com/orlando.smiles/ and @media screens.
""", encoding="utf-8")
scrubbed = C.scrub((sec / "content-ideas.md").read_text(encoding="utf-8"))
ok("review 2: a Discord webhook address, an unlabelled access token and a 'password for X is Y' line are hidden, and the good lines stay", "discord.com/api/webhooks" not in scrubbed and "AQXdSP1234567890" not in scrubbed and "Hunter2" not in scrubbed and "Five myths about whitening" in scrubbed and "front desk" in scrubbed)
fr = C.read_file("content-ideas.md", "text", (sec / "content-ideas.md").read_text(encoding="utf-8"))
tops = " ".join(t for t, _ in fr["topics"])
ok("review 2: no secret can become a post idea or go to the model: the topics and the digest are clean", "webhooks" not in tops and "AQXdSP" not in tops and "Hunter2" not in tops and any("myths about whitening" in t for t, _ in fr["topics"]) and "Hunter2" not in C.ai_digest([("a.md", (sec / "content-ideas.md").read_text(encoding="utf-8"))]) and "webhooks" not in C.ai_digest([("a.md", (sec / "content-ideas.md").read_text(encoding="utf-8"))]))
hs = {h for _p, h in fr["handles"]}
ok("review 2: address paths and style words are not account handles (reel, watch, @media), a real profile still is", not ({"reel", "watch", "media", "Cx123abc"} & hs) and "orlando.smiles" in hs)
# a sibling folder that starts with the same letters, and a junction to it, are outside the folder
import os, subprocess
plan = td / "jt" / "plan"; plan.mkdir(parents=True); priv = td / "jt" / "plan-private"; priv.mkdir()
(plan / "a-social.md").write_text("social media plan for instagram and linkedin, captions and hashtags, content calendar.", encoding="utf-8")
(priv / "notes-social.md").write_text("PRIVATE social media plan instagram linkedin captions hashtags content calendar.", encoding="utf-8")
linked = False
try:
    if os.name == "nt":
        linked = subprocess.run(["cmd", "/c", "mklink", "/J", str(plan / "link"), str(priv)], capture_output=True).returncode == 0
    else:
        os.symlink(priv, plan / "link"); linked = True
except OSError:
    linked = False
got = [r for r, _k, _t in C.walk_texts(plan)]
ok("review 2: a junction or link to a sibling folder that starts with the same letters is not followed (nothing outside the folder is read)" + ("" if linked else " [no junction could be made here]"), "a-social.md" in got and not any("notes-social" in g or g.startswith("link") for g in got))
ok("review 2: the engine context reader and this reader agree on what is inside a folder", C.cf.inside(plan, plan / "a-social.md") and not C.cf.inside(plan, priv) and not C.cf.inside(plan, str(plan) + "-private") and C.cf.inside(plan, plan))
# a PDF whose compressed stream expands enormously is read to a limit, not to its full size
import time, zlib
bomb = td / "bomb.pdf"
payload = b"BT (hello social media plan) Tj ET " + b"0" * (120 * 1024 * 1024)
bomb.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + zlib.compress(payload, 9) + b"\nendstream\nendobj\n%%EOF")
t0 = time.time(); txt = C.cf.read_doc(bomb); dt_ = time.time() - t0
ok("review 2: a PDF stream that expands 1000 to 1 is cut at a limit: quick, and only a small piece is read", dt_ < 5 and len(txt) < 200_000)

# ---- calendars, schedules, idea banks, posting times and brand files (a real plan looks like this)
import datetime as dtm
cal = td / "work" / "calendar-plan"; cal.mkdir(parents=True); (cal / "brand").mkdir()
(cal / "brand" / "profile-picture.jpg").write_bytes(b"\xff\xd8")
(cal / "brand" / "logo.svg").write_text("<svg/>", encoding="utf-8")
(cal / "calendar-2026-12-10-to-2027-01-08.md").write_text("""# Studio content calendar 10 Dec - 08 Jan 2027

Made by a script. Times: carousel 18:00 WAT (11am Dallas), post 21:00 WAT (2pm Dallas). Instagram and Facebook.

| Date | Carousel | Single post | Question card |
|---|---|---|---|
| Thu 10 Dec | ED60: 25 of 25 studios I checked have no fast reply promise | ED59: Selective, not desperate. | - |
| Fri 11 Dec | ED64: I asked ChatGPT for designers in 6 cities. Were you named? | ED66: Fewer visits. Bigger stakes today. | What do you wish clients did first? |
| Fri 01 Jan | ED70: A new year, a kinder auto-reply for every inquiry | - | - |
| Fri 08 Jan | ED71: What a good first call agenda looks like for you | ED72: Remind, do not chase them | - |
""", encoding="utf-8")
(cal / "schedule-2026-12-10.json").write_text(json.dumps({"_note": "scheduled posts", "2026-12-10": {"carousel": "ED60", "post": "ED59"}, "2026-12-11": {"carousel": "ED64", "post": "ED66"}, "2026-12-12": {"carousel": "ED58", "post": ""}}), encoding="utf-8")
(cal / "ideas.json").write_text(json.dumps({"how_to_add": "x", "ideas": [{"id": "ED01", "topic": "late-night inquiries", "hooks": ["Your best client wrote to you <em>at 11pm.</em> Did anyone answer?"]}, {"id": "ED02", "topic": "x", "hooks": ["short"]}, {"id": "ED03", "topic": "Why portfolios do not close a sale without a reply", "hooks": []}]}), encoding="utf-8")
rng = C._range_of("calendar-2026-12-10-to-2027-01-08.md", "")
ok("a calendar file's range is read from its name, and from a title like '10 Dec - 08 Jan 2027'", rng == (dtm.date(2026, 12, 10), dtm.date(2027, 1, 8)) and C._range_of("x.md", "# Plan 10 Dec - 08 Jan 2027\n") == (dtm.date(2026, 12, 10), dtm.date(2027, 1, 8)) and C._range_of("x.md", "no dates here") is None)
ok("a table date takes its year from that range: '10 Dec' is 2026 and '01 Jan' is 2027, and an ISO date stands as written", C._cell_date("Thu 10 Dec", rng) == dtm.date(2026, 12, 10) and C._cell_date("Fri 01 Jan", rng) == dtm.date(2027, 1, 1) and C._cell_date("2026-12-20", None) == dtm.date(2026, 12, 20) and C._cell_date("Mon 29 Feb", rng) is None and C._cell_date("whenever", rng) is None)
sch = C.schedule_from("calendar-2026-12-10-to-2027-01-08.md", (cal / "calendar-2026-12-10-to-2027-01-08.md").read_text(encoding="utf-8"), "text")
ok("a markdown calendar table gives the first and last day, the number of days and items, and the columns, counting only filled cells", sch and sch["schedule"]["from"] == "2026-12-10" and sch["schedule"]["to"] == "2027-01-08" and sch["schedule"]["days"] == 4 and sch["schedule"]["items"] == 8 and set(sch["schedule"]["columns"]) >= {"carousel", "single post"})
ok("the scheduled sentences become post ideas with the ids (ED60:) removed, and one-or-two-word cells are dropped", any(t.startswith("25 of 25 studios") for t, _ in sch["topics"]) and not any(__import__("re").match(r"^ED\d", t) for t, _ in sch["topics"]) and any(t.startswith("Fewer visits") for t, _ in sch["topics"]) and not any(t in ("-", "") for t, _ in sch["topics"]))
js = C.schedule_from("schedule-2026-12-10.json", (cal / "schedule-2026-12-10.json").read_text(encoding="utf-8"), "json")
ok("a date-keyed JSON schedule gives its days and items (empty slots do not count)", js and js["schedule"]["days"] == 3 and js["schedule"]["items"] == 5 and js["schedule"]["from"] == "2026-12-10" and js["schedule"]["to"] == "2026-12-12")
ok("a file with no dates, a plain list or broken JSON gives no schedule", C.schedule_from("a.md", "just words", "text") is None and C.schedule_from("a.json", "[1,2]", "json") is None and C.schedule_from("a.json", "{{", "json") is None and C.schedule_from("a.md", "| Name | Role |\n|---|---|\n| Ada | lead |\n", "text") is None)
ib = C.ideas_from_json((cal / "ideas.json").read_text(encoding="utf-8"))
ok("an idea bank gives the first hook without markup, and skips short hooks", ib and ib[0][0].startswith("Your best client wrote to you at 11pm.") and "<em>" not in ib[0][0] and len(ib) == 2 and ib[1][0].startswith("Why portfolios do not close"))
ok("brand files are listed by name only (pictures and design files in a brand folder), nothing is read", sorted(C.brand_files(cal)) == ["brand/logo.svg", "brand/profile-picture.jpg"])
ok("a time line must really give clock times: 'Times: carousel 18:00 ...' counts, 'one time zone split' does not", C.read_file("c.md", "text", "Made by a script. Times: carousel 18:00 WAT (11am Dallas), post 21:00 WAT.\n")["times"][0].startswith("carousel 18:00") and C.read_file("c.md", "text", "We use one time: it is a zone split in a sentence about nothing.\n")["times"] == [])
# the whole run on this folder, as a Function's engine would inherit it
(E.ENGINES / "calendar-eng").mkdir(); (E.ENGINES / "calendar-eng" / "engine.json").write_text(json.dumps({"context_folders": [{"path": str(cal)}]}), encoding="utf-8")
outc = []
C.run_context("calendar-eng", outc.append, today=dtm.date(2026, 11, 20))
jc = json.loads((C.LISTS / "calendar-eng-presence-context.json").read_text(encoding="utf-8"))
fc = jc["findings"]
ok("the whole run finds the schedule across the calendar and the JSON, the posting times, the brand files, and puts the scheduled ideas first", fc["schedule"]["from"] == "2026-12-10" and fc["schedule"]["to"] == "2027-01-08" and fc["schedule"]["items"] >= 8 and any("18:00" in t for t in fc["times"]) and fc["brand"] == ["brand/logo.svg", "brand/profile-picture.jpg"] and fc["topics"][0]["text"].startswith("25 of 25 studios"))
qc = {x["id"]: x for x in jc["questions"]}
ok("it asks what to do about the weeks that are already scheduled, with the day after the last scheduled post offered as the start", qc["schedule"]["kind"] == "schedule" and [o["value"] for o in qc["schedule"]["options"]] == ["start_after", "alongside", "ignore"] and "2027-01-09" in qc["schedule"]["options"][0]["label"] and "2027-01-08" in qc["schedule"]["text"] and "times" in qc and "brand" in qc)
past = C.questions_for({"schedule": {"from": "2020-01-01", "to": "2020-02-01", "items": 5, "days": 3, "columns": []}})
ok("a schedule that is already over only offers to keep a note of it", past[0]["id"] == "schedule" and [o["value"] for o in past[0]["options"]] == ["note", "ignore"] and "is over" in past[0]["text"])

# ---- brand style from the plan
sty = C.style_from([("brand.md", "Our colours: #1a4d3a green, #F4E9D8 cream, #1A4D3A again, and white #FFFFFF. Fonts: Playfair Display for headlines, Inter for text."), ("notes.md", "colour #12345 is too short, and &#123456 is an entity")])
ok("it reads brand colours (most used first, white dropped when others exist) and fonts that really appear in the text", sty["colors"][:2] == ["#1A4D3A", "#F4E9D8"] and "#FFFFFF" not in sty["colors"] and sty["fonts"] == ["Playfair Display", "Inter"] and len(sty["colors"]) == 2)
ok("no colour in the text means no style, and look-alikes are not read as colours", C.style_from([("a.md", "nothing here, # 123456 and &#123456; and #12345")]) is None and C.style_from([("a.md", "colours: #FFFFFF #000000")])["colors"] == ["#FFFFFF", "#000000"])
qs = C.questions_for({"style": sty})
ok("it asks whether to use the plan's colours and fonts as the Function's own look, saying which ones", qs[0]["id"] == "style" and qs[0]["kind"] == "style" and "#1A4D3A" in qs[0]["text"] and "Playfair Display" in qs[0]["text"] and [o["value"] for o in qs[0]["options"]] == ["adopt", "skip"])
ok("review fix: a six-digit code in an ordinary file (a ticket, an invoice) is not a brand colour, but one in a brand file or on a colour line is", C.style_from([("notes.md", "Invoice #123456 is paid, ticket #ABCDEF closed")]) is None and C.style_from([("brand/palette.md", "#123456")])["colors"] == ["#123456"] and C.style_from([("plan.md", "Primary colour: #123456")])["colors"] == ["#123456"])
src = Path(C.__file__).read_text(encoding="utf-8")
ok("it only reads: one write (its own result file), no delete or move, and the only network call is to this PC's own Ollama", src.count(".write_text(") == 1 and "unlink" not in src and "rename" not in src and "shutil" not in src and "requests" not in src and src.count("urlopen(") == 1 and 'OLLAMA = "http://localhost:11434/api/chat"' in src and "api/tags" not in src)
ok("no em dash in the file", chr(0x2014) not in src)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
