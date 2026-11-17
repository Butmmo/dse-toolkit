"""Two Herald safety fixes: one send pass at a time on a PC (no double send), and a big first inbox read that never drops the oldest mail.   python tests/test_herald_safety.py
Nothing real is contacted."""
import datetime as dt
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald as H  # noqa: E402
from dse import herald_graph as G  # noqa: E402
from dse import herald_oauth as O  # noqa: E402
from dse import herald_send as S  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp())
H.DATA = tmp / "herald"
H.MAILBOXES = H.DATA / "mailboxes.json"
H.SECRETS = H.DATA / "secrets.dat"
H.STATUS = H.DATA / "status.json"
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 23, 10, 0, tzinfo=UTC)

# ---------------------------------------------------------------- one pass at a time
check("the first pass takes the lock, a second one at the same time does not", S._take_lock(1000) and not S._take_lock(1001) and S.RUN_LOCK().exists())
S._drop_lock()
check("when the first pass is finished the lock is free again", not S.RUN_LOCK().exists() and S._take_lock(2000))
S._drop_lock()
S._take_lock(1000)
check("a lock left behind by a pass that died is ignored after 20 minutes, not before", not S._take_lock(1000 + S.LOCK_STALE_S - 60) and S._take_lock(time.time() + S.LOCK_STALE_S + 60))
S._drop_lock()

calls = []


def fake_pass(api, now, dry, send, poll, out):
    calls.append("outer")
    inner = S.run_pass(None, out=lambda *a: calls.append("said: " + str(a[0])))        # a second pass starting while this one runs
    calls.append(inner)
    return {"sent": 0}


orig = S._run_pass
S._run_pass = fake_pass
outer = S.run_pass(None, out=lambda *a: None)
inner = calls[-1]
check("a second send pass that starts while one is running stops at once, says so, and sends nothing (the periodic runner and a manual 'herald send' can no longer double-send)", outer == {"sent": 0} and inner["held"] == {"another pass is running": 1} and inner["sent"] == 0 and any("already running" in str(c) for c in calls))
check("the lock is released when the pass is over", not S.RUN_LOCK().exists())


def exploding(*a, **k):
    raise RuntimeError("boom")


S._run_pass = exploding
try:
    S.run_pass(None, out=lambda *a: None)
except RuntimeError:
    pass
check("even when a pass crashes the lock is released, so the next one can run", not S.RUN_LOCK().exists())
S._take_lock(time.time())
seen_dry = []
S._run_pass = lambda *a, **k: seen_dry.append("ran") or {"sent": 0}
S.run_pass(None, dry=True, out=lambda *a: None)
check("a dry run (it sends nothing) is never held back by the lock", seen_dry == ["ran"])
S._drop_lock()
S._run_pass = orig


# ---------------------------------------------------------------- a big first inbox read
class Box:
    def __init__(self, n):
        self.n = n

    def login(self, u, p):
        return "OK"

    def select(self, *a, **k):
        return "OK", [b""]

    def search(self, *a):
        return "OK", [b" ".join(str(i).encode() for i in range(1, self.n + 1))]

    def fetch(self, num, spec):
        i = int(num)
        return "OK", [(b"h", f"Message-ID: <m{i}@x>\r\nFrom: lead@x.co\r\n\r\nbody {i}".encode())]

    def logout(self):
        return "BYE", []


M = {"id": "m1", "email": "a@me.com", "username": "a@me.com", "imap_host": "imap.me.com", "imap_port": 993, "provider": "custom"}
O.HOST_GUARD = None
big = S.fetch_new(M, "pw", dt.date(2026, 11, 20), set(), connect=lambda: Box(450))
keys = [k for k, _ in big]
check("a busy inbox is read oldest first, 300 new messages at a time, and the reader says there are more", len(big) == 300 and keys[0] == "<m1@x>" and keys[-1] == "<m300@x>" and big.capped is True)
rest = S.fetch_new(M, "pw", dt.date(2026, 11, 20), set(keys), connect=lambda: Box(450))
check("the next read carries on from where it stopped (the messages already read are skipped) and then says it is finished", [k for k, _ in rest] == [f"<m{i}@x>" for i in range(301, 451)] and rest.capped is False)
small = S.fetch_new(M, "pw", dt.date(2026, 11, 20), set(), connect=lambda: Box(5))
check("a small inbox is read whole and is not capped", len(small) == 5 and small.capped is False)


class Api:
    def __init__(self):
        self.calls = []

    def rpc(self, name, body, tries=3):
        self.calls.append(name)
        return ["lead@x.co"] if name == "hq_herald_lead_emails" else 0


H.save_mailboxes([M])
H.set_secret("m1", "pw") if hasattr(H, "set_secret") else None
secrets = {"m1": "pw"}
state_before = S._state()
batches = [S.Batch([(f"<a{i}>", f"From: lead@x.co\r\nSubject: Re: x\r\n\r\nyes {i}".encode()) for i in range(3)])]
batches[0].capped = True
polled_after_first = {}


def fetcher(m, pw, since, seen):
    return batches.pop(0) if batches else S.Batch()


out = []
S.poll_all(Api(), NOW, secrets, out=out.append, fetch=fetcher)
st = S._state()
check("when a read was capped the mailbox is NOT marked as read up to now, so the older unread mail is not skipped, and the member is told", "m1" not in (st.get("polled") or {}) and any("rest are read on the next pass" in o for o in out))
S.poll_all(Api(), NOW + dt.timedelta(seconds=10), secrets, out=out.append, fetch=fetcher)
check("once everything has been read the mailbox is marked as read and the normal five-minute rhythm starts", "m1" in (S._state().get("polled") or {}))

# ---------------------------------------------------------------- Microsoft Graph reads the same way
G._state["api"], G._state["tokens"] = None, {}


class Http:
    def __init__(self, n):
        self.n = n
        self.urls = []

    def __call__(self, method, url, headers, data=None, timeout=30):
        self.urls.append(url)
        if url.endswith("/herald-oauth-token"):
            return 200, json.dumps({"access_token": "AT", "expires_in": 3600}).encode()
        if "/messages?" in url:
            return 200, json.dumps({"value": [{"id": f"i{i}", "internetMessageId": f"<g{i}@x>"} for i in range(1, self.n + 1)]}).encode()
        return 200, b"From: lead@x.co\r\n\r\nhi"


class FakeApi:
    url, key, token = "https://x.supabase.co", "k", "t" * 40


G._state["api"] = FakeApi()
gb = G.fetch_new({"id": "11111111-1111-4111-8111-111111111111"}, dt.date(2026, 11, 20), set(), http=Http(420))
check("Microsoft Graph reads oldest first, 300 at a time, and says when there are more", len(gb) == 300 and gb[0][0] == "<g1@x>" and gb[-1][0] == "<g300@x>" and gb.capped is True)
h = Http(5)
G._state["tokens"] = {}
G.fetch_new({"id": "11111111-1111-4111-8111-111111111111"}, dt.date(2026, 11, 20), set(), http=h)
check("it asks the inbox for the oldest first", any("receivedDateTime+asc" in u for u in h.urls))


# ---------------------------------------------------------------- answers and warmup mail are journalled (a failed report can never cause a second send)
from dse import herald_warm as W  # noqa: E402

MBX = {"id": "m9", "email": "ada@me.com", "display_name": "Ada", "provider": "custom", "paused": False}
OUT_ITEM = {"id": "o1", "to_email": "lead@x.co", "subject": "Re: Hello", "body": "Thanks!", "lead_status": "new", "mailbox": MBX}


class AnsApi:
    def __init__(self, fail_report=True):
        self.fail_report, self.reports, self.done = fail_report, [], set()

    def rpc(self, name, body, tries=3):
        if name == "hq_herald_outbox_due":
            return [OUT_ITEM] if "o1" not in self.done else []        # the real Citadel stops listing an answer once it has been told it was sent
        if name == "hq_herald_outbox_report":
            if self.fail_report:
                raise RuntimeError("Citadel is down")
            self.reports.append(body["p_results"])
            self.done.update(r["id"] for r in body["p_results"])
        return None


sent_to = []
send_fn = lambda m, pw, msg: sent_to.append(msg["To"])  # noqa: E731
H.DATA.mkdir(parents=True, exist_ok=True)
api = AnsApi(fail_report=True)
said = []
n1 = S.send_answers(api, NOW, {"m9": "pw"}, send=send_fn, out=said.append)
check("an answer is sent once, and when Citadel cannot be told it is written down on this PC instead of being lost", n1 == 1 and sent_to == ["lead@x.co"] and [r["id"] for r in S.journal_load("answers")] == ["o1"] and any("remembered on this PC" in x for x in said))
n2 = S.send_answers(api, NOW + dt.timedelta(seconds=60), {"m9": "pw"}, send=send_fn, out=said.append)
check("the next pass (Citadel still lists the answer as waiting, because it was never told) does NOT send it a second time", n2 == 0 and sent_to == ["lead@x.co"])
api.fail_report = False
n3 = S.send_answers(api, NOW + dt.timedelta(seconds=120), {"m9": "pw"}, send=send_fn, out=said.append)
check("once Citadel is back it is told about the earlier answer, the journal is emptied, and still nothing is sent twice", n3 == 0 and sent_to == ["lead@x.co"] and api.reports and api.reports[0][0]["id"] == "o1" and S.journal_load("answers") == [])
api2 = AnsApi(fail_report=False)
sent_to.clear()
S.send_answers(api2, NOW, {"m9": "pw"}, send=send_fn, out=said.append)
check("when the report works at once the journal is emptied straight away", sent_to == ["lead@x.co"] and S.journal_load("answers") == [] and api2.reports[0][0]["status"] == "sent")
jd = []
S.journal_save("warm", [{"id": "w7", "status": "sent"}])


class WApi:
    def __init__(self, ok):
        self.ok = ok

    def rpc(self, name, body, tries=3):
        if not self.ok:
            raise RuntimeError("down")
        jd.append((name, body))


still = S.journal_flush(WApi(False), "warm", "hq_herald_warm_report", "p_results", out=lambda *a: None)
check("sends that Citadel could not be told about stay on the journal and are named as owed, so they are skipped; once it can be told they are reported and cleared", still == {"w7"} and S.journal_load("warm") == [{"id": "w7", "status": "sent"}] and S.journal_flush(WApi(True), "warm", "hq_herald_warm_report", "p_results", out=lambda *a: None) == set() and S.journal_load("warm") == [] and jd[0][0] == "hq_herald_warm_report")
warm_src = (ROOT / "dse" / "herald_warm.py").read_text(encoding="utf-8")
check("the warmup sends and warmup answers use the same journal: flushed first, skipped while owed, written down before Citadel is told, cleared when it has been", warm_src.count("S.journal_flush(") == 2 and warm_src.count("S.journal_save(") == 4 and warm_src.count("in owed_ids") + warm_src.count("not in owed_ids") >= 2)
check("no em dash", DASH not in (ROOT / "dse" / "herald_send.py").read_text(encoding="utf-8") + (ROOT / "dse" / "herald_graph.py").read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8"))
shutil.rmtree(tmp, ignore_errors=True)
print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
