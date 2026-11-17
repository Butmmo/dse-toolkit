"""Tests for Herald phase 3: the sending engine, replies and bounces.   python tests/test_herald_send.py
Nothing real is contacted: the mail servers and Citadel are replaced by fakes."""
import datetime as dt
import json
import shutil
import smtplib
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald as H  # noqa: E402
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

PW = "app-pass-SECRET-123"
UTC = dt.timezone.utc
MON_10 = dt.datetime(2026, 11, 23, 10, 0, tzinfo=UTC)          # a Monday, inside a 09:00 to 17:00 window


def mbox(mid="m1", **o):
    return {"id": mid, "email": f"{mid}@me.com", "display_name": "Ada Obi", "username": f"{mid}@me.com", "provider": "custom", "smtp_host": "smtp.me.com", "smtp_port": 465, "smtp_security": "ssl",
            "daily_limit": 5, "min_gap_seconds": 60, "timezone": "UTC", "window_start": "09:00", "window_end": "17:00", "send_days": ["mon", "tue", "wed", "thu", "fri"], "paused": False, **o}


def item(i=1, step=1, day="2026-11-23", time="09:00", mid="m1", **o):
    return {"id": f"s{i}", "campaign_id": "c1", "lead_id": f"l{i}", "step": step, "to_email": f"lead{i}@x.co", "subject": f"Hello {i}", "body": f"Hi, body {i}\n\nunsubscribe: https://x/unsubscribe/tok{i}",
            "scheduled_day": day, "scheduled_time": time, "attempts": 0, "unsub_token": f"tok{i}", "lead_status": "new", "delay_days": 3 if step > 1 else 0, "prev_sent_at": None, "prev_message_id": None,
            "first_message_id": None, "prev_open": False, "mailbox": mbox(mid), **o}


try:
    # ---- the decision, rule by rule
    ok = lambda it, now=MON_10, today=None, last=None, used=None, pw=True: S.decide(it, now, today or {}, last or {}, used or set(), pw)  # noqa: E731
    check("a due email inside the window on a send day may go", ok(item())[0])
    check("a lead who replied, bounced or unsubscribed is never sent to", not ok(item(lead_status="replied"))[0] and not ok(item(lead_status="unsubscribed"))[0] and not ok(item(lead_status="bounced"))[0])
    check("no password on this PC means no sending", ok(item(), pw=False)[1].startswith("no password"))
    check("a paused mailbox sends nothing", not ok(item(mid="m1"))[0] is False and not S.decide({**item(), "mailbox": mbox(paused=True)}, MON_10, {}, {}, set(), True)[0])
    check("a day that is not planned yet is held", not ok(item(day="2026-11-24"))[0] and ok(item(day="2026-11-22"))[0])
    check("a planned time later today is held, but a past day catches up at any time in the window", not ok(item(time="11:00"))[0] and ok(item(day="2026-11-20", time="16:30"))[0])
    check("outside the window is held (before, at the end, after)", not ok(item(), now=MON_10.replace(hour=8))[0] and not ok(item(), now=MON_10.replace(hour=17))[0] and not ok(item(), now=MON_10.replace(hour=21))[0] and ok(item(), now=MON_10.replace(hour=16, minute=59))[0])
    sun = dt.datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
    check("a day that is not a send day is held", not ok(item(day="2026-11-20"), now=sun)[0] and "send day" in ok(item(day="2026-11-20"), now=sun)[1])
    lagos = dt.timezone(dt.timedelta(hours=1))
    real = S.tz_of
    S.tz_of = lambda name: lagos if name == "Africa/Lagos" else real(name)
    early = dt.datetime(2026, 11, 23, 7, 30, tzinfo=UTC)          # 08:30 in Lagos: before the window; 08:30 UTC is also before it
    check("the window is read in the campaign's own time zone", not S.decide({**item(), "mailbox": mbox(timezone="Africa/Lagos")}, early, {}, {}, set(), True)[0] and S.decide({**item(), "mailbox": mbox(timezone="Africa/Lagos")}, early.replace(hour=8, minute=30), {}, {}, set(), True)[0])
    S.tz_of = real
    S.tz_of = lambda name: None if name == "Nowhere/Land" else real(name)
    check("a time zone this PC has no data for holds the email and says how to fix it, never guesses", "pip install tzdata" in S.decide({**item(), "mailbox": mbox(timezone="Nowhere/Land")}, MON_10, {}, {}, set(), True)[1])
    S.tz_of = real
    check("the daily limit is enforced from what was really sent today", ok(item(), today={"m1": 4})[0] and not ok(item(), today={"m1": 5})[0] and "daily limit" in ok(item(), today={"m1": 5})[1])
    check("the gap since the mailbox's last email is enforced", not ok(item(), last={"m1": MON_10 - dt.timedelta(seconds=30)})[0] and ok(item(), last={"m1": MON_10 - dt.timedelta(seconds=61)})[0])
    check("a mailbox sends at most one email per pass", not ok(item(), used={"m1"})[0])
    check("a follow-up waits for the previous step and for its delay", not ok(item(step=2, prev_open=True))[0] and not ok(item(step=2, prev_sent_at="2026-11-21T10:00:00Z"))[0] and ok(item(step=2, prev_sent_at="2026-11-20T10:00:00Z"))[0])
    check("an email that has failed three times is left alone", not ok(item(attempts=3))[0])

    # ---- the message
    msg = S.build_message(item(2, step=2, prev_message_id="<p@x>", first_message_id="<f@x>"), MON_10)
    check("the message has the sender's name, the unsubscribe headers and the thread headers for a follow-up", "Ada Obi" in msg["From"] and msg["To"] == "lead2@x.co" and "tok2" in msg["List-Unsubscribe"] and "mailto:m1@me.com" in msg["List-Unsubscribe"] and msg["In-Reply-To"] == "<p@x>" and "<f@x>" in msg["References"] and msg["Message-ID"].endswith("@me.com>"))
    check("the first email has no thread headers, and the body is plain text as written", S.build_message(item(1), MON_10)["In-Reply-To"] is None and "Hi, body 1" in S.build_message(item(1), MON_10).get_content())
    check("the password is nowhere in the message", PW not in str(msg))

    # ---- delivering one email
    sent = []
    r = S.deliver(item(), PW, MON_10, send=lambda m, pw, ms: sent.append((pw, ms["To"])))
    check("a sent email reports its message id and time, and used the password only to send", r["status"] == "sent" and r["message_id"].startswith("<") and sent == [(PW, "lead1@x.co")] and PW not in json.dumps(r))

    def boom(exc):
        def f(m, pw, ms):
            raise exc
        return f
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPAuthenticationError(535, b"bad")))
    check("a refused login holds the email without counting an attempt and marks the mailbox", r["status"] == "retry" and r["count_attempt"] is False and r.get("auth") is True)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPRecipientsRefused({"lead1@x.co": (550, b"no such user")})))
    check("an address that does not exist is a failure marked as a bounce", r["status"] == "failed" and r["bounced"] is True)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPResponseException(554, b"rejected as spam")))
    check("another permanent refusal fails the email but is not a bounce", r["status"] == "failed" and r["bounced"] is False)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPResponseException(451, b"try later")))
    check("a temporary server error is retried and counts an attempt", r["status"] == "retry" and r["count_attempt"] is True)
    r = S.deliver(item(), PW, MON_10, send=boom(socket.timeout("timed out")))
    check("a network problem is retried without using up attempts", r["status"] == "retry" and r["count_attempt"] is False)
    r = S.deliver(item(), PW, MON_10, send=boom(RuntimeError(f"oops {PW}")) if False else boom(smtplib.SMTPException(f"login {PW} failed")))
    check("a password an error message echoes is hidden", PW not in json.dumps(r))

    # ---- one whole pass
    class FakeApi:
        def __init__(self, due, recent=None, leads=None):
            self.due, self.recent, self.leads, self.calls = due, recent or [], leads or [], []

        def rpc(self, name, body):
            self.calls.append((name, body))
            return {"hq_herald_due": self.due, "hq_herald_recent_sent": self.recent, "hq_herald_lead_emails": self.leads}.get(name, 1)

    H.set_secret("m1", PW)
    H.set_secret("m2", PW)
    out = []
    sends = []
    due = [item(1, mid="m1"), item(2, mid="m1"), item(3, mid="m2"), item(4, mid="m2", day="2026-11-24"), item(5, mid="m3")]
    api = FakeApi(due)
    s = S.run_pass(api, now=MON_10, send=lambda m, pw, ms: sends.append(ms["To"]), poll=False, out=out.append)
    check("one email per mailbox per pass; not-yet-due and no-password ones are held with reasons", s["sent"] == 2 and sends == ["lead1@x.co", "lead3@x.co"] and s["held"].get("this mailbox already sent this pass") == 1 and s["held"].get("not due yet") == 1 and any("no password" in k for k in s["held"]))
    rep = [c for c in api.calls if c[0] == "hq_herald_report"]
    check("the results go to Citadel, without any password", len(rep) == 1 and len(rep[0][1]["p_results"]) == 2 and PW not in json.dumps(api.calls) and all(r["status"] == "sent" for r in rep[0][1]["p_results"]))
    sends.clear()
    s = S.run_pass(FakeApi(due), now=MON_10, dry=True, send=lambda m, pw, ms: sends.append(1), poll=False, out=out.append)
    check("a dry run sends and reports nothing, and says what would go", sends == [] and any("WOULD SEND" in o for o in out) and not [c for c in FakeApi(due).calls])
    recent = [{"mailbox_id": "m1", "sent_at": (MON_10 - dt.timedelta(minutes=k)).isoformat()} for k in range(2, 7)]
    sends.clear()
    s = S.run_pass(FakeApi([item(1, mid="m1")], recent), now=MON_10, send=lambda m, pw, ms: sends.append(1), poll=False, out=out.append)
    check("a mailbox that already sent its daily limit today sends no more", sends == [] and any("daily limit" in k for k in s["held"]))
    S.pause()
    s = S.run_pass(FakeApi(due), now=MON_10, send=lambda m, pw, ms: sends.append(1), poll=False, out=out.append)
    check("the stop switch pauses everything, and resume turns it on again", s["paused"] and sends == [] and "paused" in S.pause() and "on again" in S.resume() and not S.PAUSE().exists())
    bad_api = FakeApi([item(1, mid="m1"), item(2, mid="m1", day="2026-11-22")])
    s = S.run_pass(bad_api, now=MON_10, send=lambda m, pw, ms: (_ for _ in ()).throw(smtplib.SMTPAuthenticationError(535, b"x")), poll=False, out=out.append)
    check("a mailbox whose login is refused is skipped for the rest of the pass and its email stays scheduled", s["sent"] == 0 and [c for c in bad_api.calls if c[0] == "hq_herald_report"][0][1]["p_results"][0]["status"] == "retry")
    check("the log holds what happened but not the message body or the password", PW not in S.SENDLOG().read_text(encoding="utf-8") and "body 1" not in S.SENDLOG().read_text(encoding="utf-8") and "lead1@x.co" in S.SENDLOG().read_text(encoding="utf-8"))

    # ---- replies, bounces and unsubscribe requests
    leads = {"ann@acme.com", "bob@x.co"}

    def raw(frm, subject, body, extra=""):
        return f"From: {frm}\r\nTo: me@me.com\r\nSubject: {subject}\r\nDate: Mon, 23 Nov 2026 10:00:00 +0000\r\nMessage-ID: <{abs(hash((frm, subject, body)))}@x>\r\n{extra}\r\n{body}".encode()
    ev = S.classify(raw("Ann <ann@acme.com>", "Re: Hello", "Yes, interested. Call me tomorrow."), leads)
    check("a reply from one of your leads is a reply, with a short snippet", ev and ev["kind"] == "reply" and ev["from_email"] == "ann@acme.com" and "interested" in ev["snippet"])
    check("'stop' or 'unsubscribe' as the reply is an unsubscribe request", S.classify(raw("bob@x.co", "Re: Hello", "Please unsubscribe me"), leads)["kind"] == "unsubscribe" and S.classify(raw("bob@x.co", "STOP", "thanks"), leads)["kind"] == "unsubscribe")
    check("mail from someone who is not your lead is ignored", S.classify(raw("friend@home.com", "Lunch?", "hi"), leads) is None)
    check("out-of-office and other automatic replies are ignored, so the sequence goes on", S.classify(raw("ann@acme.com", "Automatic reply: Hello", "I am away"), leads) is None and S.classify(raw("ann@acme.com", "Re: Hello", "away", "Auto-Submitted: auto-replied\r\n"), leads) is None and S.classify(raw("ann@acme.com", "Re: Hello", "away", "Precedence: auto_reply\r\n"), leads) is None)
    bn = S.classify(raw("MAILER-DAEMON@mail.me.com", "Undelivered Mail Returned to Sender", "Final-Recipient: rfc822; bob@x.co\nAction: failed\nStatus: 5.1.1 user unknown"), leads)
    check("a bounce is matched to the lead whose address failed", bn and bn["kind"] == "bounce" and bn["from_email"] == "bob@x.co")
    check("a bounce about an address that is not yours is ignored", S.classify(raw("postmaster@x.com", "Undeliverable", "failed: stranger@else.com"), leads) is None)

    # ---- reading the inboxes
    polls = []

    def fake_fetch(m, pw, since, seen):
        polls.append((m["id"], pw))
        return [(f"<k{m['id']}>", raw("ann@acme.com", "Re: Hello", "Yes please"))]
    H.save_mailboxes([{**mbox("m1")}, {**mbox("m2")}, {**mbox("m3")}])
    api = FakeApi([], leads=["Ann@Acme.com"])
    n = S.poll_all(api, MON_10, H._read_secrets(), out=out.append, fetch=fake_fetch)
    ev_calls = [c for c in api.calls if c[0] == "hq_herald_events"]
    check("each mailbox with a password is read, and only your leads' mail is reported", [p[0] for p in polls] == ["m1", "m2"] and len(ev_calls) == 1 and len(ev_calls[0][1]["p_events"]) == 2 and ev_calls[0][1]["p_events"][0]["kind"] == "reply" and PW not in json.dumps(api.calls))
    polls.clear()
    S.poll_all(FakeApi([], leads=["ann@acme.com"]), MON_10 + dt.timedelta(seconds=60), H._read_secrets(), out=out.append, fetch=fake_fetch)
    check("a mailbox is not read again until five minutes have passed", polls == [])
    S.poll_all(FakeApi([], leads=["ann@acme.com"]), MON_10 + dt.timedelta(seconds=400), H._read_secrets(), out=out.append, fetch=fake_fetch)
    check("after five minutes it is read again, and a message already seen is not reported twice", len(polls) == 2)
    api3 = FakeApi([], leads=["ann@acme.com"])
    seen_fetch = lambda m, pw, since, seen: [(k, r) for k, r in fake_fetch(m, pw, since, seen) if k not in seen]  # noqa: E731
    S.poll_all(api3, MON_10 + dt.timedelta(seconds=900), H._read_secrets(), out=out.append, fetch=seen_fetch)
    check("seen messages are remembered", not [c for c in api3.calls if c[0] == "hq_herald_events"])
    check("a mailbox that cannot be read is reported plainly and does not stop the others", (lambda o: any("could not read" in x for x in o))((lambda o: (S.poll_all(FakeApi([], leads=["a@b.co"]), MON_10 + dt.timedelta(seconds=2000), H._read_secrets(), out=o.append, fetch=lambda *a: (_ for _ in ()).throw(ConnectionRefusedError("refused"))), o)[1])([])))

    # ---- the test email
    sent_t = []
    check("a test email needs a password and a real address, then sends exactly one", (lambda: (lambda r: r.startswith("Sent one test email"))(S.send_test("m1@me.com", "me@home.com", send=lambda m, pw, ms: sent_t.append(ms["To"]))))() and sent_t == ["me@home.com"])
    for args in (("nobody@x.co", "a@b.co"), ("m1@me.com", "not-an-address")):
        try:
            S.send_test(*args, send=lambda *a: None)
            refused = False
        except ValueError:
            refused = True
        check(f"a test email is refused for {args[0]} to {args[1]}", refused)
    try:
        S.send_test("m1@me.com", "me@home.com", send=lambda m, pw, ms: (_ for _ in ()).throw(smtplib.SMTPException(f"bad {PW}")))
        msg_t = ""
    except ValueError as e:
        msg_t = str(e)
    check("a failed test says why and never shows the password", "not sent" in msg_t and PW not in msg_t)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- wiring
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
check("the sending tools are in the catalog, and the sender runs every minute", {"dse.herald_sendstatus", "dse.herald_sendtest", "dse.herald_pause", "dse.herald_resume"} <= set(cat["tools"]) and any(x.get("script") == "bridge/herald_send.py" and x.get("every_s") == 60 for x in cat["periodic"]))
check("the test-email tool asks for no password", all(f["name"] != "password" for f in cat["tools"]["dse.herald_sendtest"]["fields"]))
src = (ROOT / "dse" / "herald_send.py").read_text(encoding="utf-8")
check("the engine never marks mail read (BODY.PEEK) and never deletes or moves mail", "BODY.PEEK" in src and "readonly=True" in src and ".store(" not in src and ".expunge(" not in src and ".copy(" not in src)
check("only a started campaign is sent: the engine asks Citadel only for running campaigns' due emails", 'api.rpc("hq_herald_due"' in src)
check("no em dash", DASH not in src + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
