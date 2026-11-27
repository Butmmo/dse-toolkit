"""Email verification: give every address on a list a verdict, a reason and a date.

    python dse.py verify leads.csv [--max 200] [--from you@yourdomain.com] [--refresh]

Four verdicts, in plain words:
  valid    the domain takes mail and its server accepted this address
  risky    the address might work, but something real is wrong: the server accepts
           every address at the domain (catch-all), or the domain is a throwaway
           email service
  invalid  the address cannot receive mail: the format is wrong, the domain has
           no mail servers, or the server said the address does not exist
  unknown  this PC could not get an answer (the server was unreachable, it asked
           us to try again later, or the lookup failed). Unknown is never
           dressed up as invalid.

How it checks, cheapest first:
  syntax   the address is written in a valid format
  domain   the domain is not a known throwaway service, and it publishes mail
           servers (MX, looked up with nslookup, the same way preflight does)
  mailbox  one short SMTP conversation per domain: the server is asked about a
           made-up address first (the catch-all check), then about each real
           address. No message is ever sent: the conversation ends before any
           content exists.

The probe introduces itself with the sender address you give it (--from; your
real sending address gets the most honest answers). With no sender it uses an
empty return path, which some servers refuse; those addresses come back
unknown, never invalid.

Results land in three new columns (email_verdict, email_verdict_reason,
email_verified_at). Your columns are never touched. Rows verified in the last
30 days are left alone unless --refresh is given. The send-list preflight
reads the verdicts: invalid blocks the row, risky warns.
"""
from __future__ import annotations

import datetime as dt
import random
import re
import smtplib
import string
import subprocess
import time
from pathlib import Path

from . import importer
from .common import ROOT, write_csv

VERDICTS = ("valid", "risky", "invalid", "unknown")
VERDICT_COLUMNS = ["email_verdict", "email_verdict_reason", "email_verified_at"]
FRESH_DAYS = 30
PROBE_TIMEOUT = 10
EHLO_NAME = "verify.dbicitadel.app"

ROLE_LOCALS = {
    "info", "admin", "sales", "support", "hello", "contact", "office",
    "enquiries", "inquiries", "team", "help", "service", "services",
    "booking", "bookings", "reception", "accounts", "billing", "marketing",
    "press", "jobs", "careers", "hr", "webmaster", "postmaster", "mail",
    "general",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamailblock.com",
    "10minutemail.com", "tempmail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "getnada.com", "maildrop.cc", "dispostable.com",
    "fakeinbox.com", "sharklasers.com", "throwawaymail.com", "mailnesia.com",
    "mintemail.com", "mytemp.email", "mohmal.com", "emailondeck.com",
}

_LOCAL_OK = re.compile(r"^[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~.]+$")
_LABEL_OK = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")


def syntax_ok(addr: str) -> bool:
    a = (addr or "").strip()
    if not a or len(a) > 254 or a.count("@") != 1:
        return False
    local, domain = a.rsplit("@", 1)
    if not local or len(local) > 64 or not _LOCAL_OK.match(local):
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    labels = domain.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2 or not labels[-1].isalpha():
        return False
    return all(_LABEL_OK.match(x) for x in labels)


def domain_of(addr: str) -> str:
    a = (addr or "").strip().lower()
    return a.rsplit("@", 1)[1] if "@" in a else ""


def mx_hosts(domain: str, runner=subprocess.run) -> list[str] | None:
    """The domain's mail servers, best first. [] = none exist, None = lookup failed."""
    try:
        r = runner(["nslookup", "-type=MX", domain], capture_output=True, timeout=12, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.decode("utf-8", "replace").lower()
    found: list[tuple[int, str]] = []
    for line in out.splitlines():
        m = re.search(r"mail exchanger\s*=\s*([a-z0-9.\-]+)", line)
        if not m:
            continue
        p = re.search(r"preference\s*=\s*(\d+)", line)
        found.append((int(p.group(1)) if p else 10, m.group(1).rstrip(".")))
    if found:
        return [host for _pref, host in sorted(set(found))]
    if "non-existent" in out or "can't find" in out or "no answer" in out or "no mx" in out:
        return []
    return None


def _smtp_connect(host: str, timeout: int = PROBE_TIMEOUT):
    s = smtplib.SMTP(host, 25, timeout=timeout)
    try:
        s.ehlo(EHLO_NAME)
    except smtplib.SMTPException:
        s.helo(EHLO_NAME)
    return s


def probe_domain(domain: str, hosts: list[str], addresses: list[str], sender: str = "",
                 connect=_smtp_connect, rng: random.Random | None = None) -> dict:
    """One SMTP conversation for a whole domain. Never sends a message."""
    rng = rng or random.Random()
    result: dict = {"reachable": False, "catch_all": None, "codes": {}}
    session = None
    for host in hosts:
        try:
            session = connect(host)
            break
        except (OSError, smtplib.SMTPException):
            session = None
    if session is None:
        return result
    result["reachable"] = True
    try:
        try:
            session.mail(sender or "")
        except (OSError, smtplib.SMTPException):
            pass  # some servers only judge at RCPT time
        made_up = "dse-verify-" + "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(12)) + "@" + domain
        try:
            code, _msg = session.rcpt(made_up)
            if code in (250, 251):
                result["catch_all"] = True
            elif code in (550, 551, 553):
                result["catch_all"] = False
        except (OSError, smtplib.SMTPException):
            result["catch_all"] = None
        for addr in addresses:
            try:
                code, _msg = session.rcpt(addr)
                result["codes"][addr] = code
            except (OSError, smtplib.SMTPException):
                result["codes"][addr] = None
    finally:
        try:
            session.quit()
        except Exception:
            pass
    return result


def compose(addr: str, mx: list[str] | None, probe: dict | None) -> tuple[str, str]:
    """(verdict, reason) for one address, from the syntax, MX and probe results."""
    a = (addr or "").strip()
    if not syntax_ok(a):
        return "invalid", "not a valid email format"
    local, domain = a.rsplit("@", 1)
    domain = domain.lower()
    if domain in DISPOSABLE_DOMAINS:
        return "risky", "the domain is a throwaway email service"
    if mx is None:
        return "unknown", "the mail server lookup failed from this PC"
    if not mx:
        return "invalid", "the domain has no mail servers, so it cannot receive email"
    if probe is None or not probe.get("reachable"):
        return "unknown", "the mail server could not be reached from this PC"
    code = probe.get("codes", {}).get(a)
    if code is None:
        verdict, reason = "unknown", "the mail server did not answer the check"
    elif code in (250, 251):
        if probe.get("catch_all"):
            verdict, reason = "risky", "the server accepts every address at this domain, so this one cannot be confirmed"
        else:
            verdict, reason = "valid", "the mail server accepted this address"
    elif code in (550, 551, 553):
        verdict, reason = "invalid", "the mail server said this address does not exist"
    elif 400 <= code < 500:
        verdict, reason = "unknown", "the mail server asked us to try again later"
    else:
        verdict, reason = "unknown", "the mail server refused the check"
    if local.lower() in ROLE_LOCALS and verdict in ("valid", "risky"):
        reason += " (role address: replies may reach a team inbox)"
    return verdict, reason


def _fresh(value: object, today: dt.date) -> bool:
    try:
        d = dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return False
    return 0 <= (today - d).days < FRESH_DAYS


def verify_rows(rows: list[dict], email_col: str, *, sender: str = "", today: dt.date | None = None,
                refresh: bool = False, mx_lookup=mx_hosts, connect=_smtp_connect,
                sleep=time.sleep, rng: random.Random | None = None) -> dict:
    """Add the verdict columns to rows in place. Returns counts per verdict."""
    today = today or dt.date.today()
    counts: dict = {v: 0 for v in VERDICTS}
    counts["skipped"] = 0
    counts["blank"] = 0
    pending: dict[str, list[tuple[dict, str]]] = {}
    for row in rows:
        addr = (row.get(email_col) or "").strip()
        if not addr:
            counts["blank"] += 1
            continue
        if not refresh and (row.get("email_verdict") or "").strip() and _fresh(row.get("email_verified_at"), today):
            counts["skipped"] += 1
            continue
        pending.setdefault(domain_of(addr), []).append((row, addr))
    for domain, items in pending.items():
        good = [(row, addr) for row, addr in items if syntax_ok(addr)]
        if domain in DISPOSABLE_DOMAINS:
            mx, probe = None, None  # every address there is risky; no network needed
            for row, addr in items:
                verdict, reason = compose(addr, mx, probe)
                row["email_verdict"] = verdict
                row["email_verdict_reason"] = reason
                row["email_verified_at"] = today.isoformat()
                counts[verdict] += 1
            continue
        mx = mx_lookup(domain) if domain and good else None
        probe = None
        if mx:
            probe = probe_domain(domain, mx, sorted({addr for _row, addr in good}),
                                 sender=sender, connect=connect, rng=rng)
        for row, addr in items:
            verdict, reason = compose(addr, mx, probe)
            row["email_verdict"] = verdict
            row["email_verdict_reason"] = reason
            row["email_verified_at"] = today.isoformat()
            counts[verdict] += 1
        if sleep is not None:
            sleep(0.2)
    return counts


def find_email_column(headers: list[str], rows: list[dict]) -> str:
    lows = {h.lower().strip(): h for h in headers}
    for want in ("best_email", "email", "email_address", "e-mail", "work_email", "contact_email"):
        if want in lows:
            return lows[want]
    for h in headers:
        if "email" in h.lower():
            return h
    raise ValueError("That list has no email column to verify. Enrich it first (the website lane finds emails), or put the addresses under a column named Email.")


def verify_file(src: str, max_rows: int = 200, out: str = "", sender: str = "", refresh: bool = False,
                today: dt.date | None = None, say=print, **kw) -> str:
    """Verify a CSV on disk and write the result next to it. Returns the output path."""
    p = Path(src)
    if not p.is_absolute():
        p = (ROOT / src) if (ROOT / src).exists() else p
    if not p.is_file():
        raise ValueError(f"I could not find the file: {src}")
    headers, rows = importer.read_rows(p)
    if not rows:
        raise ValueError("That file has no rows.")
    col = find_email_column(headers, rows)
    work = rows[:max_rows] if max_rows else rows
    counts = verify_rows(work, col, sender=sender, today=today, refresh=refresh, **kw)
    dest = Path(out) if out else p.with_name(p.stem + "-verified.csv")
    write_csv(dest, rows, first=list(headers))
    say(f"Email verification: {counts['valid']} valid, {counts['risky']} risky, "
        f"{counts['invalid']} invalid, {counts['unknown']} unknown, "
        f"{counts['skipped']} left as they were (checked in the last {FRESH_DAYS} days), "
        f"{counts['blank']} rows with no email.")
    say("The verdicts are in the email_verdict column, each with its reason and the date checked. "
        "The send-list preflight blocks invalid addresses and warns on risky ones.")
    return str(dest)
