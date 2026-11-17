"""Tests for Herald phase 1: mailboxes, passwords that stay on this PC, connection tests, status.   python tests/test_herald.py"""
import contextlib
import io
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

PW = "hunter2-app-password-XYZ"
G = {"id": "11111111-aaaa-bbbb-cccc-000000000001", "email": "Ada@Example.com", "provider": "google", "username": "Ada@Example.com", "smtp_host": "smtp.gmail.com", "smtp_port": 465,
     "smtp_security": "ssl", "imap_host": "imap.gmail.com", "imap_port": 993, "daily_limit": 30}
M2 = {"id": "22222222-aaaa-bbbb-cccc-000000000002", "email": "bob@example.org", "provider": "custom", "username": "bob", "smtp_host": "mail.example.org", "smtp_port": 587,
      "smtp_security": "starttls", "imap_host": "mail.example.org", "imap_port": 993, "daily_limit": 20}

try:
    # ---- the protected password file
    blob = H.protect(b"secret")
    check("protecting and opening a value round-trips", H.unprotect(blob) == b"secret" and blob != b"secret")
    try:
        H.unprotect(b"JUNK:abc")
        refused = False
    except ValueError:
        refused = True
    check("a file in an unknown format is refused", refused)

    H.set_secret(G["id"], PW)
    raw = H.SECRETS.read_bytes()
    check("the password is stored, but never as readable text in the file", PW.encode() not in raw and PW.encode() not in raw.replace(b"=", b"") and H.has_secret(G["id"]) and H.get_secret(G["id"]) == PW)
    H.set_secret(M2["id"], "other-pass-1")
    check("several mailboxes each keep their own password", H.get_secret(M2["id"]) == "other-pass-1" and H.get_secret(G["id"]) == PW)
    check("a password can be forgotten, and forgetting twice says so", H.forget_secret(M2["id"]) is True and H.forget_secret(M2["id"]) is False and not H.has_secret(M2["id"]))
    for bad in ("", "x" * 201, "line1\nline2"):
        try:
            H.set_secret("z", bad)
            ok = False
        except ValueError:
            ok = True
        check(f"a bad password is refused ({len(bad)} chars)", ok)
    H.SECRETS.write_bytes(b"garbage")
    check("a damaged password file reads as empty and never crashes", H._read_secrets() == {} and not H.has_secret(G["id"]))
    H.set_secret(G["id"], PW)

    # ---- the mailboxes pulled from Citadel
    H.save_mailboxes([G, M2, {"id": "x", "email": "not-an-email"}, {"email": "a@b.co"}, "junk"])
    ms = H.load_mailboxes()
    check("only well-formed mailboxes are kept", [m["id"] for m in ms] == [G["id"], M2["id"]])
    check("a mailbox is found by address or id, in any case", H.find("ada@example.com")["id"] == G["id"] and H.find(M2["id"].upper())["email"] == "bob@example.org")
    try:
        H.find("nobody@x.co")
        msg = ""
    except ValueError as e:
        msg = str(e)
    check("an unknown mailbox says what to do and what exists", "Herald > Mailboxes" in msg and "bob@example.org" in msg)

    # ---- testing a mailbox (the logins are replaced: nothing real is contacted)
    calls = []
    H._smtp_login = lambda m, pw: calls.append(("smtp", m["smtp_host"], pw))
    H._imap_login = lambda m, pw: calls.append(("imap", m["imap_host"], pw))
    r = H.test_mailbox(G)
    check("both logins working means ready", r["status"] == "ready" and r["smtp"] and r["imap"] and r["secret_set"] and "Both logins worked" in r["note"] and [c[0] for c in calls] == ["smtp", "imap"])
    check("the stored password is what is used to log in", all(c[2] == PW for c in calls))

    def smtp_refuses(m, pw):
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    H._smtp_login = smtp_refuses
    r = H.test_mailbox(G)
    check("a refused sending login is an error with the Gmail app-password tip, and reading is still tried", r["status"] == "error" and r["smtp"] is False and r["imap"] is True and "App Password" in r["note"] and "Sending (SMTP)" in r["note"])

    def leaky(m, pw):
        raise RuntimeError(f"login failed for {pw}")
    H._smtp_login = leaky
    r = H.test_mailbox(G)
    check("a password that an error message echoes is hidden", PW not in json.dumps(r) and "[hidden]" in json.dumps(r))

    H._smtp_login = lambda m, pw: None
    r = H.test_mailbox(M2)
    check("a mailbox with no password set is 'new' and says the command to run", r["status"] == "new" and r["secret_set"] is False and "herald secret bob@example.org" in r["note"] and r["smtp"] is None)

    check("failures are explained in plain words", "not found" in H.explain(socket.gaierror("Name or service not known")) and "did not answer" in H.explain(socket.timeout("timed out"))
          and "other security option" in H.explain(__import__("ssl").SSLError("wrong version number")) and "refused the connection" in H.explain(ConnectionRefusedError("refused")) and "Microsoft 365" in H.explain(smtplib.SMTPAuthenticationError(535, b"x"), "microsoft"))

    # ---- what is reported to Citadel
    H.record_test(G["id"], {"status": "ready", "note": "Both logins worked: this mailbox can send and read."})
    pay = H.status_payload()
    check("status says whether a password is set and the last test, per mailbox", pay[G["id"]]["status"] == "ready" and pay[G["id"]]["secret_set"] is True and "checked_at" in pay[G["id"]] and pay[M2["id"]]["status"] == "new" and pay[M2["id"]]["secret_set"] is False and "herald secret" in pay[M2["id"]]["note"])
    check("no password ever appears in the status, the saved test or the mailbox file", all(PW not in json.dumps(x) for x in (pay,)) and PW not in H.STATUS.read_text(encoding="utf-8") and PW not in H.MAILBOXES.read_text(encoding="utf-8"))
    H.forget_secret(G["id"])
    check("forgetting the password resets that mailbox to new, even if it tested ready before", H.status_payload()[G["id"]]["status"] == "new" and H.status_payload()[G["id"]]["secret_set"] is False)
    H.set_secret(G["id"], PW)
    H._load_status().pop(G["id"], None)

    # ---- the command line
    def run(args, typed=None):
        buf = io.StringIO()
        old = H.getpass.getpass
        if typed is not None:
            H.getpass.getpass = lambda prompt="": typed
        try:
            with contextlib.redirect_stdout(buf):
                rc = H.cli(args)
        finally:
            H.getpass.getpass = old
        return rc, buf.getvalue()
    rc, out = run(["list"])
    check("list shows each mailbox, whether a password is set, and the limit", rc == 0 and "ada@example.com".lower() in out.lower() and "password: set" in out and "password: NOT SET" in out and "limit: 30" in out)
    rc, out = run(["secret", "bob@example.org"], typed="new-pass-9")
    check("secret saves a typed password and never prints it", rc == 0 and H.get_secret(M2["id"]) == "new-pass-9" and "new-pass-9" not in out and "Saved on this PC only" in out)
    rc, out = run(["secret", "ada@example.com"], typed="")
    check("an empty password is refused and the old one is kept", rc == 1 and H.get_secret(G["id"]) == PW)
    rc, out = run(["secret", "nobody@x.co"], typed="x")
    check("an unknown mailbox is explained", rc == 1 and "Herald > Mailboxes" in out)
    rc, out = run(["forget", "bob@example.org"])
    check("forget deletes it", rc == 0 and not H.has_secret(M2["id"]) and "Deleted" in out)
    rc, out = run([])
    check("no command shows the help", rc == 0 and "THE PASSWORD STAYS ON THIS PC" in out)
    rc, out = run(["wat"])
    check("an unknown command is explained", rc == 1 and "Unknown command" in out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- the password window (opened from the Citadel mailbox card)
calls = []
real_name = H.os.name
H.os.name = "nt"
msg_w = H.open_password_window({"id": "m-1", "email": "ada@me.com"}, popen=lambda cmd, **kw: calls.append((cmd, kw)))
H.os.name = real_name
check("the Citadel button opens a window on this PC that runs the password command for that mailbox", len(calls) == 1 and calls[0][0][-3:] == ["secret", "m-1", "--wait"] and "ada@me.com" in msg_w and calls[0][0][0] == sys.executable)
check("the address is one argument, never a shell string", isinstance(calls[0][0], list) and "shell" not in calls[0][1])
check("the message says where to type the password (that window) and what to do next", "paste the app password" in msg_w and "Test connection" in msg_w and "Go to it" in msg_w)
cat2 = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
check("the password tool takes only an address, never a password", [f["name"] for f in cat2["tools"]["dse.herald_password"]["fields"]] == ["mailbox"] and "never goes through Citadel" in cat2["tools"]["dse.herald_password"]["help"])

# ---- the catalog and the program
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
check("the two Herald tools are in the catalog, and say the password never leaves this PC", {"dse.herald_list", "dse.herald_test"} <= set(cat["tools"]) and "never leaves this PC" in cat["tools"]["dse.herald_test"]["help"])
check("the background sync runs every minute", any(x.get("script") == "bridge/herald_sync.py" and x.get("every_s") == 60 for x in cat["periodic"]))
check("the tool never puts a password in its form", all(f["name"] != "password" for f in cat["tools"]["dse.herald_test"]["fields"]))
src = (ROOT / "dse" / "herald.py").read_text(encoding="utf-8") + (ROOT / "bridge" / "herald_sync.py").read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8")
check("the PC code never sends a password to Citadel", "hq_herald_status" in src and "get_secret" in src and src.count("rpc(") <= 3 and "password" not in (ROOT / "bridge" / "herald_sync.py").read_text(encoding="utf-8").split('"""')[2])
check("dse.py knows the herald command", "herald.cli(a.rest)" in (ROOT / "dse.py").read_text(encoding="utf-8"))
check("no em dash", DASH not in src)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
