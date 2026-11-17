"""Tests for the fixes that came out of the independent Herald review (17 Nov 2026).   python tests/test_herald_review.py
Nothing real is contacted: mail servers, Citadel and Google are fakes."""
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
PW = "app-pass-SECRET-123"
REAL_ACCESS = O.access_token                     # kept: a later test replaces O.access_token with a fake
UTC = dt.timezone.utc
MON_10 = dt.datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def mbox(mid="m1", **o):
    return {"id": mid, "email": f"{mid}@me.com", "display_name": "Ada Obi", "username": f"{mid}@me.com", "provider": "custom", "smtp_host": "smtp.me.com", "smtp_port": 465, "smtp_security": "ssl",
            "daily_limit": 5, "min_gap_seconds": 60, "timezone": "UTC", "window_start": "09:00", "window_end": "17:00", "send_days": ["mon", "tue", "wed", "thu", "fri"], "paused": False, **o}


def item(i=1, mid="m1", **o):
    return {"id": f"s{i}", "campaign_id": "c1", "lead_id": f"l{i}", "step": 1, "to_email": f"lead{i}@x.co", "subject": f"Hello {i}", "body": f"Hi {i}\n\nunsubscribe: https://x/unsubscribe/tok{i}",
            "scheduled_day": "2026-11-23", "scheduled_time": "09:00", "attempts": 0, "unsub_token": f"tok{i}", "lead_status": "new", "delay_days": 0, "prev_sent_at": None, "prev_message_id": None,
            "first_message_id": None, "prev_open": False, "mailbox": mbox(mid), **o}


def boom(e):
    def f(*a, **k):
        raise e
    return f


try:
    # ---- what a server's refusal means: only a refusal of the ADDRESS is a bounce
    unknown = smtplib.SMTPRecipientsRefused({"lead1@x.co": (550, b"5.1.1 The email account that you tried to reach does not exist")})
    quota = smtplib.SMTPRecipientsRefused({"lead1@x.co": (550, b"5.4.5 Daily user sending quota exceeded")})
    blocked = smtplib.SMTPRecipientsRefused({"lead1@x.co": (550, b"5.7.1 Message blocked as spam")})
    r = S.deliver(item(), PW, MON_10, send=boom(unknown))
    check("an address that does not exist is a bounce", r["status"] == "failed" and r["bounced"] is True)
    r = S.deliver(item(), PW, MON_10, send=boom(quota))
    check("a daily-quota refusal is NOT a bounce: the lead is kept and the email is tried again later", r["status"] == "retry" and r["count_attempt"] is True and not r.get("bounced"))
    r = S.deliver(item(), PW, MON_10, send=boom(blocked))
    check("a spam or policy block is NOT a bounce either", r["status"] == "retry" and not r.get("bounced"))
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPRecipientsRefused({"lead1@x.co": (452, b"4.2.2 mailbox full")})))
    check("a temporary 4xx refusal of the address is tried again, not lost", r["status"] == "retry" and r["count_attempt"] is True)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPSenderRefused(553, b"5.7.1 sender not allowed", "m1@me.com")))
    check("a refusal of the SENDER (553) never marks the lead bounced", r["status"] == "failed" and r["bounced"] is False)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPDataError(550, b"5.7.0 content rejected")))
    check("a content rejection (550 after DATA) never marks the lead bounced", r["status"] == "failed" and r["bounced"] is False)

    # ---- a bad header fails one email, not the pass
    bad = item(2, mailbox=mbox("m1", display_name="Ada\r\nBcc: spy@evil.co"))
    r = S.deliver(bad, PW, MON_10, send=lambda *a: (_ for _ in ()).throw(AssertionError("must not send")))
    check("a mailbox name with a line break makes that one email fail with a clear reason, and nothing is sent", r["status"] == "failed" and r["bounced"] is False and "Citadel" in r["error"])

    # ---- a send is never repeated because the report failed
    class Api:
        def __init__(self, due, fail_report=False):
            self.due, self.fail, self.reports = due, fail_report, []

        def rpc(self, name, body):
            if name == "hq_herald_report":
                if self.fail:
                    raise OSError("no internet")
                self.reports.append(body["p_results"])
                return 1
            return {"hq_herald_due": self.due, "hq_herald_recent_sent": [], "hq_herald_lead_emails": [], "hq_herald_outbox_due": []}.get(name, 1)
    H.set_secret("m1", PW)
    sends, out = [], []
    api1 = Api([item(1)], fail_report=True)
    s1 = S.run_pass(api1, now=MON_10, send=lambda m, pw, ms: sends.append(ms["To"]), poll=False, out=out.append)
    check("the email is sent, the report fails, and the pass still finishes and remembers it on this PC", s1["sent"] == 1 and sends == ["lead1@x.co"] and len(S._journal_load()) == 1)
    api2 = Api([item(1)], fail_report=True)
    s2 = S.run_pass(api2, now=MON_10 + dt.timedelta(minutes=1), send=lambda m, pw, ms: sends.append(ms["To"]), poll=False, out=out.append)
    check("while Citadel still cannot be told, the same email (still listed as due) is held and NOT sent again", sends == ["lead1@x.co"] and s2["sent"] == 0 and s2["held"].get("already sent, waiting to be reported") == 1)
    api2b = Api([])
    S.run_pass(api2b, now=MON_10 + dt.timedelta(minutes=2), send=lambda m, pw, ms: sends.append("x"), poll=False, out=out.append)
    check("as soon as Citadel can be told, the earlier send is reported first and the note is cleared", len(api2b.reports) == 1 and api2b.reports[0][0]["id"] == "s1" and api2b.reports[0][0]["status"] == "sent" and S._journal_load() == [] and sends == ["lead1@x.co"])
    check("the saved note holds no password and no message text", PW not in json.dumps(api1.reports) and "Hi 1" not in json.dumps(S._journal_load()))
    api3 = Api([item(1)], fail_report=True)
    sends3 = []
    S.run_pass(api3, now=MON_10, send=lambda m, pw, ms: sends3.append(1), poll=False, out=out.append)
    api4 = Api([item(2, mid="m1")], fail_report=True)
    s4 = S.run_pass(api4, now=MON_10 + dt.timedelta(minutes=2), send=lambda m, pw, ms: sends3.append(2), poll=False, out=out.append)
    check("a send that Citadel does not know about yet still counts toward the mailbox's gap and daily limit", s4["sent"] == 0 and s4["held"], str(s4["held"]))
    S._journal_save([])

    # ---- the saved passwords file is never wiped by a failed read
    H.SECRETS.unlink(missing_ok=True)
    H.set_secret("a", "pw-a-123456")
    H.set_secret("b", "pw-b-123456")
    good = H.SECRETS.read_bytes()
    H.SECRETS.unlink()
    H.SECRETS.mkdir()                                  # a file that cannot be opened right now (here: a folder stands in for a locked file)
    try:
        H.set_secret("c", "pw-c-123456")
        refused = False
    except (ValueError, OSError):
        refused = True
    H.SECRETS.rmdir()
    H.SECRETS.write_bytes(good)
    check("saving a password while the file cannot be opened is refused, and the others stay safe", refused and H.get_secret("a") == "pw-a-123456" and H.get_secret("b") == "pw-b-123456")
    H.SECRETS.write_bytes(b"garbage")
    H.set_secret("d", "pw-d-123456")
    check("a damaged file is kept aside (never deleted) and a fresh one is started", H.SECRETS.with_suffix(".damaged").read_bytes() == b"garbage" and H.get_secret("d") == "pw-d-123456")
    H.set_secret("e", "pw-e-123456")
    check("every save keeps the last good copy beside the file and writes it in one piece (no half-written file)", H.SECRETS.with_suffix(".bak").exists() and not H.SECRETS.with_suffix(".tmp").exists() and H.get_secret("d") == "pw-d-123456" and H.get_secret("e") == "pw-e-123456")

    # ---- a sign-in token goes only to its own provider's servers, and the server is greeted first
    asked = []
    O.access_token = lambda secret, now=None, post=None: (asked.append(1) or "TOKEN")
    google = O.pack("123.apps.googleusercontent.com", "GOCSPX-secretvalue", "1//rt", "bob@gmail.com")
    ms = O.pack("8f2c1a3e-4b5d-4e6f-9a7b-1c2d3e4f5a6b", "", "0.A-rt", "bob@outlook.com", "microsoft")

    class Smtp:
        def __init__(self):
            self.log = []

        def ehlo_or_helo_if_needed(self):
            self.log.append("ehlo")

        def auth(self, mech, cb, initial_response_ok=True):
            self.log.append("auth")

    class Imap:
        def __init__(self):
            self.log = []

        def authenticate(self, mech, cb):
            self.log.append("auth")
    s = Smtp()
    O.smtp_auth(s, {"email": "bob@gmail.com", "smtp_host": "smtp.gmail.com"}, google)
    check("the server is greeted before the sign-in is used (an SSL connection has not said hello yet)", s.log == ["ehlo", "auth"])
    for prov, sec, host in (("google", google, "smtp.evil.example"), ("google", google, "smtp.gmail.com.evil.example"), ("microsoft", ms, "mail.evil.example"), ("microsoft", ms, "smtp.gmail.com")):
        s2, asked[:] = Smtp(), []
        try:
            O.smtp_auth(s2, {"email": "bob@x.com", "smtp_host": host}, sec)
            blocked_ok = False
        except O.OAuthRevoked:
            blocked_ok = True
        check(f"a {prov} sign-in is never handed to {host}: no token is even requested", blocked_ok and asked == [] and s2.log == [])
    i2 = Imap()
    try:
        O.imap_auth(i2, {"email": "bob@gmail.com", "imap_host": "imap.evil.example"}, google)
        imap_ok = False
    except O.OAuthRevoked:
        imap_ok = True
    O.imap_auth(Imap(), {"email": "bob@gmail.com", "imap_host": "imap.gmail.com"}, google)
    O.smtp_auth(Smtp(), {"email": "bob@outlook.com", "smtp_host": "smtp.office365.com"}, ms)
    check("the same rule for reading mail, and the real servers of both providers still work", imap_ok and i2.log == [])
    s3 = Smtp()
    O.smtp_auth(s3, {"email": "bob@x.com", "smtp_host": "smtp.evil.example", "username": "bob"}, "plain-app-password") if False else None

    # ---- reading the inbox
    leads = {"lead1@x.co"}
    bounce = (b"From: MAILER-DAEMON@x.com\r\nSubject: Delivery Status Notification (Failure)\r\nMessage-ID: <b1@x>\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=B\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\n"
              b"Could not deliver to lead1@x.co\r\n--B\r\nContent-Type: message/delivery-status\r\n\r\nAction: failed\r\nFinal-Recipient: rfc822; lead1@x.co\r\n\r\n--B--\r\n")
    delay = bounce.replace(b"Action: failed", b"Action: delayed").replace(b"(Failure)", b"(Delay)")
    receipt = bounce.replace(b"report-type=delivery-status", b"report-type=disposition-notification").replace(b"Delivery Status Notification (Failure)", b"Read: Hello")
    check("a real failure notice is a bounce", (S.classify(bounce, leads) or {}).get("kind") == "bounce")
    check("a 'your email is delayed' notice is not a bounce", S.classify(delay, leads) is None)
    check("a read receipt is not a bounce", S.classify(receipt, leads) is None)
    reply = b"From: lead1@x.co\r\nSubject: Re: Hello\r\nDate: not a real date\r\nMessage-ID: <r1@x>\r\n\r\nSounds good, call me Tuesday.\r\n"
    c = S.classify(reply, leads)
    check("a reply with a broken Date header is still read (the message is not lost)", c is not None and c["kind"] == "reply" and "Tuesday" in c["body"])
    # ---- second batch of review fixes
    check("'Stop by Tuesday' is a reply, but a real stop request is an unsubscribe", all((S.classify(f"From: lead1@x.co\r\nSubject: Re: Hello\r\nMessage-ID: <u{i}@x>\r\n\r\n{t}\r\n".encode(), {"lead1@x.co"}) or {}).get("kind") == k
          for i, (t, k) in enumerate([("Stop by Tuesday and we can talk", "reply"), ("Stop", "unsubscribe"), ("Please stop emailing me.", "unsubscribe"), ("Unsubscribe", "unsubscribe"), ("Remove me from your list", "unsubscribe"), ("Do not contact me again", "unsubscribe"), ("Can you stop over on Friday?", "reply")])))
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPNotSupportedError("SMTPUTF8 not supported")))
    check("an address the server can never take (accents without SMTPUTF8) fails that one email instead of blocking its mailbox forever", r["status"] == "failed" and r["bounced"] is False)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPException("strange protocol problem")))
    check("any other mail-protocol problem counts as an attempt, so it gives up after a few tries", r["status"] == "retry" and r["count_attempt"] is True)
    r = S.deliver(item(), PW, MON_10, send=boom(smtplib.SMTPServerDisconnected("closed")))
    check("a dropped connection is a network problem: tried again without using an attempt", r["status"] == "retry" and r["count_attempt"] is False)

    # a password goes only to the server it was first used with
    H.set_secret("pm", "pw-pm-123456")

    class Login:
        def __init__(self):
            self.log = []

        def login(self, *a):
            self.log.append("login")
    pm = {"id": "pm", "email": "pm@me.com", "smtp_host": "smtp.me.com", "imap_host": "imap.me.com"}
    l1 = Login()
    O.smtp_auth(l1, pm, "pw-pm-123456")
    l2 = Login()
    O.smtp_auth(l2, pm, "pw-pm-123456")
    check("the first login remembers the server, and the same server keeps working", l1.log == ["login"] and l2.log == ["login"] and H._read_secrets().get("_host:pm:smtp") == "smtp.me.com")
    l3 = Login()
    try:
        O.smtp_auth(l3, {**pm, "smtp_host": "smtp.evil.example"}, "pw-pm-123456")
        moved = False
    except O.HostChanged as e:
        moved = "type the password again" in str(e) and "pw-pm-123456" not in str(e) and "The mail server in this mailbox" in H.explain(e)
    check("a changed server setting stops the login: the password is not sent, and the message says what to do", moved and l3.log == [])
    box = Login()
    box.login = lambda *a: box.log.append("login")
    O.imap_auth(box, pm, "pw-pm-123456")
    check("the reading server is pinned separately from the sending server", box.log == ["login"] and H._read_secrets().get("_host:pm:imap") == "imap.me.com")
    H.set_secret("pm", "pw-pm-123456")
    l4 = Login()
    O.smtp_auth(l4, {**pm, "smtp_host": "smtp.moved.example"}, "pw-pm-123456")
    check("typing the password again on this PC accepts the new server", l4.log == ["login"] and H._read_secrets().get("_host:pm:smtp") == "smtp.moved.example")

    # a refreshed long-lasting token is kept
    old = O.pack("8f2c1a3e-4b5d-4e6f-9a7b-1c2d3e4f5a6b", "", "OLD-RT", "bob@outlook.com", "microsoft")
    H.set_secret_raw("mb-ms", old)
    O._CACHE.clear()
    REAL_ACCESS(old, now=1.0, post=lambda u, d: {"access_token": "AT", "refresh_token": "NEW-RT", "expires_in": 3600})
    check("Microsoft's newer long-lasting token replaces the old one in the saved sign-in (so it does not expire 90 days after the first)", O.unpack(H.get_secret("mb-ms"))["rt"] == "NEW-RT" and O.provider_of(H.get_secret("mb-ms")) == "microsoft")

    # answers and warmup mail count toward the day
    S._save_state({})
    H.set_secret("m1", PW)
    S._extra_add("m1", MON_10)
    sends_x = []
    apiX = Api([item(7, mailbox=mbox("m1", daily_limit=1))])
    sX = S.run_pass(apiX, now=MON_10, send=lambda m, pw, ms: sends_x.append(1), poll=False, out=lambda *a: None)
    check("an inbox answer or warmup email sent today uses up the mailbox's daily limit: no campaign email goes past it", sends_x == [] and sX["sent"] == 0 and sum(sX["held"].values()) == 1, str(sX["held"]))
    check("the count restarts the next day", S._extra_today(MON_10 + dt.timedelta(days=1)) == {} and S._extra_today(MON_10) == {"m1": 1})

    # the sign-in page's error text is cleaned
    class ErrLoop:
        redirect_uri = "http://127.0.0.1:5555"

        def wait(self, timeout=0):
            return {"error": "x<script>alert(1)</script>\x1b[31m", "code": "C", "extra": "ignored"}
    try:
        O.run_flow("bob@gmail.com", {"cid": "1.apps.googleusercontent.com", "cs": "GOCSPX-secretvalue"}, loop=ErrLoop(), opener=lambda u: None, out=lambda *a: None)
        msg_err = ""
    except O.OAuthSetupError as e:
        msg_err = str(e)
    check("an error a web page puts in the local sign-in address is cleaned before it is shown", "did not allow it" in msg_err and "<" not in msg_err and "\x1b" not in msg_err)

finally:
    shutil.rmtree(tmp, ignore_errors=True)

src = "".join((ROOT / "dse" / n).read_text(encoding="utf-8") for n in ("herald.py", "herald_send.py", "herald_oauth.py")) + Path(__file__).read_text(encoding="utf-8")
check("no em dash", DASH not in src)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
