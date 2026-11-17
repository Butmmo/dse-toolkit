"""Tests for Herald phase 6: the warmup ramp and the opt-in exchange.   python tests/test_herald_warm.py
Nothing real is contacted: the mail servers, the mailboxes and Citadel are replaced by fakes."""
import datetime as dt
import json
import shutil
import smtplib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald as H  # noqa: E402
from dse import herald_send as S  # noqa: E402
from dse import herald_warm as W  # noqa: E402

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
MON_10 = dt.datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
PW = "pw-SECRET-xyz"


def mbox(mid="m1", **o):
    return {"id": mid, "email": f"{mid}@me.com", "display_name": "Ada Obi", "username": f"{mid}@me.com", "provider": "custom", "smtp_host": "smtp.me.com", "smtp_port": 465, "smtp_security": "ssl",
            "imap_host": "imap.me.com", "imap_port": 993, "daily_limit": 30, "min_gap_seconds": 60, "timezone": "UTC", "window_start": "09:00", "window_end": "17:00",
            "send_days": ["mon", "tue", "wed", "thu", "fri"], "paused": False, **o}


class Api:
    def __init__(self, **replies):
        self.replies, self.calls = replies, []

    def rpc(self, name, args):
        self.calls.append((name, args))
        r = self.replies.get(name)
        return r(args) if callable(r) else r


class Box:
    """A fake IMAP connection holding messages by folder."""
    def __init__(self, folders):
        self.folders, self.sel, self.log = {k: dict(v) for k, v in folders.items()}, None, []

    def select(self, name):
        n = name.strip('"')
        if n not in self.folders:
            return ("NO", [b""])
        self.sel = n
        return ("OK", [b"1"])

    def search(self, _c, *crit):
        mid = crit[2]
        hits = [str(k).encode() for k, v in self.folders[self.sel].items() if v == mid]
        return ("OK", [b" ".join(hits)])

    def store(self, num, op, flag):
        self.log.append(("store", self.sel, num.decode(), flag))
        return ("OK", [b""])

    def copy(self, num, dest):
        self.folders[dest][int(num)] = self.folders[self.sel][int(num)]
        self.log.append(("copy", self.sel, num.decode(), dest))
        return ("OK", [b""])

    def expunge(self):
        self.folders[self.sel] = {k: v for k, v in self.folders[self.sel].items() if ("store", self.sel, str(k), "\\Deleted") not in self.log}
        return ("OK", [b""])

    def logout(self):
        pass


try:
    # ---- the ramp
    check("the ramp is 5 on day one and 2 more each day", [W.ramp(d) for d in (0, 1, 2, 7)] == [5, 7, 9, 19] and W.ramp(-3) == 5)
    check("the ramp never raises a limit and applies only when warmup is on", W.effective_limit(30, {"warmup": True, "day": 0}) == 5 and W.effective_limit(6, {"warmup": True, "day": 5}) == 6
          and W.effective_limit(30, {"warmup": False, "day": 0}) == 30 and W.effective_limit(30, None) == 30 and W.effective_limit(30, {"warmup": True, "day": 40}) == 30)
    due = [{"mailbox": mbox("a")}, {"mailbox": mbox("a")}, {"mailbox": mbox("b", daily_limit=3)}]
    n = W.apply_ramp(due, {"a": {"warmup": True, "day": 1}, "b": {"warmup": True, "day": 0}})
    check("apply_ramp lowers each mailbox's limit and counts the held ones", n == 1 and due[0]["mailbox"]["daily_limit"] == 7 and due[2]["mailbox"]["daily_limit"] == 3)
    check("with no plan from Citadel nothing is limited", W.get_plan(Api(hq_herald_warm_plan=1)) == {} and W.effective_limit(30, W.get_plan(Api()).get("a")) == 30)

    class Boom:
        def rpc(self, *a):
            raise RuntimeError("function does not exist")
    check("an old Citadel without the warmup file does not break sending", W.get_plan(Boom()) == {} and W.answer_warm(Boom(), MON_10, {}) == 0)

    # the sender uses the ramp: day-0 mailbox with 5 sent today may not send a sixth
    ok6 = S.decide({"mailbox": {**mbox(), "daily_limit": W.effective_limit(30, {"warmup": True, "day": 0})}, "lead_status": "new", "attempts": 0, "scheduled_day": "2026-11-23", "scheduled_time": "09:00", "step": 1}, MON_10, {"m1": 5}, {}, set(), True)
    check("a warming mailbox stops at the ramp even with a higher limit", not ok6[0] and "daily limit" in ok6[1])

    # ---- sending exchange mail
    H.DATA.mkdir(parents=True, exist_ok=True)
    H.MAILBOXES.write_text(json.dumps([mbox("m1"), mbox("m2"), mbox("m3", paused=True)]), encoding="utf-8")
    plan = {"m1": {"warm_pool": True, "warmup": True, "day": 3}, "m2": {"warm_pool": False}, "m3": {"warm_pool": True}}
    secrets = {"m1": PW, "m2": PW, "m3": PW}
    sent = []
    job = {"id": "j1", "to_email": "partner@elsewhere.org", "subject": "Quick check-in", "body": "Hi\n\n(A short Herald warmup message between members.)"}
    api = Api(hq_herald_warm_next=job, hq_herald_warm_report=1)
    n = W.send_warm(api, MON_10, plan, secrets, lambda m, pw, ms: sent.append((m["id"], ms)), rng=lambda: 1.0)
    check("only opted-in, unpaused mailboxes with a password send exchange mail", n == 1 and [x[0] for x in sent] == ["m1"] and [c[1].get("p_mailbox") for c in api.calls if c[0] == "hq_herald_warm_next"] == ["m1"])
    ms = sent[0][1]
    check("the message is exactly Citadel's words, to the partner, with its own Message-ID", ms["To"] == "partner@elsewhere.org" and ms["Subject"] == "Quick check-in" and "short Herald warmup message" in ms.get_content() and ms["Message-ID"].startswith("<"))
    rep = [c for c in api.calls if c[0] == "hq_herald_warm_report"][0][1]["p_results"]
    check("the result reports the id and Message-ID, never the password", rep[0]["id"] == "j1" and rep[0]["status"] == "sent" and rep[0]["message_id"] == ms["Message-ID"] and PW not in json.dumps(rep))
    api = Api(hq_herald_warm_next=job, hq_herald_warm_report=1)
    check("most passes send nothing (a steady beat looks automated)", W.send_warm(api, MON_10, plan, secrets, lambda *a: None, rng=lambda: 0.1) == 0 and not [c for c in api.calls if c[0] == "hq_herald_warm_next"])
    api = Api(hq_herald_warm_next=job, hq_herald_warm_report=1)
    check("nothing is sent outside the mailbox's window or on a day off", W.send_warm(api, MON_10.replace(hour=20), plan, secrets, lambda *a: None, rng=lambda: 1.0) == 0 and W.send_warm(api, dt.datetime(2026, 11, 22, 10, tzinfo=UTC), plan, secrets, lambda *a: None, rng=lambda: 1.0) == 0)
    api = Api(hq_herald_warm_next=None, hq_herald_warm_report=1)
    check("when Citadel has no partner or the cap is reached, nothing is sent", W.send_warm(api, MON_10, plan, secrets, lambda *a: None, rng=lambda: 1.0) == 0)

    def bad(m, pw, ms):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials " + PW.encode())
    out = []
    api = Api(hq_herald_warm_next=job, hq_herald_warm_report=1)
    check("a failed send is reported as failed, and the password never reaches the screen", W.send_warm(api, MON_10, plan, secrets, bad, rng=lambda: 1.0, out=out.append) == 0 and [c for c in api.calls if c[0] == "hq_herald_warm_report"][0][1]["p_results"][0]["status"] == "failed" and PW not in " ".join(out))

    # ---- finding, rescuing and answering
    MID = "<abc123@partner.org>"
    check("a message in the inbox is found and marked read, not moved", (lambda b: (W.find_and_rescue(b, MID), b.log))(Box({"INBOX": {1: MID}, "Spam": {}}))[0] == (True, False))
    b = Box({"INBOX": {}, "[Gmail]/Spam": {7: MID, 8: "<other@x>"}})
    check("a message in spam is moved to the inbox and only that one", W.find_and_rescue(b, MID) == (True, True) and 7 in b.folders["INBOX"] and 8 not in b.folders["INBOX"] and 8 in b.folders["[Gmail]/Spam"])
    check("a message that is nowhere is not found", W.find_and_rescue(Box({"INBOX": {}, "Spam": {}}), MID) == (False, False))
    b = Box({"INBOX": {1: "<x@y>"}})
    check("a bad Message-ID is refused before it touches the mailbox", W.find_and_rescue(b, "<a b>") == (False, False) and W.find_and_rescue(b, 'x" OR ALL') == (False, False) and not b.log)

    inbox_item = {"id": "w1", "to_mailbox_id": "m1", "from_email": "partner@elsewhere.org", "subject": "Quick check-in", "message_id": MID, "reply_body": "Thanks for the note.", "age_minutes": 30}
    replies = []
    api = Api(hq_herald_warm_inbox=[inbox_item], hq_herald_warm_report=1)
    n = W.answer_warm(api, MON_10, secrets, lambda m, pw, ms: replies.append(ms), connect=lambda m, pw: Box({"INBOX": {}, "Spam": {3: MID}}))
    r = replies[0]
    check("a message found in spam is rescued, answered in the same thread and reported", n == 1 and r["To"] == "partner@elsewhere.org" and r["Subject"] == "Re: Quick check-in" and r["In-Reply-To"] == MID and r.get_content().startswith("Thanks"))
    res = [c for c in api.calls if c[0] == "hq_herald_warm_report"][0][1]["p_results"][0]
    check("the report says replied and rescued", res["status"] == "replied" and res["rescued"] is True and res["reply_message_id"] == r["Message-ID"])
    replies.clear()
    api = Api(hq_herald_warm_inbox=[{**inbox_item, "age_minutes": 2}], hq_herald_warm_report=1)
    check("a message that arrived a minute ago is not answered yet", W.answer_warm(api, MON_10, secrets, lambda *a: replies.append(1), connect=lambda m, pw: Box({"INBOX": {1: MID}})) == 0 and not replies)
    api = Api(hq_herald_warm_inbox=[{**inbox_item, "age_minutes": 60}], hq_herald_warm_report=1)
    check("a message not found yet is left for the next pass", W.answer_warm(api, MON_10, secrets, lambda *a: replies.append(1), connect=lambda m, pw: Box({"INBOX": {}, "Spam": {}})) == 0 and not [c for c in api.calls if c[0] == "hq_herald_warm_report"])
    api = Api(hq_herald_warm_inbox=[{**inbox_item, "age_minutes": 60 * 30}], hq_herald_warm_report=1)
    W.answer_warm(api, MON_10, secrets, lambda *a: None, connect=lambda m, pw: Box({"INBOX": {}, "Spam": {}}))
    check("a message still missing after a day is reported missing (a delivery warning)", [c for c in api.calls if c[0] == "hq_herald_warm_report"][0][1]["p_results"][0]["status"] == "missing")
    api = Api(hq_herald_warm_inbox=[{**inbox_item, "to_mailbox_id": "m3"}], hq_herald_warm_report=1)
    check("a paused mailbox answers nothing", W.answer_warm(api, MON_10, secrets, lambda *a: replies.append(1), connect=lambda m, pw: Box({"INBOX": {1: MID}})) == 0)

    # ---- the pass wires it in, and the PAUSE switch holds it
    api = Api(hq_herald_warm_plan={"m1": {"warm_pool": False, "warmup": True, "day": 0}}, hq_herald_outbox_due=[], hq_herald_due=[], hq_herald_recent_sent=[], hq_herald_warm_inbox=[])
    s = S.run_pass(api, now=MON_10, send=lambda *a: None, poll=False, out=lambda *a: None)
    check("a normal pass asks for the ramp and reports the warmup count", s["warm"] == 0 and any(c[0] == "hq_herald_warm_plan" for c in api.calls))
    H.DATA.mkdir(parents=True, exist_ok=True)
    (H.DATA / "PAUSE").write_text("x")
    api = Api()
    S.run_pass(api, now=MON_10, send=lambda *a: None, poll=False, out=lambda *a: None)
    check("the pause switch stops the exchange too", not api.calls)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- wiring and honesty
src = (ROOT / "dse" / "herald_warm.py").read_text(encoding="utf-8")
sender = (ROOT / "dse" / "herald_send.py").read_text(encoding="utf-8")
check("the sender itself still never moves or deletes mail", ".store(" not in sender and ".expunge(" not in sender and ".copy(" not in sender)
check("the exchange touches only a message it was told the exact Message-ID of", 'crit = ("HEADER", "Message-ID", mid)' in src and src.count(".search(") == 3 and "ALL" not in src.replace("SMALL", ""))
check("the exchange writes no words of its own", "subject" in src and "bodies" not in src and "random.choice" not in src)
check("no em dash", DASH not in src + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
