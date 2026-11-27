"""Offline tests for dse.email_verify: fake DNS and fake SMTP, no network."""
import datetime as dt
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dse import email_verify as ev

TODAY = dt.date(2026, 11, 27)
PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


class FakeSMTP:
    def __init__(self, codes, default=550):
        self.codes = codes
        self.default = default
        self.checked = []
        self.mail_from = None

    def mail(self, sender):
        self.mail_from = sender
        return (250, b"ok")

    def rcpt(self, addr):
        self.checked.append(addr)
        return (self.codes.get(addr, self.default), b"")

    def quit(self):
        pass


def run(rows, mx_map, sessions, col="email", **kw):
    def mx_lookup(domain):
        return mx_map.get(domain)

    def connect(host):
        s = sessions[host]
        if isinstance(s, Exception):
            raise s
        return s

    return ev.verify_rows(rows, col, today=TODAY, mx_lookup=mx_lookup,
                          connect=connect, sleep=None, rng=random.Random(7), **kw)


# 1. bad syntax is invalid and never touches the network
rows = [{"email": "not-an-address"}]
c = run(rows, {}, {})
check("syntax: invalid", rows[0]["email_verdict"] == "invalid" and c["invalid"] == 1)
check("syntax: reason is plain", "format" in rows[0]["email_verdict_reason"])
check("syntax: date stamped", rows[0]["email_verified_at"] == "2026-11-27")

# 2. domain with no mail servers is invalid
rows = [{"email": "owner@nomx.com"}]
run(rows, {"nomx.com": []}, {})
check("no MX: invalid", rows[0]["email_verdict"] == "invalid" and "no mail servers" in rows[0]["email_verdict_reason"])

# 3. a failed lookup is unknown, never invalid
rows = [{"email": "owner@flaky.com"}]
run(rows, {"flaky.com": None}, {})
check("lookup failed: unknown", rows[0]["email_verdict"] == "unknown")

# 4. accepted address, made-up address refused: valid
s = FakeSMTP({"owner@good.com": 250})
rows = [{"email": "owner@good.com"}]
run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("accepted: valid", rows[0]["email_verdict"] == "valid")
check("catch-all probed first", s.checked[0].startswith("dse-verify-"))

# 5. server accepts everything: risky (catch-all)
s = FakeSMTP({}, default=250)
rows = [{"email": "owner@catchall.com"}]
run(rows, {"catchall.com": ["mx.catchall.com"]}, {"mx.catchall.com": s})
check("catch-all: risky", rows[0]["email_verdict"] == "risky" and "accepts every address" in rows[0]["email_verdict_reason"])

# 6. server says the address does not exist: invalid
s = FakeSMTP({"ghost@good.com": 550})
rows = [{"email": "ghost@good.com"}]
run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("550: invalid", rows[0]["email_verdict"] == "invalid" and "does not exist" in rows[0]["email_verdict_reason"])

# 7. greylisting (450) is unknown
s = FakeSMTP({"owner@good.com": 450})
rows = [{"email": "owner@good.com"}]
run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("450: unknown", rows[0]["email_verdict"] == "unknown" and "try again later" in rows[0]["email_verdict_reason"])

# 8. unreachable server is unknown
rows = [{"email": "owner@down.com"}]
run(rows, {"down.com": ["mx.down.com"]}, {"mx.down.com": OSError("no route")})
check("unreachable: unknown", rows[0]["email_verdict"] == "unknown" and "could not be reached" in rows[0]["email_verdict_reason"])

# 9. throwaway domain is risky without any SMTP session
rows = [{"email": "x@mailinator.com"}]
run(rows, {"mailinator.com": ["mx.mailinator.com"]}, {})
check("disposable: risky", rows[0]["email_verdict"] == "risky" and "throwaway" in rows[0]["email_verdict_reason"])

# 10. role addresses keep their verdict and gain the team-inbox note
s = FakeSMTP({"info@good.com": 250})
rows = [{"email": "info@good.com"}]
run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("role: valid with note", rows[0]["email_verdict"] == "valid" and "team inbox" in rows[0]["email_verdict_reason"])

# 11. a fresh verdict is left alone; refresh checks again
old = [{"email": "owner@good.com", "email_verdict": "valid", "email_verdict_reason": "earlier",
        "email_verified_at": "2026-11-20"}]
s = FakeSMTP({"owner@good.com": 550})
c = run(old, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("fresh: skipped", c["skipped"] == 1 and old[0]["email_verdict"] == "valid" and s.checked == [])
c = run(old, {"good.com": ["mx.good.com"]}, {"mx.good.com": s}, refresh=True)
check("refresh: rechecked", old[0]["email_verdict"] == "invalid")

# 12. a stale verdict is rechecked without refresh
stale = [{"email": "owner@good.com", "email_verdict": "valid", "email_verdict_reason": "earlier",
          "email_verified_at": "2026-09-01"}]
s = FakeSMTP({"owner@good.com": 250})
run(stale, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("stale: rechecked", stale[0]["email_verified_at"] == "2026-11-27")

# 13. blank rows are counted, not verified
rows = [{"email": ""}, {"email": "owner@good.com"}]
s = FakeSMTP({"owner@good.com": 250})
c = run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s})
check("blank: counted only", c["blank"] == 1 and "email_verdict" not in rows[0])

# 14. one session serves a whole domain, and the sender is passed through
s = FakeSMTP({"a@good.com": 250, "b@good.com": 550})
rows = [{"email": "a@good.com"}, {"email": "b@good.com"}]
run(rows, {"good.com": ["mx.good.com"]}, {"mx.good.com": s}, sender="me@mine.com")
check("domain session: mixed verdicts", rows[0]["email_verdict"] == "valid" and rows[1]["email_verdict"] == "invalid")
check("domain session: sender used", s.mail_from == "me@mine.com")

# 15. mx_hosts parses real nslookup output (Windows shape)
class R:
    stdout = b"example.com\tMX preference = 10, mail exchanger = mail.example.com\r\nexample.com\tMX preference = 5, mail exchanger = mx.example.com\r\n"

hosts = ev.mx_hosts("example.com", runner=lambda *a, **k: R())
check("mx parse: sorted hosts", hosts == ["mx.example.com", "mail.example.com"])

class RNone:
    stdout = b"*** dns.google can't find no-such-domain.example: Non-existent domain\r\n"

check("mx parse: no domain means no hosts", ev.mx_hosts("no-such-domain.example", runner=lambda *a, **k: RNone()) == [])

def boom(*a, **k):
    raise subprocess.TimeoutExpired("nslookup", 12)

check("mx parse: timeout means unknown", ev.mx_hosts("example.com", runner=boom) is None)

# 16. the email column is found the way grids name it
check("column: best_email wins", ev.find_email_column(["Company", "best_email", "email"], []) == "best_email")
check("column: plain email found", ev.find_email_column(["Company", "Email"], []) == "Email")
try:
    ev.find_email_column(["Company", "Phone"], [])
    check("column: missing raises", False)
except ValueError:
    check("column: missing raises", True)

failed = [n for n, ok in PASS if not ok]
print(f"\n{len(PASS) - len(failed)}/{len(PASS)} checks passed")
sys.exit(1 if failed else 0)
