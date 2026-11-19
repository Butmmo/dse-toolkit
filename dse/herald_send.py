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
  * answers you write in the Citadel inbox are sent at once from the same mailbox, in the same thread (never to someone who unsubscribed or bounced);
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
import time
from email.message import EmailMessage
from pathlib import Path

from . import herald as H
from . import herald_oauth as O
from . import herald_graph as G

SITE_URL = (os.environ.get("HQ_SITE_URL") or "https://dbicitadel.vercel.app").rstrip("/")
RUN_LOCK = lambda: H.DATA / "run.lock"          # noqa: E731
LOCK_STALE_S = 20 * 60                                 # a pass that died leaves a lock behind: it is ignored after 20 minutes
PAUSE = lambda: H.DATA / "PAUSE"          # noqa: E731  (looked up each time so tests can move DATA)
ENGINE = lambda: H.DATA / "engine.json"   # noqa: E731
SENDLOG = lambda: H.DATA / "sendlog.jsonl"  # noqa: E731
POLL_EVERY_S = 300
MAX_ATTEMPTS = 3
HARD_PC_DAILY_CAP = 1500
DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PERMANENT = (550, 551, 553)               # the address does not exist (a bounce) ... unless the server's own words say it is about us (SOFT_REFUSAL below)
# a 5xx that is really about the sender, a quota, spam rules or a block: the lead is fine and must NOT be marked bounced or suppressed
SOFT_REFUSAL = re.compile(r"\b5\.7\.\d|\b5\.4\.5|quota|spam|block(ed|list)|denied|polic(y|ies)|reputation|rate|too many|throttl|limit|try again|temporar|sender", re.I)


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


TZ_MISSING = "no time zone data for"


def tz_warning(name) -> str:
    """The loud line for the runner log: with no time zone data NOTHING is sent (19 Nov 2026: a whole day of emails was silently held)."""
    return (f"!!! HERALD WARNING: this PC has no time zone data for '{name}', so Herald is HOLDING EVERY EMAIL for it and sending nothing. "
            "Fix: run  python -m pip install tzdata  (bridge/start-runner.ps1 and requirements.txt now include it), then restart the runner.")


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
        return False, f"{TZ_MISSING} {m.get('timezone')} on this PC (run: pip install tzdata)"
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
    if G.is_cloud(password):                      # signed in with Microsoft from Citadel: send through Microsoft Graph, no SMTP
        return G.send_mime(m["id"], msg)
    ctx = ssl.create_default_context()
    if m.get("smtp_security", "ssl") == "ssl":
        with smtplib.SMTP_SSL(m["smtp_host"], int(m["smtp_port"]), timeout=H.TIMEOUT, context=ctx) as s:
            O.smtp_auth(s, m, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(m["smtp_host"], int(m["smtp_port"]), timeout=H.TIMEOUT) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            O.smtp_auth(s, m, password)
            s.send_message(msg)


def deliver(item: dict, password: str, now: dt.datetime, send=_smtp_send) -> dict:
    """Sends one email and says what happened, in the form Citadel stores. Never includes the password."""
    try:
        msg = build_message(item, now)
    except ValueError:
        # a header with a line break or an illegal character (a mailbox name, a reply reference): this one email fails, the pass and the other mailboxes carry on
        return {"id": item["id"], "status": "failed", "bounced": False, "error": "This email could not be built: a mailbox name, subject or reply reference has a line break or an illegal character. Fix it in Citadel."}
    mid = msg["Message-ID"]
    try:
        send(item["mailbox"], password, msg)
        return {"id": item["id"], "status": "sent", "message_id": mid, "sent_at": now.isoformat(timespec="seconds")}
    except smtplib.SMTPAuthenticationError as e:
        return {"id": item["id"], "status": "retry", "count_attempt": False, "error": H._scrub("The mail server refused the login: " + H.explain(e, item["mailbox"].get("provider", "")), password), "auth": True}
    except smtplib.SMTPRecipientsRefused as e:
        code, text = next(((c, t) for c, t in e.recipients.values()), (550, b""))
        why = text.decode("utf-8", "replace") if isinstance(text, (bytes, bytearray)) else str(text)
        if 400 <= code < 500 or (code in PERMANENT and SOFT_REFUSAL.search(why)):
            return {"id": item["id"], "status": "retry", "count_attempt": True, "error": H._scrub(f"The server could not take this email now ({code}); it is tried again.", password)}
        return {"id": item["id"], "status": "failed", "bounced": code in PERMANENT, "error": H._scrub(f"The server refused the address ({code}).", password)}
    except smtplib.SMTPResponseException as e:
        # a sender or content refusal says nothing about whether the lead's address exists: never a bounce
        if 500 <= e.smtp_code < 600:
            return {"id": item["id"], "status": "failed", "bounced": False, "error": H._scrub(f"The server rejected the email ({e.smtp_code}): {e.smtp_error!r}"[:300], password)}
        return {"id": item["id"], "status": "retry", "count_attempt": True, "error": H._scrub(f"Temporary server error ({e.smtp_code}).", password)}
    except smtplib.SMTPNotSupportedError:
        # for example an address with accented letters through a server that does not take them: it will never work, so it must not block this mailbox's queue
        return {"id": item["id"], "status": "failed", "bounced": False, "error": "The mail server does not support something this email needs (for example an address with accented letters)."}
    except (smtplib.SMTPServerDisconnected, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError) as e:
        return {"id": item["id"], "status": "retry", "count_attempt": False, "error": H._scrub(H.explain(e, item["mailbox"].get("provider", "")), password)}
    except smtplib.SMTPException as e:
        # any other mail-protocol problem counts as an attempt, so one strange email gives up after a few tries instead of blocking its mailbox forever
        return {"id": item["id"], "status": "retry", "count_attempt": True, "error": H._scrub(H.explain(e, item["mailbox"].get("provider", "")), password)}
    except OSError as e:
        return {"id": item["id"], "status": "retry", "count_attempt": False, "error": H._scrub(H.explain(e, item["mailbox"].get("provider", "")), password)}


# Mail that is not a campaign email (inbox answers, warmup) still uses the mailbox's day. This counts it on this PC so the daily limit sees it.
def _extra_add(mailbox_id: str, now: dt.datetime) -> None:
    st = _state()
    day = now.date().isoformat()
    ex = st.get("extra") if isinstance(st.get("extra"), dict) and st["extra"].get("day") == day else {"day": day, "n": {}}
    ex["n"][mailbox_id] = int(ex["n"].get(mailbox_id, 0)) + 1
    st["extra"] = ex
    _save_state(st)


def _extra_today(now: dt.datetime) -> dict:
    ex = _state().get("extra")
    return dict(ex["n"]) if isinstance(ex, dict) and ex.get("day") == now.date().isoformat() and isinstance(ex.get("n"), dict) else {}


# ------------------------------------------------------------------ answers written in the Citadel inbox

def build_answer(item: dict, now: dt.datetime) -> EmailMessage:
    m = item["mailbox"]
    msg = EmailMessage()
    name = (m.get("display_name") or "").strip()
    msg["From"] = email.utils.formataddr((name, m["email"])) if name else m["email"]
    msg["To"] = item["to_email"]
    msg["Subject"] = item.get("subject") or ""
    msg["Date"] = email.utils.format_datetime(now)
    msg["Message-ID"] = email.utils.make_msgid(domain=m["email"].split("@")[1])
    if item.get("in_reply_to"):
        msg["In-Reply-To"] = item["in_reply_to"]
        msg["References"] = (item.get("refs") or item["in_reply_to"]).strip()[:1000]
    msg.set_content(item["body"])
    return msg


def send_answers(api, now: dt.datetime, secrets: dict, dry: bool = False, send=_smtp_send, out=print) -> int:
    """Sends the answers the member wrote in the Citadel inbox, at once, in the same thread. Never to someone who unsubscribed or bounced."""
    owed_ids = set() if dry else journal_flush(api, "answers", "hq_herald_outbox_report", "p_results", out)      # first: so the list below no longer holds answers that were already sent
    items = api.rpc("hq_herald_outbox_due", {}) or []
    results, sent, bad_login = [], 0, set()
    for it in items:
        m = it["mailbox"]
        if str(it["id"]) in owed_ids:
            continue
        if m["id"] in bad_login or m.get("paused") or not secrets.get(m["id"]):
            continue
        if it.get("lead_status") in ("unsubscribed", "bounced"):
            results.append({"id": it["id"], "status": "failed", "error": "They unsubscribed or the address bounced: not sent."})
            continue
        if dry:
            out(f"WOULD SEND an answer to {it['to_email']} from {m['email']}")
            continue
        try:
            msg = build_answer(it, now)
        except ValueError:
            results.append({"id": it["id"], "status": "failed", "error": "This answer could not be built: a name or reply reference has a line break or an illegal character."})
            continue
        try:
            send(m, secrets[m["id"]], msg)
            results.append({"id": it["id"], "status": "sent", "message_id": msg["Message-ID"], "sent_at": now.isoformat(timespec="seconds")})
            journal_save("answers", [r for r in results if r["status"] == "sent"])      # written down before Citadel is told
            sent += 1
            _extra_add(m["id"], now)
        except smtplib.SMTPAuthenticationError as e:
            bad_login.add(m["id"])
            results.append({"id": it["id"], "status": "retry", "count_attempt": False, "error": H._scrub("The mail server refused the login: " + H.explain(e, m.get("provider", "")), secrets[m["id"]])})
        except smtplib.SMTPRecipientsRefused:
            results.append({"id": it["id"], "status": "failed", "error": "The server refused the address."})
        except smtplib.SMTPResponseException as e:
            results.append({"id": it["id"], "status": "failed" if 500 <= e.smtp_code < 600 else "retry", "count_attempt": True, "error": H._scrub(f"The server answered {e.smtp_code}.", secrets[m["id"]])})
        except (socket.timeout, TimeoutError, ConnectionError, OSError, smtplib.SMTPException, ssl.SSLError) as e:
            results.append({"id": it["id"], "status": "retry", "count_attempt": False, "error": H._scrub(H.explain(e, m.get("provider", "")), secrets[m["id"]])})
        _log({"at": now.isoformat(timespec="seconds"), "to": it["to_email"], "from": m["email"], "step": 0, "result": results[-1]["status"], "error": results[-1].get("error", ""), "kind": "answer"})
    if results:
        try:
            api.rpc("hq_herald_outbox_report", {"p_results": results})
            journal_save("answers", [])
        except Exception:
            out("Citadel could not be told about these answers yet: they are remembered on this PC and reported next minute (nothing is sent twice).")
    return sent


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


# Results Citadel has not been told about yet. An email that WAS sent is written here the moment it is sent, before the report is made: if the report fails (internet, a crash), the next pass
# reports it first and does not send that email again. Without this, a failed report meant the same email went out again every minute.
def _journal() -> Path:
    return H.DATA / "unreported.json"


def _journal_load() -> list:
    try:
        d = json.loads(_journal().read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _journal_save(items: list) -> None:
    H.DATA.mkdir(parents=True, exist_ok=True)
    tmp = _journal().with_suffix(".tmp")
    tmp.write_text(json.dumps(items), encoding="utf-8")
    os.replace(tmp, _journal())


# Answers and warmup mail are journalled like campaign mail: a sent email is written down on this PC BEFORE Citadel is told, so a crash or a failed report can never make the next pass send it a second time.
def _jpath(name: str) -> Path:
    return H.DATA / f"journal-{name}.json"


def journal_load(name: str) -> list:
    try:
        d = json.loads(_jpath(name).read_text(encoding="utf-8")) if _jpath(name).exists() else []
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def journal_save(name: str, items: list) -> None:
    H.DATA.mkdir(parents=True, exist_ok=True)
    tmp = _jpath(name).with_suffix(".tmp")
    tmp.write_text(json.dumps(items), encoding="utf-8")
    os.replace(tmp, _jpath(name))


def journal_flush(api, name: str, rpc: str, param: str, out=print) -> set:
    """Tells Citadel about sends from an earlier pass that it was not told about. Returns the ids that are still owed (so they are not sent again)."""
    owed = journal_load(name)
    if not owed:
        return set()
    try:
        api.rpc(rpc, {param: owed})
        journal_save(name, [])
        return set()
    except Exception:
        out("Citadel could not be told about earlier sends yet: they will not be sent again, and it is tried again next minute.")
        return {str(o.get("id")) for o in owed}


def _take_lock(now_s: float | None = None) -> bool:
    """Only one send pass may run on this PC at a time (the periodic runner and a manual 'herald send' could otherwise send the same email twice). Created exclusively, so two passes cannot both get it."""
    now_s = time.time() if now_s is None else now_s
    p = RUN_LOCK()
    H.DATA.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {int(now_s)}\n".encode("ascii"))
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if now_s - p.stat().st_mtime < LOCK_STALE_S:
                    return False
                p.unlink()                              # left behind by a pass that died: take over
            except FileNotFoundError:
                continue
            except OSError:
                return False
    return False


def _drop_lock() -> None:
    try:
        RUN_LOCK().unlink()
    except OSError:
        pass


def run_pass(api, now: dt.datetime | None = None, dry: bool = False, send=_smtp_send, poll=True, out=print) -> dict:
    """One pass: send what is due (at most one per mailbox), report, and now and then read the inboxes. Only one pass runs at a time on this PC."""
    if dry:
        return _run_pass(api, now, dry, send, poll, out)
    if not _take_lock():
        out("Herald: another send pass is already running on this PC: this one stops so nothing is sent twice.")
        return {"checked": 0, "sent": 0, "held": {"another pass is running": 1}, "events": 0, "paused": False, "answers": 0, "warm": 0, "ramped": 0, "hooks": 0}
    try:
        return _run_pass(api, now, dry, send, poll, out)
    finally:
        _drop_lock()


def _run_pass(api, now: dt.datetime | None = None, dry: bool = False, send=_smtp_send, poll=True, out=print) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    summary = {"checked": 0, "sent": 0, "held": {}, "events": 0, "paused": False, "answers": 0, "warm": 0, "ramped": 0, "hooks": 0}
    if PAUSE().exists():
        summary["paused"] = True
        out("Herald sending is paused on this PC (data/herald/PAUSE). Run: python dse.py herald resume")
        return summary
    G.set_api(api)
    secrets = G.with_signed_in(api, H._read_secrets())      # mailboxes signed in through Citadel count as having a login
    summary["answers"] = send_answers(api, now, secrets, dry, send, out)
    from . import herald_warm as W        # the ramp and the opt-in exchange (phase 6); imported here because it imports this module
    plan = W.get_plan(api)
    if not dry:
        summary["warm"] = W.answer_warm(api, now, secrets, send, out=out) + W.send_warm(api, now, plan, secrets, send, out=out)
    owed = [] if dry else _journal_load()
    if owed:
        try:
            api.rpc("hq_herald_report", {"p_results": [o["r"] for o in owed]})
            owed = []
            _journal_save([])
        except Exception:
            out("Citadel could not be told about earlier sends yet: they will not be sent again, and it is tried again next minute.")
    owed_ids = {o["r"]["id"] for o in owed}
    due = api.rpc("hq_herald_due", {"p_limit": 200}) or []
    summary["ramped"] = W.apply_ramp(due, plan)
    summary["checked"] = len(due)
    boxes = {d["mailbox"]["id"]: d["mailbox"] for d in due}
    recent = api.rpc("hq_herald_recent_sent", {}) or []
    sent_today, last_sent = count_today(recent, boxes, now)
    for mb, n in _extra_today(now).items():              # answers and warmup mail sent from this PC today
        sent_today[mb] = sent_today.get(mb, 0) + int(n)
    for o in owed:                                       # sent but not yet known to Citadel: they still count against today's limits
        if o["r"].get("status") == "sent":
            sent_today[o["mb"]] = sent_today.get(o["mb"], 0) + 1
            last_sent[o["mb"]] = now
    if sum(sent_today.values()) >= HARD_PC_DAILY_CAP:
        out(f"This PC has sent {sum(sent_today.values())} today: the safety cap of {HARD_PC_DAILY_CAP} is reached.")
        due = []
    used: set = set()
    bad_login: set = set()
    tz_warned = False
    results = []
    for it in due:
        mid = it["mailbox"]["id"]
        if mid in bad_login:
            continue
        if it["id"] in owed_ids:
            summary["held"]["already sent, waiting to be reported"] = summary["held"].get("already sent, waiting to be reported", 0) + 1
            continue
        ok, why = decide(it, now, sent_today, last_sent, used, bool(secrets.get(mid)))
        if not ok:
            summary["held"][why] = summary["held"].get(why, 0) + 1
            if why.startswith(TZ_MISSING) and not tz_warned:
                tz_warned = True
                out(tz_warning(it["mailbox"].get("timezone")))
            continue
        if dry:
            out(f"WOULD SEND to {it['to_email']} (step {it['step']}) from {it['mailbox']['email']}: {it['subject'][:60]}")
            used.add(mid)
            continue
        r = deliver(it, secrets[mid], now, send)
        used.add(mid)
        results.append(r)
        owed.append({"r": {k: v for k, v in r.items() if k != "auth"}, "mb": mid})
        _journal_save(owed)                              # written before the report, so a crash or a failed report cannot cause a second send
        _log({"at": now.isoformat(timespec="seconds"), "to": it["to_email"], "from": it["mailbox"]["email"], "step": it["step"], "result": r["status"], "error": r.get("error", "")})
        if r.get("auth"):
            bad_login.add(mid)
        if r["status"] == "sent":
            summary["sent"] += 1
            sent_today[mid] = sent_today.get(mid, 0) + 1
            last_sent[mid] = now
    if results:
        try:
            api.rpc("hq_herald_report", {"p_results": [{k: v for k, v in r.items() if k != "auth"} for r in results]})
            _journal_save([])
        except Exception:
            out("Citadel could not be told about this pass yet: the sends are remembered on this PC and reported next minute (nothing is sent twice).")
    if poll and not dry:
        summary["events"] = poll_all(api, now, secrets, out)
    if not dry:
        from . import herald_hooks            # webhooks (phase 7): deliver what Citadel queued, including events found just now
        summary["hooks"] = herald_hooks.run(api, now, out=out)
    return summary


# ------------------------------------------------------------------ reading the mailbox for replies, bounces, unsubscribes

AUTO_SUBJECT = re.compile(r"^\s*(automatic reply|auto(matic)?[- ]?reply|autoreply|auto:|out of (the )?office|away from|vacation)", re.I)
BOUNCE_SUBJECT = re.compile(r"(undeliverable|delivery status notification|mail delivery (failed|subsystem)|returned mail|failure notice|delivery failure)", re.I)
UNSUB_BODY = re.compile(r"^\s*(please\s+)?(stop|unsubscribe|remove me|opt[- ]?out|take me off|do not (contact|email))(?=\s*$|\s*[.!,;:]|\s+(?:emailing|contacting|sending|messaging|texting|calling|me|us|this|these|my|please|now|immediately|all|the|from|it)\b)", re.I)
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


QUOTE_START = re.compile(r"(?im)^(>.*|on .{5,120} wrote:\s*|-{2,}\s*original message\s*-{2,}.*|from:\s.+sent:\s.+|_{5,}\s*)$")


def strip_quoted(text: str) -> str:
    """Their own words only: everything from the first quoted line ("> ..." or "On Mon, ... wrote:") on is the earlier thread and is cut."""
    m = QUOTE_START.search(text or "")
    body = (text[: m.start()] if m else text or "").strip()
    return re.sub(r"\n{3,}", "\n\n", body)


def classify(raw: bytes, leads: set[str]) -> dict | None:
    """Reads one message: a reply, a bounce or an unsubscribe request from one of YOUR leads, or None (auto-replies and everything else are ignored)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    sender = email.utils.parseaddr(str(msg.get("From", "")))[1].lower()
    subject = re.sub(r"\s+", " ", str(msg.get("Subject", ""))).strip()
    text = _text_of(msg)
    try:
        when = _parse_ts(email.utils.parsedate_to_datetime(str(msg["Date"])).isoformat()) if msg.get("Date") else None
    except (TypeError, ValueError, IndexError):
        when = None
    base = {"subject": subject[:300], "received_at": (when or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"), "message_id": str(msg.get("Message-ID", "")).strip()[:300]}
    local = sender.split("@")[0]
    ctype = (msg.get_content_type() or "").lower()
    rtype = str(msg.get_param("report-type") or "").lower()
    if "report" in ctype and rtype and rtype != "delivery-status":
        return None                                      # a read receipt or another kind of report: not a failure
    raw_text = raw.decode("utf-8", "ignore")
    if rtype == "delivery-status" and re.search(r"^Action:\s*(delayed|delivered|relayed|expanded)", raw_text, re.I | re.M) and not re.search(r"^Action:\s*failed", raw_text, re.I | re.M):
        return None                                      # "your email is delayed" or "delivered": nothing failed
    if local in ("mailer-daemon", "postmaster") or "delivery-status" in ctype or "report" in ctype or BOUNCE_SUBJECT.search(subject):
        found = [a.lower() for a in ADDR.findall(text) if a.lower() in leads]
        if not found:
            return None
        return {**base, "kind": "bounce", "from_email": found[0], "snippet": re.sub(r"\s+", " ", text).strip()[:300]}
    auto = str(msg.get("Auto-Submitted", "no")).lower() != "no" or msg.get("X-Autoreply") or msg.get("X-Autorespond") or str(msg.get("Precedence", "")).lower() in ("auto_reply", "bulk", "junk") or AUTO_SUBJECT.search(subject)
    if auto or sender not in leads:
        return None
    own = strip_quoted(text)
    first = own[:300]
    kind = "unsubscribe" if UNSUB_BODY.search(first) or re.match(r"^\s*(unsubscribe|stop)\s*$", subject, re.I) else "reply"
    return {**base, "kind": kind, "from_email": sender, "snippet": re.sub(r"\s+", " ", first)[:600], "body": own[:6000]}


MAX_NEW_PER_POLL = G.MAX_NEW
Batch = G.Batch            # new messages found by one read; .capped is True when there were more than the cap (the next pass carries on)


def fetch_new(m: dict, password: str, since: dt.date, seen: set[str], connect=None) -> list[tuple[str, bytes]]:
    """New messages in the inbox since a date, without marking anything as read."""
    if G.is_cloud(password):
        return G.fetch_new(m, since, seen)
    connect = connect or (lambda: imaplib.IMAP4_SSL(m["imap_host"], int(m["imap_port"]), ssl_context=ssl.create_default_context(), timeout=H.TIMEOUT))
    box = connect()
    out = Batch()
    try:
        O.imap_auth(box, m, password)
        box.select("INBOX", readonly=True)
        typ, data = box.search(None, "SINCE", since.strftime("%d-%b-%Y"))
        for num in (data[0].split() if typ == "OK" and data and data[0] else [])[-2000:]:       # oldest first, so the oldest unseen mail is never the part that is dropped
            if len(out) >= MAX_NEW_PER_POLL:
                out.capped = True
                break
            typ, parts = box.fetch(num, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.14000>)")
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
            batch = fetch(m, secrets[m["id"]], since, seen)
            for key, raw in batch:
                seen.add(key)
                ev = classify(raw, leads)
                if ev:
                    events.append({**ev, "mailbox_id": m["id"]})
            if getattr(batch, "capped", False):
                out(f"Herald: {m['email']} has more than {MAX_NEW_PER_POLL} new messages: the rest are read on the next pass.")
            else:
                polled[m["id"]] = now.isoformat(timespec="seconds")      # only moved forward when everything in the window was read
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
    pw = H.get_secret(m["id"]) or G.cloud_if_signed(m["id"])
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
