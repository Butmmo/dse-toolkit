"""Herald webhooks, phase 7: delivers the events Citadel queued, from your own PC.

When a reply, a bounce or an unsubscribe is found, Citadel queues one delivery for each webhook you set up. This PC sends it to your address, signed with the webhook's secret, so it can
reach things on your own computer too (for example a local n8n at http://localhost:5678). Only https:// addresses and http://localhost are allowed. Redirects are not followed.

The request is a POST of JSON with these headers:
  X-Herald-Event      reply | bounce | unsubscribe | test
  X-Herald-Timestamp  seconds since 1970
  X-Herald-Signature  sha256=<hex>   an HMAC-SHA256 of  "<timestamp>.<body>"  with your webhook secret
Your side should check the signature and ignore anything older than 5 minutes. A reply is "delivered" when your address answers with a 2xx code; otherwise it is retried (2, 4, 8, 16, 32 minutes).
Stdlib only; honours the PAUSE file of the sender.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request

from . import herald as H

TIMEOUT = 10
MAX_BODY = 20000
URL_OK = re.compile(r"^(https://[^\s/]+|http://(localhost|127\.0\.0\.1)(:[0-9]+)?(/|$))", re.I)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _post(url: str, body: bytes, headers: dict) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=TIMEOUT) as r:
            return int(r.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def deliver(item: dict, now: dt.datetime, post=_post) -> dict:
    """Sends one delivery and says what happened in the form Citadel stores. The secret never appears in the result."""
    secret = item.get("secret", "")
    if not URL_OK.match(item.get("url", "")):
        return {"id": item["id"], "ok": False, "error": "The address must start with https:// (or be http://localhost)."}
    body = json.dumps(item["payload"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")[:MAX_BODY]
    ts = str(int(now.timestamp()))
    headers = {"Content-Type": "application/json", "User-Agent": "Herald-Webhook/1", "X-Herald-Event": str(item.get("event", "")), "X-Herald-Timestamp": ts, "X-Herald-Signature": sign(secret, ts, body)}
    try:
        code = post(item["url"], body, headers)
    except Exception as e:                          # a refused connection, a timeout, a bad certificate
        return {"id": item["id"], "ok": False, "error": H._scrub(f"Could not reach it: {type(e).__name__}", secret)[:200]}
    if 200 <= code < 300:
        return {"id": item["id"], "ok": True, "code": code}
    return {"id": item["id"], "ok": False, "code": code, "error": f"Your address answered {code}."}


def run(api, now: dt.datetime, post=_post, out=print) -> int:
    """Delivers everything due. Returns how many went through. A Citadel without the developer file simply has nothing due."""
    try:
        items = api.rpc("hq_herald_hooks_due", {})
    except Exception:
        return 0
    if not isinstance(items, list) or not items:
        return 0
    results = [deliver(it, now, post) for it in items]
    api.rpc("hq_herald_hooks_report", {"p_results": results})
    bad = [r for r in results if not r["ok"]]
    if bad:
        out(f"Herald webhooks: {len(bad)} of {len(results)} not delivered (they will be retried).")
    return len(results) - len(bad)
