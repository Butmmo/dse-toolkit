"""Tests for the Paystack key slot and the Get paid tools. Run: python tests/test_payments.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.pop("PAYSTACK_SECRET_KEY", None)

from dse import paylinks, paystackkey  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"   {extra}"))
    if not cond:
        FAILS.append(name)


class FakeStore:
    def __init__(self):
        self.data = {}

    def get(self, name):
        return self.data.get(name, "")

    def set(self, name, value):
        self.data[name] = value

    def delete(self, name):
        self.data.pop(name, None)


LIVE = "sk_live_1234567890abcdef"
TEST = "sk_test_1234567890abcdef"


def http200(url, headers):
    assert headers.get("Authorization", "").startswith("Bearer sk_")
    return 200, "{}"


def http401(url, headers):
    return 401, "{}"


# ---- the key slot
ok("paystack key shapes: sk_test_ and sk_live_ pass, other shapes are refused",
   bool(paystackkey.KEY_RE.match(LIVE)) and bool(paystackkey.KEY_RE.match(TEST))
   and not paystackkey.KEY_RE.match("sk-proj-1234567890abcdef1234567890")
   and not paystackkey.KEY_RE.match("sk_live_short")
   and not paystackkey.KEY_RE.match(""))
ok("the mask shows only the last four, and the mode reads test or live",
   paystackkey.mask(LIVE).endswith(LIVE[-4:]) and LIVE not in paystackkey.mask(LIVE)
   and paystackkey.mode(TEST) == "test" and paystackkey.mode(LIVE) == "live")
ok("verify reads the answer plainly: 200 ok, 401 invalid, no network offline",
   paystackkey.verify(LIVE, http200)[0] == "ok" and paystackkey.verify(LIVE, http401)[0] == "invalid"
   and paystackkey.verify(LIVE, lambda u, h: (0, ""))[0] == "offline" and paystackkey.verify("junk", http200)[0] == "invalid")
store = FakeStore()
ok("a key Paystack rejects is not saved; a good key is saved and reported masked",
   paystackkey.save(LIVE, store, http401).startswith("Not saved") and not store.data
   and paystackkey.save(LIVE, store, http200).startswith("Saved") and store.data.get("PAYSTACK_SECRET_KEY") == LIVE)
st = paystackkey.status(store)
ok("status says yes with the mask and never prints the key",
   "Key on this PC: yes" in st and LIVE not in st and "live mode" in st)
ok("remove forgets the key, and a second remove says there was none",
   paystackkey.remove(store).startswith("Removed") and not store.data
   and paystackkey.remove(store).startswith("There was no key"))
ok("with no key, status gives the setup step",
   "python dse.py paystack setup" in paystackkey.status(FakeStore()))

# ---- money
ok("amounts convert exactly: whole and cents, commas tolerated, junk refused",
   paylinks.to_minor("500") == 50000 and paylinks.to_minor("99.50") == 9950 and paylinks.to_minor("1,200") == 120000
   and paylinks.to_minor("0") is None and paylinks.to_minor("-5") is None and paylinks.to_minor("1.234") is None
   and paylinks.to_minor("abc") is None and paylinks.to_minor("99999999") is None and paylinks.to_minor("") is None)
ok("minor units print back plainly",
   paylinks.fmt_major(50000) == "500" and paylinks.fmt_major(125050) == "1250.50" and paylinks.fmt_major(50005) == "500.05" and paylinks.fmt_major(99) == "0.99")

# ---- creating a link
seen = {}


def fake_post(url, key, payload):
    seen.update(url=url, key=key, payload=payload)
    return 201, {"status": True, "data": {"slug": "ada-retainer-x1"}}


out = paylinks.create_link("Ada Designs retainer", "500", "NGN", key=LIVE, post=fake_post)
ok("a created page prints its PAY_LINK_URL line, and the payload carries minor units",
   "PAY_LINK_URL: https://paystack.com/pay/ada-retainer-x1" in out and seen["payload"] == {"name": "Ada Designs retainer", "amount": 50000, "currency": "NGN"} and seen["url"] == paylinks.PAGE_API)
ok("with no key the tool does nothing and says how to connect one",
   paylinks.create_link("X work", "500", "NGN", key="", post=fake_post, store=FakeStore()).startswith("No Paystack key"))
ok("a bad currency and a bad amount are refused before any call",
   "currency must be one of" in paylinks.create_link("X work", "500", "BTC", key=LIVE, post=fake_post)
   and "plain number" in paylinks.create_link("X work", "five", "NGN", key=LIVE, post=fake_post))
ok("a refused key (401) is reported with the fix, and a slugless answer saves nothing",
   "refused the key" in paylinks.create_link("X work", "500", "NGN", key=LIVE, post=lambda u, k, p: (401, {"status": False}))
   and "without a page link" in paylinks.create_link("X work", "500", "NGN", key=LIVE, post=lambda u, k, p: (200, {"status": True, "data": {}})))

# ---- recent payments
TXS = {"status": True, "data": [
    {"amount": 125050, "currency": "NGN", "reference": "T987", "paid_at": "2026-11-28T08:00:00.000Z", "customer": {"email": "ada@example.com"}},
    {"amount": 50000, "currency": "NGN", "reference": "T986", "paid_at": "2026-11-27T08:00:00.000Z", "customer": {"email": ""}},
]}
out = paylinks.recent(key=LIVE, get=lambda url, key: (200, TXS))
ok("recent payments print one PAYMENT line each, in the pinned format",
   "PAYMENT: 1250.50 NGN | ref: T987 | 2026-11-28T08:00:00.000Z | ada@example.com" in out
   and "PAYMENT: 500 NGN | ref: T986 | 2026-11-27T08:00:00.000Z | " in out)
ok("no payments yet reads honestly, and no key does nothing",
   "No successful payments found yet." in paylinks.recent(key=LIVE, get=lambda url, key: (200, {"status": True, "data": []}))
   and paylinks.recent(key="", get=lambda url, key: (200, TXS), store=FakeStore()).startswith("No Paystack key"))

print()
print("FAILED:", len(FAILS), FAILS if FAILS else "")
sys.exit(1 if FAILS else 0)
