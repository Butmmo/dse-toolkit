"""Get paid with your own Paystack key: create a payment link, and read your recent payments.

    python dse.py paylink create --name "Ada Designs retainer" --amount 500 --currency NGN
    python dse.py paylink recent

The create command makes ONE payment page at Paystack, with the amount fixed on it, and prints
its link on a line of its own (PAY_LINK_URL:) so Citadel can save it onto the client or the quote.
The recent command lists your latest successful payments, one per PAYMENT: line, so Citadel can
show them beside your unpaid invoices. Matching a payment to an invoice is always the member's
tap in Citadel: this tool changes nothing at Paystack and marks nothing paid anywhere.

The key is your own Paystack secret key, saved on this PC only (python dse.py paystack setup).
It is sent only to Paystack itself. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from dse import paystackkey

PAGE_API = "https://api.paystack.co/page"
TX_API = "https://api.paystack.co/transaction"
PAGE_BASE = "https://paystack.com/pay/"
CURRENCIES = ("NGN", "USD", "GBP", "GHS", "KES", "ZAR")
AMOUNT_RE = re.compile(r"^[0-9]+(\.[0-9]{1,2})?\Z")
MAX_MAJOR = Decimal("10000000")


# ------------------------------------------------------------------ http (injectable for tests)

def _request(method: str, url: str, key: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, dict | None]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read(200000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read(200000).decode("utf-8", "replace"))
        except Exception:
            return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


def http_get(url: str, key: str) -> tuple[int, dict | None]:
    return _request("GET", url, key)


def http_post(url: str, key: str, payload: dict) -> tuple[int, dict | None]:
    return _request("POST", url, key, payload)


# ------------------------------------------------------------------ money

def to_minor(amount_text: str) -> int | None:
    """A typed amount ('500', '99.50') in minor units, or None when it is not a sane amount."""
    t = str(amount_text or "").strip().replace(",", "")
    if not AMOUNT_RE.match(t):
        return None
    try:
        major = Decimal(t)
    except InvalidOperation:
        return None
    if major <= 0 or major > MAX_MAJOR:
        return None
    return int((major * 100).to_integral_value())


def fmt_major(minor: int) -> str:
    """Minor units back to the plain amount text the PAYMENT lines and reports use ('1250.50', '500')."""
    minor = int(minor)
    whole, rem = divmod(minor, 100)
    return f"{whole}.{rem:02d}" if rem else str(whole)


# ------------------------------------------------------------------ the two jobs

def _no_key() -> str:
    return ("No Paystack key on this PC, so nothing was done.\n"
            "Connect yours first, on this PC: python dse.py paystack setup\n"
            "The key stays on this PC; Citadel only ever learns yes or no.\n")


def _key_refused(code: int) -> str:
    if code == 401:
        return ("Paystack refused the key on this PC (401). It may have been rolled.\n"
                "Save the current one again: python dse.py paystack setup\n")
    if code == 0:
        return "Could not reach Paystack: check this PC's internet and try again.\n"
    return f"Paystack answered {code}: try again in a minute. Nothing was changed.\n"


def create_link(name: str, amount_text: str, currency: str, key: str = "", post=http_post, store=None) -> str:
    key = key or paystackkey.current_key(store)
    if not key:
        return _no_key()
    name = " ".join(str(name or "").split())[:120]
    if len(name) < 2:
        return "Not created: give the payment page a name (the client or the work, a few words).\n"
    currency = str(currency or "").strip().upper()
    if currency not in CURRENCIES:
        return f"Not created: the currency must be one of {', '.join(CURRENCIES)}.\n"
    minor = to_minor(amount_text)
    if minor is None:
        return "Not created: the amount must be a plain number like 500 or 99.50, more than zero.\n"
    code, body = post(PAGE_API, key, {"name": name, "amount": minor, "currency": currency})
    if code not in (200, 201) or not body or not body.get("status"):
        return _key_refused(code) if code in (0, 401) else f"Paystack did not create the page (answered {code}). Nothing was changed.\n"
    slug = str((body.get("data") or {}).get("slug") or "").strip()
    if not slug:
        return "Paystack answered without a page link, so nothing was saved. Try again in a minute.\n"
    url = PAGE_BASE + slug
    return (f"Payment page created with Paystack.\n"
            f"Name: {name}\n"
            f"Amount: {fmt_major(minor)} {currency} (fixed on the page; the client cannot change it)\n"
            f"PAY_LINK_URL: {url}\n"
            f"Citadel saves this link onto the client or the quote you created it from.\n")


def recent(key: str = "", get=http_get, store=None, per_page: int = 20) -> str:
    key = key or paystackkey.current_key(store)
    if not key:
        return _no_key()
    code, body = get(f"{TX_API}?status=success&perPage={per_page}", key)
    if code != 200 or not body or not body.get("status"):
        return _key_refused(code)
    rows = body.get("data") or []
    lines = ["Recent successful payments at Paystack (newest first):"]
    found = 0
    for tx in rows:
        try:
            amount = fmt_major(int(tx.get("amount") or 0))
        except (TypeError, ValueError):
            continue
        currency = str(tx.get("currency") or "").upper()
        ref = str(tx.get("reference") or "").strip()
        paid_at = str(tx.get("paid_at") or tx.get("created_at") or "").strip()
        email = str((tx.get("customer") or {}).get("email") or "").strip()
        if not ref:
            continue
        lines.append(f"PAYMENT: {amount} {currency} | ref: {ref} | {paid_at} | {email}")
        found += 1
    if not found:
        lines.append("No successful payments found yet.")
    lines.append("Match each one to an unpaid invoice in Citadel and mark it paid there. Nothing here changes anything at Paystack.")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ the command

def _opts(args: list[str]) -> dict:
    out: dict[str, str] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and i + 1 < len(args):
            out[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return out


def run_cli(args: list[str]) -> int:
    x = args[0] if args else ""
    if x == "create":
        o = _opts(args[1:])
        out = create_link(o.get("name", ""), o.get("amount", ""), o.get("currency", ""))
        print(out)
        return 0 if out.startswith("Payment page created") else 1
    if x == "recent":
        out = recent()
        print(out)
        return 0 if out.startswith("Recent successful") else 1
    print(__doc__)
    return 0 if x in ("", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
