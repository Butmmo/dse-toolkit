"""Herald warmup, phase 6: the ramp and the opt-in exchange (runs on your PC, inside the sending pass).

THE RAMP. A mailbox with "warm this mailbox up" on may send at most 5 emails on its first day and 2 more each day after (5, 7, 9 ...), never above the daily limit you set. Citadel keeps
the start date; this module turns it into the limit the sender uses (effective_limit).

THE EXCHANGE (only for mailboxes you opted in). Citadel pairs your mailbox with another member's. This PC sends the short message Citadel wrote, and answers the messages other members'
PCs sent to you: it finds the message by its exact Message-ID, rescues it from the spam folder if it landed there (that is what tells the provider the mail is wanted), marks it read and
answers it. It touches only those exact messages, never any other mail. The words come only from Citadel's lists; nothing else can be sent through the exchange.

Nothing here runs when the PAUSE file exists or the mailbox is paused. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import email
import email.policy
import email.utils
import imaplib
import random
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage

from . import herald as H
from . import herald_send as S
from . import herald_oauth as O

RAMP_START = 5
RAMP_STEP = 2
EXCHANGE_CAP = 20
MIN_REPLY_AGE_MIN = 5            # a real person does not answer in the same second
MISSING_AFTER_MIN = 24 * 60      # not in the inbox or the spam folder after a day: it did not arrive
SPAM_FOLDERS = ("[Gmail]/Spam", "Spam", "Junk", "Junk Email", "INBOX.Junk", "INBOX.Spam", "Junk E-mail")
SKIP_ODDS = 0.6                  # most passes do nothing, so exchange mail does not arrive on a one-minute beat


def ramp(day: int) -> int:
    """Emails a warming mailbox may send on its Nth day (0 is the first day)."""
    return RAMP_START + RAMP_STEP * max(0, int(day))


def effective_limit(daily_limit: int, plan: dict | None) -> int:
    """The limit the sender applies today: the member's own limit, or the ramp if that is lower and warmup is on."""
    if plan and plan.get("warmup"):
        return max(1, min(int(daily_limit), ramp(int(plan.get("day", 0)))))
    return int(daily_limit)


def get_plan(api) -> dict:
    """The ramp and pool state for each mailbox. Empty when Citadel has not been updated yet (nothing is limited then)."""
    try:
        p = api.rpc("hq_herald_warm_plan", {})
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def apply_ramp(due: list[dict], plan: dict) -> int:
    """Lowers each due email's mailbox limit to today's ramp. Returns how many mailboxes are held below their own limit."""
    held = set()
    for it in due:
        m = it["mailbox"]
        lim = effective_limit(int(m["daily_limit"]), plan.get(m["id"]))
        if lim < int(m["daily_limit"]):
            held.add(m["id"])
        m["daily_limit"] = lim
    return len(held)


def in_window(m: dict, now: dt.datetime) -> bool:
    tz = S.tz_of(m.get("timezone", "UTC"))
    if tz is None:
        return False
    local = now.astimezone(tz)
    return S.DOW[local.weekday()] in m.get("send_days", S.DOW[:5]) and S._hm(m["window_start"]) <= local.time().replace(second=0, microsecond=0) < S._hm(m["window_end"])


def _msg(m: dict, to: str, subject: str, body: str, now: dt.datetime, reply_to: dict | None = None) -> EmailMessage:
    msg = EmailMessage()
    name = (m.get("display_name") or "").strip()
    msg["From"] = email.utils.formataddr((name, m["email"])) if name else m["email"]
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.format_datetime(now)
    msg["Message-ID"] = email.utils.make_msgid(domain=m["email"].split("@")[1])
    if reply_to and reply_to.get("message_id"):
        msg["In-Reply-To"] = reply_to["message_id"]
        msg["References"] = reply_to["message_id"]
    msg.set_content(body)
    return msg


def send_warm(api, now: dt.datetime, plan: dict, secrets: dict, send=S._smtp_send, rng=random.random, out=print) -> int:
    """At most one exchange email per opted-in mailbox per pass (and most passes none), inside the mailbox's own window."""
    results, sent = [], 0
    owed_ids = S.journal_flush(api, "warm", "hq_herald_warm_report", "p_results", out)
    for m in H.load_mailboxes():
        p = plan.get(m["id"]) or {}
        if not p.get("warm_pool") or m.get("paused") or not secrets.get(m["id"]) or not in_window(m, now) or rng() < SKIP_ODDS:
            continue
        job = api.rpc("hq_herald_warm_next", {"p_mailbox": m["id"]})
        if not isinstance(job, dict) or not job.get("to_email") or str(job.get("id")) in owed_ids:
            continue
        try:
            msg = _msg(m, job["to_email"], job["subject"], job["body"], now)
        except ValueError:
            results.append({"id": job["id"], "status": "failed"})
            continue
        try:
            send(m, secrets[m["id"]], msg)
            results.append({"id": job["id"], "status": "sent", "message_id": msg["Message-ID"]})
            S.journal_save("warm", [r for r in results if r["status"] == "sent"])      # written down before Citadel is told
            sent += 1
            S._extra_add(m["id"], now)
        except (smtplib.SMTPException, socket.timeout, TimeoutError, ConnectionError, OSError, ssl.SSLError) as e:
            results.append({"id": job["id"], "status": "failed"})
            out(f"Herald warmup: could not send from {m['email']}: {H._scrub(H.explain(e, m.get('provider', '')), secrets[m['id']])}")
        S._log({"at": now.isoformat(timespec="seconds"), "to": "(exchange)", "from": m["email"], "step": 0, "result": results[-1]["status"], "error": "", "kind": "warmup"})
    if results:
        try:
            api.rpc("hq_herald_warm_report", {"p_results": results})
            S.journal_save("warm", [])
        except Exception:
            out("Citadel could not be told about the warmup sends yet: they are remembered on this PC and reported next minute (nothing is sent twice).")
    return sent


def _imap(m: dict, password: str):
    box = imaplib.IMAP4_SSL(m["imap_host"], int(m["imap_port"]), ssl_context=ssl.create_default_context(), timeout=H.TIMEOUT)
    O.imap_auth(box, m, password)
    return box


def find_and_rescue(box, message_id: str, spam_folders=SPAM_FOLDERS) -> tuple[bool, bool]:
    """Looks for the exact message. (found, rescued): in the inbox it is marked read; in a spam folder it is moved to the inbox first. Touches nothing else."""
    mid = message_id.strip()
    if not re.fullmatch(r"<[^<>\s]{3,300}>", mid):
        return False, False
    crit = ("HEADER", "Message-ID", mid)
    box.select("INBOX")
    typ, data = box.search(None, *crit)
    if typ == "OK" and data and data[0]:
        for num in data[0].split():
            box.store(num, "+FLAGS", "\\Seen")
        return True, False
    for folder in spam_folders:
        try:
            if box.select(f'"{folder}"')[0] != "OK":
                continue
        except imaplib.IMAP4.error:
            continue
        typ, data = box.search(None, *crit)
        if typ != "OK" or not data or not data[0]:
            continue
        for num in data[0].split():
            if box.copy(num, "INBOX")[0] == "OK":
                box.store(num, "+FLAGS", "\\Deleted")
        box.expunge()
        box.select("INBOX")
        typ, data = box.search(None, *crit)
        for num in (data[0].split() if typ == "OK" and data and data[0] else []):
            box.store(num, "+FLAGS", "\\Seen")
        return True, True
    return False, False


def answer_warm(api, now: dt.datetime, secrets: dict, send=S._smtp_send, connect=_imap, out=print) -> int:
    """Finds the exchange messages other members sent to this PC's mailboxes, rescues them from spam, marks them read and answers them."""
    owed_ids = S.journal_flush(api, "warm", "hq_herald_warm_report", "p_results", out)      # first: so the list below no longer holds exchange mail that was already answered
    try:
        items = api.rpc("hq_herald_warm_inbox", {})
    except Exception:
        return 0
    if not isinstance(items, list) or not items:
        return 0
    boxes = {m["id"]: m for m in H.load_mailboxes()}
    results, answered = [], 0
    for it in items:
        if str(it.get("id")) in owed_ids:
            continue
        m = boxes.get(it["to_mailbox_id"])
        if not m or m.get("paused") or not secrets.get(m["id"]):
            continue
        if it.get("age_minutes", 0) < MIN_REPLY_AGE_MIN:
            continue
        try:
            box = connect(m, secrets[m["id"]])
            try:
                found, rescued = find_and_rescue(box, it["message_id"])
            finally:
                try:
                    box.logout()
                except Exception:
                    pass
        except Exception as e:
            out(f"Herald warmup: could not read {m['email']}: {H._scrub(H.explain(e, m.get('provider', '')), secrets[m['id']])}")
            continue
        if not found:
            if it.get("age_minutes", 0) >= MISSING_AFTER_MIN:
                results.append({"id": it["id"], "status": "missing"})
            continue
        subj = it["subject"] if re.match(r"(?i)re:", it["subject"]) else "Re: " + it["subject"]
        try:
            msg = _msg(m, it["from_email"], subj, it["reply_body"] or "Thank you.", now, {"message_id": it["message_id"]})
        except ValueError:
            continue
        try:
            send(m, secrets[m["id"]], msg)
            results.append({"id": it["id"], "status": "replied", "reply_message_id": msg["Message-ID"], "rescued": rescued})
            S.journal_save("warm", [r for r in results if r["status"] == "replied"])      # written down before Citadel is told
            answered += 1
            S._extra_add(m["id"], now)
        except (smtplib.SMTPException, socket.timeout, TimeoutError, ConnectionError, OSError, ssl.SSLError):
            continue          # try again next pass
        S._log({"at": now.isoformat(timespec="seconds"), "to": "(exchange)", "from": m["email"], "step": 0, "result": "replied", "error": "", "kind": "warmup"})
    if results:
        try:
            api.rpc("hq_herald_warm_report", {"p_results": results})
            S.journal_save("warm", [])
        except Exception:
            out("Citadel could not be told about the warmup answers yet: they are remembered on this PC and reported next minute (nothing is sent twice).")
    return answered
