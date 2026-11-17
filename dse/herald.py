"""Herald (phase 1): your sending mailboxes on this PC.

Herald is the campaign platform inside Citadel. Phase 1 connects the mailboxes you send from:

    python dse.py herald list                      your mailboxes (from Citadel) and whether a password is set here
    python dse.py herald secret <address|id>       type a mailbox's password or app password (asked here, hidden, never printed)
    python dse.py herald test <address|id|all>     try the SMTP (sending) and IMAP (reading) logins, and report the result to Citadel
    python dse.py herald forget <address|id>       delete a stored password
    python dse.py herald send [--dry]              one sending pass now (the runner does this every minute); --dry sends nothing
    python dse.py herald sendtest <mailbox> <to>   send ONE test email to an address you choose
    python dse.py herald pause | resume            stop or restart all sending on this PC

THE PASSWORD STAYS ON THIS PC. Citadel only holds a mailbox's settings (address, mail servers, limits). A password is asked for here, stored in data/herald/secrets.dat under
Windows' own protection (DPAPI: only this Windows user on this PC can read it), and only ever used to log in to YOUR mail server. It is never written to a log, a CSV, a
Citadel table or a message. data/ is not in Git. Stdlib only.
"""
from __future__ import annotations

import base64
import datetime as dt
import getpass
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "herald"
MAILBOXES = DATA / "mailboxes.json"      # the settings pulled from Citadel (no secrets)
SECRETS = DATA / "secrets.dat"           # passwords, protected
STATUS = DATA / "status.json"            # the last test of each mailbox (no secrets)
TIMEOUT = 20
EMAIL_RX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


# ------------------------------------------------------------------ protecting the passwords

def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows Data Protection API through ctypes: tied to this Windows user on this PC."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    src = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("Windows could not protect or open the stored passwords (they belong to another Windows user or PC).")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    if os.name == "nt":
        return b"DPAPI1:" + _dpapi(data, True)
    return b"PLAIN1:" + base64.b64encode(data)      # not Windows: stored as is, file mode 600 (said plainly by `herald secret`)


def unprotect(blob: bytes) -> bytes:
    if blob.startswith(b"DPAPI1:"):
        return _dpapi(blob[7:], False)
    if blob.startswith(b"PLAIN1:"):
        return base64.b64decode(blob[7:])
    raise ValueError("The password file is not in a known format.")


def _read_secrets() -> dict[str, str]:
    if not SECRETS.exists():
        return {}
    try:
        data = json.loads(unprotect(SECRETS.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _write_secrets(d: dict[str, str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    SECRETS.write_bytes(protect(json.dumps(d).encode("utf-8")))
    try:
        os.chmod(SECRETS, 0o600)
    except OSError:
        pass


def has_secret(mailbox_id: str) -> bool:
    return bool(_read_secrets().get(mailbox_id))


def set_secret(mailbox_id: str, password: str) -> None:
    if not password or len(password) > 200 or "\n" in password:
        raise ValueError("That does not look like a password.")
    d = _read_secrets()
    d[mailbox_id] = password
    _write_secrets(d)


def forget_secret(mailbox_id: str) -> bool:
    d = _read_secrets()
    if mailbox_id not in d:
        return False
    del d[mailbox_id]
    _write_secrets(d)
    return True


def get_secret(mailbox_id: str) -> str | None:
    """For the sending engine only (a later phase). Never print the result."""
    return _read_secrets().get(mailbox_id)


# ------------------------------------------------------------------ the mailboxes

def load_mailboxes() -> list[dict]:
    if not MAILBOXES.exists():
        return []
    try:
        data = json.loads(MAILBOXES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [m for m in data if isinstance(m, dict) and m.get("id") and EMAIL_RX.match(str(m.get("email", "")))] if isinstance(data, list) else []


def save_mailboxes(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    MAILBOXES.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find(ref: str) -> dict:
    """A mailbox by address or id (any case); says what to do when it is not there."""
    ref = (ref or "").strip().lower()
    rows = load_mailboxes()
    hit = [m for m in rows if m["email"].lower() == ref or str(m["id"]).lower() == ref]
    if not hit:
        have = ", ".join(m["email"] for m in rows) or "none yet"
        raise ValueError(f"I do not know a mailbox '{ref}'. Add it in Citadel (Herald > Mailboxes) and wait a minute for it to arrive here. Mailboxes here: {have}.")
    return hit[0]


# ------------------------------------------------------------------ testing a mailbox

def _scrub(text: str, password: str | None) -> str:
    t = re.sub(r"\s+", " ", str(text)).strip()
    return t.replace(password, "[hidden]") if password else t


def explain(e: Exception, provider: str = "") -> str:
    """A plain reason for a failed login or connection, with what to try."""
    s = str(e)
    low = s.lower()
    if isinstance(e, smtplib.SMTPAuthenticationError) or "authentication" in low or "invalid credentials" in low or "auth" in low and "fail" in low:
        tip = {"google": " Gmail needs an App Password (Google account > Security > 2-Step Verification > App passwords), not your normal password.",
               "microsoft": " Microsoft 365 may need SMTP AUTH switched on for the mailbox, or an app password if two-step sign-in is on.",
               "yahoo": " Yahoo needs an app password (Account security > Generate app password)."}.get(provider, " Check the password, and whether your provider needs an app password for outside apps.")
        return "The mail server refused the login." + tip
    if isinstance(e, (socket.gaierror,)) or "name or service not known" in low or "getaddrinfo" in low:
        return "That mail server name was not found. Check the host name."
    if isinstance(e, (socket.timeout, TimeoutError)) or "timed out" in low:
        return "The mail server did not answer in time. Check the host, the port and your internet."
    if isinstance(e, ssl.SSLError) or "ssl" in low or "wrong version" in low:
        return "The secure connection failed. Try the other security option (SSL on 465, or STARTTLS on 587) for this server."
    if isinstance(e, ConnectionRefusedError) or "refused" in low:
        return "The server refused the connection. Check the port."
    return "Could not connect: " + s[:160]


def _smtp_login(m: dict, password: str) -> None:
    ctx = ssl.create_default_context()
    if m.get("smtp_security", "ssl") == "ssl":
        with smtplib.SMTP_SSL(m["smtp_host"], int(m["smtp_port"]), timeout=TIMEOUT, context=ctx) as s:
            s.login(m.get("username") or m["email"], password)
    else:
        with smtplib.SMTP(m["smtp_host"], int(m["smtp_port"]), timeout=TIMEOUT) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(m.get("username") or m["email"], password)


def _imap_login(m: dict, password: str) -> None:
    ctx = ssl.create_default_context()
    box = imaplib.IMAP4_SSL(m["imap_host"], int(m["imap_port"]), ssl_context=ctx, timeout=TIMEOUT)
    try:
        box.login(m.get("username") or m["email"], password)
    finally:
        try:
            box.logout()
        except Exception:
            pass


def test_mailbox(m: dict, password: str | None = None) -> dict:
    """Logs in to the mailbox's sending (SMTP) and reading (IMAP) servers. Sends nothing and reads nothing. Never returns or prints the password."""
    pw = password if password is not None else get_secret(m["id"])
    if not pw:
        return {"status": "new", "secret_set": False, "smtp": None, "imap": None, "note": f"No password is set on this PC yet. Run: python dse.py herald secret {m['email']}"}
    out = {"secret_set": True, "smtp": None, "imap": None}
    problems = []
    for name, fn in (("smtp", _smtp_login), ("imap", _imap_login)):
        try:
            fn(m, pw)
            out[name] = True
        except Exception as e:                   # a failed login is a result, not a crash
            out[name] = False
            problems.append(f"{'Sending (SMTP)' if name == 'smtp' else 'Reading (IMAP)'}: {_scrub(explain(e, m.get('provider', '')), pw)}")
    out["status"] = "ready" if out["smtp"] and out["imap"] else "error"
    out["note"] = "Both logins worked: this mailbox can send and read." if out["status"] == "ready" else " ".join(problems)
    return out


# ------------------------------------------------------------------ status

def _load_status() -> dict:
    try:
        d = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def record_test(mailbox_id: str, result: dict) -> None:
    d = _load_status()
    d[mailbox_id] = {"status": result["status"], "note": result["note"][:400], "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    DATA.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


def status_payload(rows: list[dict] | None = None) -> dict:
    """What is reported to Citadel: for each mailbox, whether a password is set here and the last test. No secrets."""
    rows = load_mailboxes() if rows is None else rows
    last = _load_status()
    secrets = _read_secrets()
    out = {}
    for m in rows:
        t = last.get(m["id"], {})
        have = bool(secrets.get(m["id"]))
        status = t.get("status", "new") if have else "new"
        note = t.get("note", "") if have else f"No password set on this PC yet. Run: python dse.py herald secret {m['email']}"
        if have and not t:
            note = "A password is set on this PC. Run the test to check the logins."
        out[m["id"]] = {"status": status, "note": note, "secret_set": have, **({"checked_at": t["checked_at"]} if t.get("checked_at") and have else {})}
    return out


# ------------------------------------------------------------------ command line

def cli(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd in ("send", "sendtest", "pause", "resume"):
        from . import herald_send as S
        try:
            if cmd == "pause":
                print(S.pause()); return 0
            if cmd == "resume":
                print(S.resume()); return 0
            if cmd == "sendtest":
                if len(rest) < 2:
                    print("python dse.py herald sendtest <mailbox address> <send the test to this address>")
                    return 1
                print(S.send_test(rest[0], rest[1])); return 0
            sys.path.insert(0, str(ROOT / "bridge"))
            import herald_sync
            s = S.run_pass(herald_sync._api(), dry="--dry" in rest)
            if "--dry" in rest or s["held"]:
                for why, n in sorted(s["held"].items(), key=lambda x: -x[1]):
                    print(f"held: {n} email(s): {why}")
            print(f"checked {s['checked']} due email(s); sent {s['sent']}; events from your inboxes: {s['events']}")
            return 0
        except (ValueError, RuntimeError) as e:
            print(e); return 1
    if cmd == "list":
        rows = load_mailboxes()
        if not rows:
            print("No mailboxes here yet. Add one in Citadel (Herald > Mailboxes); it arrives within a minute.")
            return 0
        pay = status_payload(rows)
        for m in rows:
            s = pay[m["id"]]
            print(f"{m['email']}  password: {'set' if s['secret_set'] else 'NOT SET'}  status: {s['status']}  limit: {m.get('daily_limit', '?')} a day")
        return 0
    if cmd in ("secret", "forget", "test"):
        if not rest:
            print(f"Which mailbox? python dse.py herald {cmd} <address>" + (" (or: all)" if cmd == "test" else ""))
            return 1
        try:
            if cmd == "test" and rest[0].lower() == "all":
                targets = load_mailboxes()
                if not targets:
                    print("No mailboxes here yet.")
                    return 1
            else:
                targets = [find(rest[0])]
        except ValueError as e:
            print(e)
            return 1
        if cmd == "secret":
            m = targets[0]
            print(f"Password for {m['email']} ({m['smtp_host']}).")
            if m.get("provider") == "google":
                print("Gmail: use an App Password (Google account > Security > 2-Step Verification > App passwords), not your normal password.")
            if os.name != "nt":
                print("Note: this is not Windows, so the password is stored in a file only you can read, not under Windows protection.")
            pw = getpass.getpass("Type it (nothing shows while you type): ")
            try:
                set_secret(m["id"], pw)
            except ValueError as e:
                print(e)
                return 1
            print("Saved on this PC only. Now test it: python dse.py herald test " + m["email"])
            return 0
        if cmd == "forget":
            print("Deleted the password for " + targets[0]["email"] + "." if forget_secret(targets[0]["id"]) else "There was no password stored for " + targets[0]["email"] + ".")
            return 0
        bad = 0
        for m in targets:
            r = test_mailbox(m)
            if r["secret_set"]:
                record_test(m["id"], r)
            print(f"{m['email']}: {r['status'].upper()}  {r['note']}")
            bad += r["status"] != "ready"
        try:                                     # tell Citadel now rather than at the next sync
            sys.path.insert(0, str(ROOT / "bridge"))
            import herald_sync
            herald_sync.push_status()
        except Exception as e:
            print(f"(Citadel was not told yet: {e}. The next sync will.)")
        return 1 if bad else 0
    print(f"Unknown command '{cmd}'. Try: list, secret, test, forget, send, sendtest, pause, resume")
    return 1
