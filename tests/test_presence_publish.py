"""Tests for Presence phase 4: posting your own content to your own account, only after you approve (dse/publish.py). Nothing here touches the network or a real account.   python tests/test_presence_publish.py"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import publish as P  # noqa: E402

fails = 0


def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        fails += 1


class Store:
    def __init__(self): self.d = {}
    def get(self, n): return self.d.get(n, "")
    def set(self, n, v): self.d[n] = v
    def delete(self, n): self.d.pop(n, None)


td = Path(tempfile.mkdtemp())
P.POSTS = td / "my-posts"; P.STATE = td / "state"; P.ACCOUNTS = P.STATE / "accounts.json"; P.LOG = P.STATE / "posted.jsonl"
P.POSTS.mkdir()
TOKEN = "AQX" + "k" * 60
HOOK = "https://discord.com/api/webhooks/123456789012345678/" + "a" * 40
good = {"v": 1, "platform": "linkedin", "account": "orlando-linkedin", "title": "T", "ready": True, "text": "Why patients message before they call (and 3 ways to answer a text in a minute).\n\nHow does your front desk handle it?"}

# ---- the checks
ok("a finished post passes", P.check_post(good) == [])
ok("not a post file, an unknown platform, a bad account name and empty words are refused in plain words", all(P.check_post(x) for x in (None, [], {"platform": "tiktok", "account": "ab", "text": "x", "ready": True}, {**good, "account": "Bad Name"}, {**good, "text": "  "})))
ok("a [bracket] left in the text is refused", any("bracket" in x for x in P.check_post({**good, "text": "The detail in [the specific thing] is lovely."})))
ok("a piece the Studio did not mark ready is refused", any("ready" in x for x in P.check_post({**good, "ready": False})) and any("ready" in x for x in P.check_post({k: v for k, v in good.items() if k != "ready"})))
ok("the length limit is per platform", any("3000" in x for x in P.check_post({**good, "text": "x" * 3001})) and P.check_post({**good, "text": "x" * 3000}) == [] and any("2000" in x for x in P.check_post({**good, "platform": "discord", "text": "x" * 2001})))

# ---- LinkedIn's text format
ok("reserved characters are escaped so the post is not cut short or turned into a mention, and hashtags stay hashtags", P.linkedin_text("Tips (3) [free] <b> @ada_x * ~ | {a} \\") == "Tips \\(3\\) \\[free\\] \\<b\\> \\@ada\\_x \\* \\~ \\| \\{a\\} \\\\" and P.linkedin_text("Love #dentistry # 1") == "Love #dentistry \\# 1")

# ---- the rate rules
now = dt.datetime(2026, 11, 20, 10, 0, 0)
sha = P.text_sha("linkedin", "orlando-linkedin", good["text"])
ent = lambda mins, s="x": {"platform": "linkedin", "account": "orlando-linkedin", "sha": s, "at": (now - dt.timedelta(minutes=mins)).isoformat()}
ok("no history means no problem", P.rate_problem("linkedin", "orlando-linkedin", sha, now, []) == "")
ok("the same text twice is refused (any time), the same text from another account is not", "already" in P.rate_problem("linkedin", "orlando-linkedin", sha, now, [ent(5000, sha)]) and P.rate_problem("linkedin", "other-account", sha, now, [ent(5000, sha)]) == "")
ok("a second post inside 30 minutes waits, one after 30 minutes may go", "30 minutes" in P.rate_problem("linkedin", "orlando-linkedin", sha, now, [ent(10)]) and P.rate_problem("linkedin", "orlando-linkedin", sha, now, [ent(31)]) == "")
ok("three posts in one day is the most", "3 a day" in P.rate_problem("linkedin", "orlando-linkedin", sha, now, [ent(40), ent(90), ent(150)]) and P.rate_problem("linkedin", "orlando-linkedin", sha, now, [ent(40), ent(90)]) == "")
ok("another platform's or account's posts do not count", P.rate_problem("linkedin", "orlando-linkedin", sha, now, [{**ent(5), "platform": "discord"}, {**ent(5), "account": "z-account"}]) == "")

# ---- connecting (nothing is saved on a bad secret)
st = Store()
calls = []
def fake(method, url, headers, body=None, timeout=30):
    calls.append((method, url, headers, body))
    if "userinfo" in url: return 200, {}, json.dumps({"sub": "782bbtaQ", "name": "Ada"})
    if "api.linkedin.com/rest/posts" in url: return 201, {"x-restli-id": "urn:li:share:123"}, ""
    if "discord.com/api/webhooks" in url: return 200, {}, json.dumps({"id": "999"})
    return 500, {}, "no"
ok("a bad token, a bad webhook, a bad account name and an unknown platform are not saved", all(("Not saved" in r or "Choose" in r or "short name" in r) for r in (
    P.connect("linkedin", "orlando-linkedin", "short", store=st, http=fake), P.connect("discord", "my-server", "https://evil.example/hook", store=st, http=fake),
    P.connect("linkedin", "Bad Name", TOKEN, store=st, http=fake), P.connect("tiktok", "my-account", TOKEN, store=st, http=fake))) and st.d == {})
r = P.connect("linkedin", "Orlando-LinkedIn", TOKEN, store=st, http=fake)
ok("a LinkedIn token is checked, the member id is read from LinkedIn, the secret goes to this PC's settings only, and the reply shows no part of it", r.startswith("Connected") and st.d.get("PRESENCE_SECRET_LINKEDIN_ORLANDO_LINKEDIN") == TOKEN and TOKEN not in r and "kkkk" not in r and any("userinfo" in c[1] for c in calls)
   and json.loads(P.ACCOUNTS.read_text())["accounts"][0] == {"platform": "linkedin", "account": "orlando-linkedin", "person": "782bbtaQ", "added": dt.date.today().isoformat()} and TOKEN not in P.ACCOUNTS.read_text())
ok("when LinkedIn will not say who the member is, nothing is saved", (lambda s2: "Not saved" in P.connect("linkedin", "second-acct", TOKEN, store=s2, http=lambda *a, **k: (401, {}, "")) and s2.d == {})(Store()))
r2 = P.connect("discord", "my-server", HOOK, store=st, http=fake)
ok("a Discord webhook is kept on this PC and never written to the accounts file", r2.startswith("Connected") and st.d["PRESENCE_SECRET_DISCORD_MY_SERVER"] == HOOK and HOOK not in P.ACCOUNTS.read_text() and HOOK not in r2)
ok("the accounts report lists names only", (lambda rep: "orlando-linkedin" in rep and "my-server" in rep and TOKEN not in rep and HOOK not in rep and "a" * 30 not in rep)(P.accounts_report(st)))

# ---- previewing and posting
os.environ.pop("PRESENCE_SECRET_LINKEDIN_ORLANDO_LINKEDIN", None)
f = P.POSTS / "why-patients.json"; f.write_text(json.dumps(good), encoding="utf-8")
out = []; calls.clear()
code = P.post_file(f, "", now, st, fake, out.append)
ok("without the word POST nothing is posted: a preview shows the exact text, the account and the length", code == 0 and not any("rest/posts" in c[1] for c in calls) and "PREVIEW" in out[0] and good["text"] in out[0] and "orlando-linkedin" in out[0] and not P.LOG.exists())
for approve in ("post", "yes", "POSTED", " "):
    o = []; calls.clear()
    P.post_file(f, approve, now, st, fake, o.append)
    ok(f"approving with {approve!r} is not enough: only the exact word POST posts", not any("rest/posts" in c[1] for c in calls))
out = []; calls.clear()
code = P.post_file(f, "POST", now, st, fake, out.append)
sent = [c for c in calls if "rest/posts" in c[1]]
body = json.loads(sent[0][3]) if sent else {}
ok("with POST, one post is made on the connected account through the Posts API, with the right headers and body", code == 0 and len(sent) == 1 and sent[0][0] == "POST" and sent[0][2]["Authorization"] == f"Bearer {TOKEN}" and sent[0][2]["X-Restli-Protocol-Version"] == "2.0.0"
   and sent[0][2]["Linkedin-Version"] == P.LINKEDIN_VERSION and body["author"] == "urn:li:person:782bbtaQ" and body["visibility"] == "PUBLIC" and body["lifecycleState"] == "PUBLISHED" and body["distribution"]["feedDistribution"] == "MAIN_FEED" and not __import__("re").search(r"(?<!\\)[()]", body["commentary"]) and "\\(and 3 ways" in body["commentary"])
ok("it is logged, a record without any secret is written for the app, and the output names the post", len(P.read_log()) == 1 and (P.POSTS / "why-patients.posted.json").exists() and TOKEN not in (P.POSTS / "why-patients.posted.json").read_text() and "Posted to linkedin" in out[-1] and "urn:li:share:123" in out[-1] and TOKEN not in "\n".join(out))
rec = json.loads((P.POSTS / "why-patients.posted.json").read_text())
ok("the record says where, when and which post, and nothing else", set(rec) == {"v", "platform", "account", "at", "id", "url", "title", "sha"} and rec["id"] == "urn:li:share:123")
out = []; calls.clear()
code = P.post_file(f, "POST", now + dt.timedelta(hours=2), st, fake, out.append)
ok("posting the same file again is refused, and nothing is sent", code == 1 and not any("rest/posts" in c[1] for c in calls) and "already" in out[0])
g2 = {**good, "text": "A second, different post for the same day. What do you think?"}
f2 = P.POSTS / "second.json"; f2.write_text(json.dumps(g2), encoding="utf-8")
out = []; calls.clear()
ok("a different post 10 minutes later waits for the 30 minute gap", P.post_file(f2, "POST", now + dt.timedelta(minutes=10), st, fake, out.append) == 1 and not calls and "30 minutes" in out[0])

# ---- Discord
dg = {**good, "platform": "discord", "account": "my-server", "text": "New post: 3 ways to answer a text in a minute. @everyone"}
fd = P.POSTS / "disc.json"; fd.write_text(json.dumps(dg), encoding="utf-8")
out = []; calls.clear()
code = P.post_file(fd, "POST", now, st, fake, out.append)
dsent = [c for c in calls if "webhooks" in c[1]]
dbody = json.loads(dsent[0][3]) if dsent else {}
ok("a Discord post goes to the channel's webhook with mentions switched off, so @everyone cannot fire", code == 0 and len(dsent) == 1 and dsent[0][1] == HOOK + "?wait=true" and dbody["allowed_mentions"] == {"parse": []} and dbody["content"] == dg["text"])

# ---- failures say what went wrong
def failing(code_):
    return lambda m, u, h, b=None, timeout=30: (code_, {}, "boom")
for c, words in ((401, "expired"), (403, "w_member_social"), (0, "internet"), (429, "too many")):
    ok(f"LinkedIn answering {c} is explained in plain words and nothing is recorded", (lambda r: (not r[0]) and words in r[1])(P.post_linkedin("hello world", TOKEN, "abc12345", failing(c))))
ok("Discord answering 404 says the webhook is gone", (lambda r: (not r[0]) and "no longer exists" in r[1])(P.post_discord("hello", HOOK, failing(404))))
P.LOG.unlink(); out = []
ok("a platform failure is not logged as a post", P.post_file(f, "POST", now, st, failing(401), out.append) == 1 and P.read_log() == [] and "Not posted" in out[0])
ok("a post for an account that is not connected on this PC says so, and asks to connect first", (lambda o: P.post_file(f, "POST", now, Store(), fake, o.append) == 1 and "connect" in o[0].lower())([]))

# ---- removing
P.remove("linkedin", "orlando-linkedin", st)
ok("removing forgets the secret and the account name on this PC", "PRESENCE_SECRET_LINKEDIN_ORLANDO_LINKEDIN" not in st.d and all(a["account"] != "orlando-linkedin" for a in P.read_accounts()))


# ---- review fixes
ok("review fix: no account name can land on a setting: even 'version' is kept apart from the LinkedIn API version setting", P.secret_name("linkedin", "version") == "PRESENCE_SECRET_LINKEDIN_VERSION" and P.secret_name("linkedin", "version") != "PRESENCE_LINKEDIN_VERSION" and all(P.secret_name("linkedin", a).startswith("PRESENCE_SECRET_") for a in ("a-b", "x1", "version", "api-version")))
ok("review fix: a post file whose platform is a list, a number or missing is refused in words, never a crash", all(P.check_post({**good, "platform": v}) for v in ([], {}, 5, None, ["linkedin"])))
st2 = Store(); st2.d["PRESENCE_SECRET_LINKEDIN_KEEP_ME"] = "x"; st2.d["PRESENCE_LINKEDIN_VERSION"] = "202610"; st2.d["PRESENCE_OTHER_THING"] = "y"
ok("review fix: remove only touches a platform and an account name this tool can have made", "Choose" in P.remove("version", "x", st2) and "Choose" in P.remove("linkedin", "Bad Name", st2) and st2.d["PRESENCE_LINKEDIN_VERSION"] == "202610" and st2.d["PRESENCE_OTHER_THING"] == "y")
P.LOG.unlink(missing_ok=True)
conn = Store(); P.write_accounts([]); P.connect("linkedin", "acct-two", TOKEN, store=conn, http=fake); f3 = P.POSTS / "third.json"
f3.write_text(json.dumps({**good, "account": "acct-two", "text": "A fresh post about patients who message first. What do you do?"}), encoding="utf-8")
def silent(m, u, h, b=None, timeout=30): return 0, {}, ""
out = []
rc = P.post_file(f3, "POST", now, conn, silent, out.append)
ok("review fix: when the platform never answers, the attempt is written BEFORE sending, the words say it may have gone out, and the same text is blocked", rc == 1 and len(P.read_log()) == 1 and P.read_log()[0]["state"] == "attempt" and "may still have gone out" in out[0])
out = []; calls.clear()
ok("review fix: trying the same file again after a silent failure sends nothing and says to look at the account first", P.post_file(f3, "POST", now + dt.timedelta(hours=1), conn, fake, out.append) == 1 and not any("rest/posts" in c[1] for c in calls) and "Look at your account first" in out[0])
out = []; calls.clear()
ok("review fix: a day later the text may be tried again, and a success settles its own attempt so one post is one entry (the old unanswered attempt stays on record)", P.post_file(f3, "POST", now + dt.timedelta(hours=25), conn, fake, out.append) == 0 and [e["state"] for e in P.read_log()] == ["attempt", "posted"])
f4 = P.POSTS / "fourth.json"; f4.write_text(json.dumps({**good, "account": "acct-two", "text": "Yet another different post, about reminders that work. Do you use them?"}), encoding="utf-8")
out = []
ok("review fix: when the platform answers with a refusal, nothing went out, so the attempt is cancelled and the text can be tried again", P.post_file(f4, "POST", now + dt.timedelta(days=2), conn, failing(401), out.append) == 1 and not any(e.get("sha") == P.text_sha("linkedin", "acct-two", g4t) for e in P.read_log()) if (g4t := "Yet another different post, about reminders that work. Do you use them?") else False)
ok("review fix: three real posts a day is still the most, with attempts counted too", "3 a day" in P.rate_problem("linkedin", "acct-two", "zz", now, [{**ent(40), "account": "acct-two", "state": "posted"}, {**ent(90), "account": "acct-two", "state": "attempt"}, {**ent(150), "account": "acct-two", "state": "posted"}]))

# ---- routing and honesty
r = subprocess.run([sys.executable, str(ROOT / "dse.py"), "presence", "publish", "accounts"], capture_output=True, text=True)
ok("python dse.py presence publish ... reaches this module", r.returncode == 0 and "account" in r.stdout.lower())
for cmd in ("carousel", "voice-setup", "graphic", "video"):
    r = subprocess.run([sys.executable, str(ROOT / "dse.py"), "presence", cmd], capture_output=True, text=True)
    ok(f"python dse.py presence {cmd} is a known command", "Unknown command" not in r.stdout)
src = Path(P.__file__).read_text(encoding="utf-8")
urls = sorted(set(__import__("re").findall(r"https?://[A-Za-z0-9./_?=-]+", src)))
ok("the only addresses in the code are LinkedIn's posts and member-id endpoints, Discord's webhook form and documentation text", all(("api.linkedin.com/rest/posts" in u or "api.linkedin.com/v2/userinfo" in u or "linkedin.com/feed/update" in u or "discord" in u) for u in urls))
ok("there is no code for direct messages, comments, follows, likes or reading anyone else's account", not any(w in src.lower() for w in ("/comments", "socialactions", "/messages", "follow(", "/likes", "reactions", "sendmessage", "/members", "/connections")))
ok("the only network calls are one GET to read your own member id and the post itself", src.count("http(\"GET\"") == 1 and src.count("http(\"POST\"") == 2)
ok("secrets are never printed: no print or output call receives a token or webhook variable", not __import__("re").search(r"(out|print)\(.*\b(secret|token|webhook)\b[^)]*\)", "\n".join(l for l in src.splitlines() if "def " not in l and "mask(" not in l and "bool(secret)" not in l and "ask_secret" not in l and "Paste" not in l and "prompt" not in l.lower() and "hidden" not in l)))
ok("no em dash in the file", chr(0x2014) not in src)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
