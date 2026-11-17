"""Tests for Herald phase 7: webhook delivery from the PC.   python tests/test_herald_hooks.py
Nothing real is contacted: the web address and Citadel are replaced by fakes."""
import datetime as dt
import hashlib
import hmac
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald_hooks as K  # noqa: E402
from dse import herald_send as S  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


NOW = dt.datetime(2026, 12, 2, 10, 0, tzinfo=dt.timezone.utc)
SECRET = "whsec_" + "ab" * 32
item = lambda i=1, **o: {"id": f"d{i}", "url": "https://hooks.example.com/herald", "secret": SECRET, "event": "reply", "payload": {"event": "reply", "from_email": "a@b.co", "snippet": "Yes please"}, "attempts": 0, **o}  # noqa: E731


class Api:
    def __init__(self, due):
        self.due, self.reports = due, []

    def rpc(self, name, args):
        if name == "hq_herald_hooks_due":
            return self.due
        if name == "hq_herald_hooks_report":
            self.reports.append(args["p_results"])
            return len(args["p_results"])
        return 1


# the signature can be checked by the receiver with the documented recipe
body = b'{"a":1}'
check("the signature is an HMAC-SHA256 of timestamp.body with the secret", K.sign(SECRET, "1700000000", body) == "sha256=" + hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest())
seen = {}
def ok_post(url, body, headers):
    seen.update(url=url, body=body, headers=headers)
    return 204
r = K.deliver(item(), NOW, ok_post)
check("a 2xx answer is a delivery", r == {"id": "d1", "ok": True, "code": 204})
h = seen["headers"]
check("the request carries the event, the time and a signature that matches the exact body", h["X-Herald-Event"] == "reply" and h["X-Herald-Timestamp"] == str(int(NOW.timestamp())) and h["X-Herald-Signature"] == K.sign(SECRET, h["X-Herald-Timestamp"], seen["body"]))
check("the body is the JSON payload", json.loads(seen["body"])["snippet"] == "Yes please" and h["Content-Type"] == "application/json")
check("a 500 is a failure with its code and a plain reason", K.deliver(item(), NOW, lambda *a: 500) == {"id": "d1", "ok": False, "code": 500, "error": "Your address answered 500."})
def boom(*a):
    raise ConnectionRefusedError("refused " + SECRET)
b = K.deliver(item(), NOW, boom)
check("an unreachable address is a failure, and the secret never appears in it", not b["ok"] and SECRET not in json.dumps(b) and "Could not reach" in b["error"])
check("only https and localhost addresses are called", all(not K.deliver(item(url=u), NOW, ok_post)["ok"] for u in ("http://example.com/x", "ftp://x.co", "file:///etc/passwd", "https://", "javascript:alert(1)")) and K.deliver(item(url="http://localhost:5678/webhook/x"), NOW, ok_post)["ok"] and K.deliver(item(url="http://127.0.0.1:8080/"), NOW, ok_post)["ok"])
check("a lookalike host is not treated as localhost", not K.deliver(item(url="http://localhost.evil.com/x"), NOW, ok_post)["ok"])
big = K.deliver(item(payload={"x": "y" * 50000}), NOW, lambda u, body, h: (seen.update(n=len(body)) or 200))
check("a huge payload is cut, not sent whole", seen["n"] <= K.MAX_BODY)

api = Api([item(1), item(2, url="http://nope.com")])
n = K.run(api, NOW, ok_post, out=lambda *a: None)
check("a run delivers what it can, reports every result, and counts the good ones", n == 1 and len(api.reports[0]) == 2 and [x["ok"] for x in api.reports[0]] == [True, False])
check("the report never carries a secret", SECRET not in json.dumps(api.reports))
check("nothing due means no call to Citadel's report", K.run(Api([]), NOW, ok_post) == 0 and K.run(Api(1), NOW, ok_post) == 0)

class Boom:
    def rpc(self, *a):
        raise RuntimeError("function does not exist")
check("an old Citadel without the developer file does not break sending", K.run(Boom(), NOW, ok_post) == 0)

src = (ROOT / "dse" / "herald_hooks.py").read_text(encoding="utf-8")
check("redirects are not followed", "_NoRedirect" in src and "build_opener(_NoRedirect)" in src)
check("the sender runs the webhooks after reading the mailboxes", "herald_hooks.run(" in (ROOT / "dse" / "herald_send.py").read_text(encoding="utf-8"))
check("no em dash", DASH not in src + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
