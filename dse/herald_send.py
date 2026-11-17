"""Herald (phase 3): the sending engine on this PC.

When you press Start on a campaign in Citadel, its whole schedule is written to Citadel, already merged and with the real unsubscribe link in it. This PC then sends each email from YOUR
mailbox when it is due, and reads the mailbox for replies, bounces and unsubscribe requests from your own leads (which stops their remaining emails). Every minute the runner calls one pass:

    python dse.py herald send [--dry]        one pass now (--dry shows what would go, and sends nothing)
    python dse.py herald sendtest <mailbox> <to>   send ONE test email from a mailbox to an address you choose
    python dse.py herald pause | resume      stop or restart all sending on this PC (a file switch; Citadel campaigns keep their place)

The rules, all enforced here and never by trust:
  * a campaign must be RUNNING in Citadel (you pressed Start); nothing else is ever sent;
  * inside the campaign's send window, on its send days, in its time zone;
  * at most the mailbox's daily limit (counted from what was really sent today), one email per mailbox per pass, and at least the mailbox's gap since its last email;
  * a follow-up only after the previous step went out, and not sooner than its delay;
  * never to a lead who replied, bounced or unsubscribed; stop switch: data/herald/PAUSE;
  * the mailbox password is read from this PC only, and never printed or logged. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import email
import email.policy
import email.utils
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import herald as H

SITE_URL = (os.environ.get("HQ_SITE_URL") or "https://dbicitadel.vercel.app").rstrip("/")
PAUSE = lambda: H.DATA / "PAUSE"          # noqa: E731  (looked up each time so tests can move DATA)
ENGINE = lambda: H.DATA / "engine.json"   # noqa: E731
SENDLOG = lambda: H.DATA / "sendlog.jsonl"  # noqa: E731
POLL_EVERY_S = 300
MAX_ATTEMPTS = 3
HARD_PC_DAILY_CAP = 1500
DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PERMANENT = (550, 551, 553)               # the address does not exist (a bounce)


# ------------------------------------------------------------------ time

def tz_of(name: str):
    """The time zone, or None when this PC has no time zone data for it (install it with: pip install tzdata). Never guesses."""
    if (name or "").upper() in ("UTC", "GMT", "Z"):
        return dt.timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def _hm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _parse_ts(s) -> dt.datetime | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------ the decision: is this email allowed to go right now?

def decide(item: dict, now: dt.datetime, sent_today: dict, last_sent: dict, used_this_pass: set, has_password: bool) -> tuple[bool, str]:
    """(may send now, why not). `sent_today[mailbox_id]` counts today's sends in the campaign's time zone; `last_sent[mailbox_id]` is the last send time (UTC)."""
    m = item["mailbox"]
    mid = m["id"]
    if item.get("lead_status") != "new":
        return False, "the lead is no longer emailable"
    if int(item.get("attempts", 0)) >= MAX_ATTEMPTS:
        return False, "too many attempts"
    if m.get("paused"):
        return False, "the mailbox is paused"
    if not has_password:
        return False, "no password set on this PC for this mailbox"
    tz = tz_of(m.get("timezone", "UTC"))
    if tz is None:
        return False, f"no time zone data for {m.get('timezone')} on this PC (run: pip install tzdata)"
    local = now.astimezone(tz)
    day = local.date()
    sched_day = dt.date.fromisoformat(str(item["scheduled_day"])[:10])
    if sched_day > day:
        return False, "not due yet"
    if DOW[local.weekday()] not in m.get("send_days", DOW[:5]):
        return False, "not a send day"
    if not (_hm(m["window_start"]) <= local.time().replace(second=0, microsecond=0) < _hm(m["window_end"])):
        return False, "outside the send window"
    if sched_day == day and local.time() < _hm(item.get("scheduled_time", "00:00")):
        return False, "earlier than its planned time"
    if int(item["step"]) > 1:
        if item.get("prev_open"):
            return False, "the previous step has not gone out"
        prev = _parse_ts(item.get("prev_sent_at"))
        if prev and day < prev.astimezone(tz).date() + dt.timedelta(days=int(item.get("delay_days", 0))):
            return False, "its delay after the previous step has not passed"
    if mid in used_this_pass:
        return False, "this mailbox already sent this pass"
    if sent_today.get(mid, 0) >= int(m["daily_limit"]):
        return False, "the mailbox's daily limit is reached"
    last = last_sent.get(mid)
    if last and (now - last).total_seconds() < int(m["min_gap_seconds"]):
        return False, "the gap since this mailbox's last email has not passed"
    return True, ""


def count_today(recent: list[dict], boxes: dict[str, dict], now: dt.datetime) -> tuple[dict, dict]:
    """From the last 48 hours of sends: how many each mailbox sent today (in its own time zone) and when it last sent."""
    today, last = {}, {}
    for r in recent:
        t = _parse_ts(r.get("sent_at"))
        mid = r.get("mailbox_id")
        if not t or not mid:
            continue
        if mid not in last or t > last[mid]:
            last[mid] = t
        tz = tz_of((boxes.get(mid) or {}).get("timezone", "UTC")) or dt.timezone.utc
        if t.astimezone(tz).date() == now.astimezone(tz).date():
            today[mid] = today.get(mid, 0) + 1
    return today, last


# ------------------------------------------------------------------ the message

def unsub_url(token: str) -> str:
    return f"{SITE_URL}/unsubscribe/{token}"


def build_message(item: dict, now: dt.datetime) -> EmailMessage:
    m = item["mailbox"]
    msg = EmailMessage()
    name = (m.get("display_name") or "").strip()
    msg["From"] = email.utils.formataddr((name, m["email"])) if name else m["email"]
    msg["To"] = item["to_email"]
    msg["Subject"] = item.get("subject") or ""
    msg["Date"] = email.utils.format_datetime(now)
    msg["Message-ID"] = email.utils.make_msgid(domain=m["email"].split("@")[1])
    if item.get("prev_message_id"):
        msg["In-Reply-To"] = item["prev_message_id"]
        msg["References"] = " ".join(x for x in (item.get("first_message_id"), item["prev_message_id"]) if x)
    if item.get("unsub_token"):
        msg["List-Unsubscribe"] = f"<{unsub_url(item['unsub_token'])}>, <mailto:{m['email']}?subject=unsubscribe>"
    msg.set_content(item["body"])
    return msg


def _smtp_send(m: dict, password: str, msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()
    if m.get("smtp_security", "ssl") == "ssl":
        with smtplib.SMTP_SSL(m["smtp_host"], int(m["smtp_port"]), timeout=H.TIMEOUT, context=ctx) as s:
            s.login(m.get("username") or m["email"], password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(m["smtp_host"], int(m["smtp_port"]), timeout=H.TIMEOUT) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(m.get("username") or m["email"], password)
            s.send_message(msg)


def deliver(item: dict, password: str, now: dt.datetime, send=_smtp_send) -> dict:
    """Sends one email and says what happened, in the form Citadel stores. Never includes the password."""
    msg = build_message(item, now)
    mid = msg["Message-ID"]
    try:
        send(item["mailbox"], password, msg)
        return {"id": item["id"], "status": "sent", "message_id": mid, "sent_at": now.isoformat(timespec="seconds")}
    except smtplib.SMTPAuthenticationError as e:
        return {"id": item["id"], "status": "retry", "count_attempt": False, "error": H._scrub("The mail server refused the login: " + H.explain(e, item["mailbox"].get("provider", "")), password), "auth": True}
    except smtplib.SMTPRecipientsRefused as e:
        code = next((c for c, _ in e.recipients.values()), 550)
        return {"id": item["id"], "status": "failed", "bounced": code in PERMANENT, "error": H._scrub(f"The server refused the address ({code}).", password)}
    except smtplib.SMTPResponseException as e:
        if e.smtp_code in PERMANENT:
            return {"id": item["id"], "status": "failed", "bounced": True, "error": H._scrub(f"Address does not exist ({e.smtp_code}).", password)}
        if 500 <= e.smtp_code < 600:
            return {"id": item["id"], "status": "failed", "bounced": False, "error": H._scrub(f"The server rejected the email ({e.smtp_code}): {e.smtp_error!r}"[:300], password)}
        return {"id": item["id"], "status": "retry", "count_attempt": True, "error": H._scrub(f"Temporary server error ({e.smtp_code}).", password)}
    except (socket.timeout, TimeoutError, ConnectionError, OSError, smtplib.SMTPException, ssl.SSLError) as e:
        return {"id": item["id"], "status": "retry", "count_attempt": False, "error": H._scrub(H.explain(e, item["mailbox"].get("provider", "")), password)}


# ------------------------------------------------------------------ one pass

def _state() -> dict:
    try:
        d = json.loads(ENGINE().read_text(encoding="utf-8")) if ENGINE().exists() else {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save_state(d: dict) -> None:
    H.DATA.mkdir(parents=True, exist_ok=True)
    ENGINE().write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


def _log(line: dict) -> None:
    H.DATA.mkdir(parents=True, exist_ok=True)
    with SENDLOG().open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def run_pass(api, now: dt.datetime | None = None, dry: bool = False, send=_smtp_send, poll=True, out=print) -> dict:
    """One pass: send what is due (at most one per mailbox), report, and now and then read the inboxes."""
    now = now or dt.datetime.now(dt.timezone.utc)
    summary = {"checked": 0, "sent": 0, "held": {}, "events": 0, "paused": False}
    if PAUSE().exists():
        summary["paused"] = True
        out("Herald sending is paused on this PC (data/herald/PAUSE). Run: python dse.py herald resume")
        return summary
    due = api.rpc("hq_herald_due", {"p_limit": 200}) or []
    summary["checked"] = len(due)
    secrets = H._read_secrets()
    boxes = {d["mailbox"]["id"]: d["mailbox"] for d in due}
    recent = api.rpc("hq_herald_recent_sent", {}) or []
    sent_today, last_sent = count_today(recent, boxes, now)
    if sum(sent_today.values()) >= HARD_PC_DAILY_CAP:
        out(f"This PC has sent {sum(sent_today.values())} today: the safety cap of {HARD_PC_DAILY_CAP} is reached.")
        due = []
    used: set = set()
    bad_login: set = set()
    results = []
    for it in due:
        mid = it["mailbox"]["id"]
        if mid in bad_login:
            continue
        ok, why = decide(it, now, sent_today, last_sent, used, bool(secrets.get(mid)))
        if not ok:
            summary["held"][why] = summary["held"].get(why, 0) + 1
            continue
        if dry:
            out(f"WOULD SEND to {it['to_email']} (step {it['step']}) from {it['mailbox']['email']}: {it['subject'][:60]}")
            used.add(mid)
            continue
        r = deliver(it, secrets[mid], now, send)
        used.add(mid)
        results.append(r)
        _log({"at": now.isoformat(timespec="seconds"), "to": it["to_email"], "from": it["mailbox"]["email"], "step": it["step"], "result": r["status"], "error": r.get("error", "")})
        if r.get("auth"):
            bad_login.add(mid)
        if r["status"] == "sent":
            summary["sent"] += 1
            sent_today[mid] = sent_today.get(mid, 0) + 1
            last_sent[mid] = now
    if results:
        api.rpc("hq_herald_report", {"p_results": [{k: v for k, v in r.items() if k != "auth"} for r in results]})
    if poll and not dry:
        summary["events"] = poll_all(api, now, secrets, out)
    return summary


# ------------------------------------------------------------------ reading the mailbox for replies, bounces, unsubscribes

AUTO_SUBJECT = re.compile(r"^\s*(automatic reply|auto(matic)?[- ]?reply|autoreply|auto:|out of (the )?office|away from|vacation)", re.I)
BOUNCE_SUBJECT = re.compile(r"(undeliverable|delivery status notification|mail delivery (failed|subsystem)|returned mail|failure notice|delivery failure)", re.I)
UNSUB_BODY = re.compile(r"^\s*(please\s+)?(stop|unsubscribe|remove me|opt[- ]?out|take me off|do not (contact|email))\b", re.I)
ADDR = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _text_of(msg) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        txt = part.get_content() if part else ""
    except Exception:
        txt = ""
    if not txt:
        try:
            txt = msg.get_payload(decode=True).decode("utf-8", "replace") if not msg.is_multipart() else ""
        except Exception:
            txt = ""
    return re.sub(r"<[^>]+>", " ", txt)


def classify(raw: bytes, leads: set[str]) -> dict | None:
    """Reads one message: a reply, a bounce or an unsubscribe request from one of YOUR leads, or None (auto-replies and everything else are ignored)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    sender = email.utils.parseaddr(str(msg.get("From", "")))[1].lower()
    subject = re.sub(r"\s+", " ", str(msg.get("Subject", ""))).strip()
    text = _text_of(msg)
    when = _parse_ts(email.utils.parsedate_to_datetime(str(msg["Date"])).isoformat()) if msg.get("Date") else None
    base = {"subject": subject[:300], "received_at": (when or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")}
    local = sender.split("@")[0]
    ctype = (msg.get_content_type() or "").lower()
    if local in ("mailer-daemon", "postmaster") or "delivery-status" in ctype or "report" in ctype or BOUNCE_SUBJECT.search(subject):
        found = [a.lower() for a in ADDR.findall(text) if a.lower() in leads]
        if not found:
            return None
        return {**base, "kind": "bounce", "from_email": found[0], "snippet": re.sub(r"\s+", " ", text).strip()[:300]}
    auto = str(msg.get("Auto-Submitted", "no")).lower() != "no" or msg.get("X-Autoreply") or msg.get("X-Autorespond") or str(msg.get("Precedence", "")).lower() in ("auto_reply", "bulk", "junk") or AUTO_SUBJECT.search(subject)
    if auto or sender not in leads:
        return None
    first = text.strip()[:300]
    kind = "unsubscribe" if UNSUB_BODY.search(first) or re.match(r"^\s*(unsubscribe|stop)\s*$", subject, re.I) else "reply"
    return {**base, "kind": kind, "from_email": sender, "snippet": re.sub(r"\s+", " ", first)[:600]}


def fetch_new(m: dict, password: str, since: dt.date, seen: set[str], connect=None) -> list[tuple[str, bytes]]:
    """New messages in the inbox since a date, without marking anything as read."""
    connect = connect or (lambda: imaplib.IMAP4_SSL(m["imap_host"], int(m["imap_port"]), ssl_context=ssl.create_default_context(), timeout=H.TIMEOUT))
    box = connect()
    out: list[tuple[str, bytes]] = []
    try:
        box.login(m.get("username") or m["email"], password)
        box.select("INBOX", readonly=True)
        typ, data = box.search(None, "SINCE", since.strftime("%d-%b-%Y"))
        for num in (data[0].split() if typ == "OK" and data and data[0] else [])[-300:]:
            typ, parts = box.fetch(num, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.6000>)")
            if typ != "OK":
                continue
            blobs = [p[1] for p in parts if isinstance(p, tuple)]
            raw = b"\r\n".join(blobs)
            mid = re.search(rb"(?im)^Message-ID:\s*(\S+)", raw)
            key = (mid.group(1).decode("utf-8", "replace") if mid else f"{m['id']}:{num.decode()}")
            if key in seen:
                continue
            out.append((key, raw))
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return out


def poll_all(api, now: dt.datetime, secrets: dict, out=print, fetch=fetch_new) -> int:
    st = _state()
    polled = st.setdefault("polled", {})
    seen = set(st.get("seen", []))
    todo = [m for m in H.load_mailboxes() if secrets.get(m["id"])]
    todo = [m for m in todo if (not polled.get(m["id"])) or (now - (_parse_ts(polled[m["id"]]) or now)).total_seconds() >= POLL_EVERY_S]
    if not todo:
        return 0
    leads = {str(e).lower() for e in (api.rpc("hq_herald_lead_emails", {}) or [])}
    events = []
    for m in todo:
        since = (_parse_ts(polled.get(m["id"])) or now - dt.timedelta(days=3)).date() - dt.timedelta(days=1)
        try:
            for key, raw in fetch(m, secrets[m["id"]], since, seen):
                seen.add(key)
                ev = classify(raw, leads)
                if ev:
                    events.append({**ev, "mailbox_id": m["id"]})
            polled[m["id"]] = now.isoformat(timespec="seconds")
        except Exception as e:
            out(f"Herald: could not read {m['email']}: {H._scrub(H.explain(e, m.get('provider', '')), secrets[m['id']])}")
    n = 0
    if events:
        n = int(api.rpc("hq_herald_events", {"p_events": events[:500]}) or 0)
    st["seen"] = list(seen)[-3000:]
    _save_state(st)
    return n


# ------------------------------------------------------------------ test email and the stop switch

def send_test(ref: str, to: str, send=_smtp_send) -> str:
    """ONE email from a mailbox to an address you type: to see that sending works and how it looks. It is not a campaign email."""
    m = H.find(ref)
    pw = H.get_secret(m["id"])
    if not pw:
        raise ValueError(f"No password is set on this PC for {m['email']}. Run: python dse.py herald secret {m['email']}")
    if not H.EMAIL_RX.match(to or ""):
        raise ValueError("Give the address to send the test to, like you@example.com.")
    now = dt.datetime.now(dt.timezone.utc)
    msg = build_message({"id": "test", "mailbox": m, "to_email": to, "subject": "Herald test email", "body": "This is a test email from Herald, sent from your own mailbox so you can see that sending works.\n\nNothing else was sent."}, now)
    try:
        send(m, pw, msg)
    except Exception as e:
        raise ValueError("The test email was not sent: " + H._scrub(H.explain(e, m.get("provider", "")), pw)) from None
    return f"Sent one test email from {m['email']} to {to}."


def pause() -> str:
    H.DATA.mkdir(parents=True, exist_ok=True)
    PAUSE().write_text("paused " + dt.datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
    return "Herald sending is paused on this PC. Campaigns keep their place. Run: python dse.py herald resume"


def resume() -> str:
    if PAUSE().exists():
        PAUSE().unlink()
        return "Herald sending is on again."
    return "Sending was not paused."
