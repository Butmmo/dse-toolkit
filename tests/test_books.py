"""Tests for the exchange rates, the currency-aware Cash Desk and the Books Desk monthly pack.   python tests/test_books.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import books as B, cashdesk as CD, clients as CL, cuts as U, fx as FX, proposal as PR  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    return None


SLUG = "zz-books"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Books test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "archived": False}), encoding="utf-8")
TODAY = dt.date(2026, 12, 5)
D = dt.date

try:
    # ---- exchange rates
    check("a rate is saved and listed", "Saved: 1 GBP = 1.25 USD" in FX.add_rate(SLUG, "gbp", "usd", 1.25, "2026-11-01", "bank rate", TODAY) and "1 GBP = 1.25 USD" in FX.listing(SLUG))
    for name, a in {"same currency": ("USD", "USD", 1), "bad code": ("US", "GBP", 1), "zero rate": ("GBP", "USD", 0), "bad date": ("GBP", "USD", 1.2, "2026-13-99"), "future date": ("GBP", "USD", 1.2, "2027-01-01")}.items():
        check(f"rate refused: {name}", raises(FX.add_rate, SLUG, *a, **({"today": TODAY} if len(a) < 5 else {"today": TODAY})) is not None)
    FX.add_rate(SLUG, "GBP", "USD", 1.30, "2026-11-20", "", TODAY)
    check("the most recent rate ON OR BEFORE the payment date is used", FX.rate_for(SLUG, D(2026, 11, 10), "GBP", "USD")["rate"] == 1.25 and FX.rate_for(SLUG, D(2026, 11, 25), "GBP", "USD")["rate"] == 1.30)
    check("a rate dated after the payment is never used", FX.rate_for(SLUG, D(2026, 10, 31), "GBP", "USD") is None)
    FX.add_rate(SLUG, "USD", "EUR", 0.50, "2026-11-01", "", TODAY)
    inv = FX.rate_for(SLUG, D(2026, 11, 10), "EUR", "USD")
    check("a rate given the other way round is turned over (USD to EUR 0.50 means EUR to USD 2.0), and marked inverse", inv["rate"] == 2.0 and inv["inverse"])
    check("a rate more than 45 days before the payment is used but marked old", FX.rate_for(SLUG, D(2027, 1, 20), "GBP", "USD")["old"] is True and FX.rate_for(SLUG, D(2026, 11, 25), "GBP", "USD")["old"] is False)
    check("the same currency needs no rate", FX.rate_for(SLUG, D(2026, 11, 1), "USD", "USD")["rate"] == 1.0)
    check("convert returns the amount and the rate used; no rate gives None", FX.convert(SLUG, 100, D(2026, 11, 25), "GBP", "USD")[0] == 130.0 and FX.convert(SLUG, 100, D(2026, 11, 25), "NGN", "USD") is None)

    # ---- the cash file: currency column and migration of an old file
    legacy = ROOT / "engines" / "zz-books-old"
    shutil.rmtree(legacy, ignore_errors=True)
    (legacy / "data").mkdir(parents=True)
    (legacy / "engine.json").write_text(json.dumps({"name": "old", "path": "smb"}), encoding="utf-8")
    (legacy / "data" / "cash.csv").write_text("date,amount,kind,note\n2026-10-05,500.00,commission,old sale\n", encoding="utf-8")
    old_rows = CD.read_cash("zz-books-old")
    check("an old cash file is still readable: no currency means dollars, and it is flagged as assumed", old_rows[0]["currency"] == "USD" and old_rows[0]["currency_assumed"] is True)
    CD.log_cash("zz-books-old", 200, "commission", "new sale", "2026-11-05", "GBP")
    rows = CD.read_cash("zz-books-old")
    head = (legacy / "data" / "cash.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    check("adding a payment to an old file adds the currency column and keeps the old row (still assumed USD)", head == "date,amount,kind,note,currency" and rows[0]["currency"] == "USD" and rows[0]["currency_assumed"] and rows[1]["currency"] == "GBP" and not rows[1]["currency_assumed"], head)
    check("a bad currency code is refused", raises(CD.log_cash, SLUG, 10, "commission", "", "", "pounds") is not None)
    shutil.rmtree(legacy, ignore_errors=True)

    # ---- the whole month
    PR.report(SLUG, "Acme Dental", "Dana", "patients cannot book online", "Online booking", 1500, "Booking page; Reminders", 2, 0, today=D(2026, 11, 3), start="2026-11-09")
    CL.won(SLUG, "2026-11-03-acme-dental", "", "", D(2026, 11, 3))                                    # INV-2026-001: 750, issued Nov 3
    CL.paid(f"{SLUG}/acme-dental", "INV-2026-001", 750, "2026-11-15", D(2026, 11, 15))
    CL.invoice(f"{SLUG}/acme-dental", "extra", 200, "extra page", 7, D(2026, 10, 10))                 # INV-2026-002: 200, issued Oct 10, due Oct 17, unpaid
    U.add(SLUG, "Gem Pound", 10, "gross", "GBP", "grey", "", 7, "2026-10-01", D(2026, 11, 1))
    U.report(f"{SLUG}/gem-pound", "2026-10", 3000, 0, "p", False, D(2026, 11, 5))                      # CUT-2026-001: GBP 300
    U.paid(f"{SLUG}/gem-pound", "CUT-2026-001", 0, "2026-11-18", False, D(2026, 11, 18))
    U.add(SLUG, "Eur Eve", 10, "gross", "EUR", "payoneer", "", 7, "2026-10-01", D(2026, 11, 1))
    U.report(f"{SLUG}/eur-eve", "2026-10", 2000, 0, "p", False, D(2026, 11, 6))                        # CUT-2026-002: EUR 200 (no rate for EUR in November before Nov 1? rate dated Nov 1 exists: inverse)
    U.paid(f"{SLUG}/eur-eve", "CUT-2026-002", 0, "2026-10-31", False, D(2026, 11, 20))                 # paid Oct 31: before any EUR rate and in October (not in the November receipts)
    U.add(SLUG, "Sho Short", 10, "gross", "USD", "grey", "", 7, "2026-10-01", D(2026, 11, 1))
    U.report(f"{SLUG}/sho-short", "2026-10", 5000, 0, "p", False, D(2026, 11, 2))                      # CUT-2026-003: 500
    U.paid(f"{SLUG}/sho-short", "CUT-2026-003", 480, "2026-11-10", True, D(2026, 11, 10))              # 480 received, 20 written off
    U.add(SLUG, "Dara Dfy", 20, today=D(2026, 11, 1), start="2026-10-01", program="dfy")
    U.report(f"{SLUG}/dara-dfy", "2026-10", 3000, 0, "p", False, D(2026, 11, 3))                       # CUT-2026-004: 600 (net 3000 x 20%)
    f = d / "cuts" / "dara-dfy" / "student.json"
    sj = json.loads(f.read_text(encoding="utf-8"))
    sj["invoices"][0]["payments"].append({"date": "2026-12-05", "amount": 600, "from_citadel": True})
    f.write_text(json.dumps(sj), encoding="utf-8")
    CD.log_cash(SLUG, 100, "commission", "referral bonus", "2026-11-12", "USD")
    CD.log_cash(SLUG, 50, "refund", "refund to a client", "2026-11-25", "USD")
    U.add(SLUG, "Nai Ra", 10, "gross", "GBP", "grey", "", 7, "2026-10-01", D(2026, 11, 1))
    U.report(f"{SLUG}/nai-ra", "2026-10", 1000, 0, "p", False, D(2026, 11, 6))                         # CUT-2026-005: GBP 100, paid below with no rate on that date? rate exists (1.25 on Nov 1)
    CD.log_cash(SLUG, 80, "commission", "CUT-2026-777 Ghost", "2026-11-22", "USD")                      # names an invoice that does not exist

    text = B.build(SLUG, "2026-11", "USD", TODAY)
    out = d / "books" / "2026-11"
    check("five files are written", all((out / n).exists() for n in ("summary.md", "receipts.csv", "invoices.csv", "receivables.csv", "writeoffs.csv")))
    rc = list(csv.DictReader((out / "receipts.csv").open(encoding="utf-8-sig")))
    by = {r["reference"] or r["note"]: r for r in rc}
    check("receipts are only those received in the month, oldest first", [r["date"] for r in rc] == sorted(r["date"] for r in rc) and "2026-10-31" not in [r["date"] for r in rc], str([r["date"] for r in rc]))
    acme = by["INV-2026-001"]
    check("a client receipt is classified, named and in dollars", acme["source"] == "Client invoice" and acme["who"] == "Acme Dental" and float(acme["amount"]) == 750 and float(acme["base_amount"]) == 750)
    gem = by["CUT-2026-001"]
    check("GBP 300 on Nov 18 uses the rate you entered for Nov 1 (1.25): 375 dollars, rate and its date shown", float(gem["base_amount"]) == 375.0 and float(gem["rate_used"]) == 1.25 and gem["rate_date"] == "2026-11-01" and gem["currency"] == "GBP", str(gem))
    inv_src = {r["invoice"]: r["source"] for r in list(csv.DictReader((out / "invoices.csv").open(encoding="utf-8-sig")))}
    check("a DFY remittance is told apart from a student revenue share and a client invoice", inv_src["CUT-2026-004"] == "DFY remittance" and inv_src["CUT-2026-001"] == "Student revenue share" and inv_src["INV-2026-001"] == "Client invoice", str(inv_src))
    check("a payment with no invoice is 'Other income (no invoice)'", by["referral bonus"]["source"] == "Other income (no invoice)")
    check("a refund is a negative line", float(by["refund to a client"]["amount"]) == -50 and by["refund to a client"]["source"] == "Refund")
    check("a payment naming an invoice you do not have keeps the reference and is flagged", by["CUT-2026-777"]["reference"] == "CUT-2026-777" and "not in your records: CUT-2026-777" in text)

    check("summary: received section with by-currency totals and by-source lines", "## Received in the month (cash basis)" in text and "Client invoice: 1 payment(s), $750" in text and "£300" in text, text[:600])
    check("summary: the dollar total counts the pounds at your rate: 750 + 375 + 480 + 100 + 80 - 50 = 1,735", "in USD: $1,735" in text, text[:700])
    inv_part = text.split("## Invoiced")[1].split("##")[0]
    check("summary: invoiced in the month (accrual) counts exactly the 6 invoices issued in November (INV-2026-001 and five cuts), by currency", "6 invoice(s):" in inv_part and "£400" in inv_part and "€200" in inv_part and "Client invoice: 1" in inv_part and "DFY remittance: 1" in inv_part, inv_part)
    check("summary: still owed at month end, with the ageing bucket for the 200 extra invoice (due Oct 17: 44 days past due at Nov 30)", "31 to 60 days past due: 1, $200" in text and "INV-2026-002" in text, text.split("## Still owed")[1][:500])
    check("summary: the written-off shortfall is shown", "CUT-2026-003 Sho Short: $20" in text and "## Written off in the month" in text)
    check("summary: exchange rates used are listed with their dates", "1 GBP = 1.25 USD, the rate you entered for 2026-11-01" in text)
    check("summary: year to date adds up the months, in dollars", "2026 to date" in text and "Total so far:" in text)
    check("summary: history already paid in Citadel is kept out of the receipts and listed on its own", "Paid in Citadel before this ledger started" in text and "Dara Dfy" in text)
    check("summary: the checks to make before sending to the accountant", "have no invoice number" in text and "refunds in the month" in text, text.split("## Check before")[1][:500])
    check("summary: the accountant's questions are listed, and it says it does not decide them", "## Questions for your accountant" in text and "this tool does not decide them" in text and "VAT, sales tax or withholding" in text)
    check("it never claims to be tax advice", "not tax advice" in text and "tax owed" not in text.lower())

    inv_rows = list(csv.DictReader((out / "invoices.csv").open(encoding="utf-8-sig")))
    check("invoices.csv lists the invoices issued in November with status at month end", {r["invoice"] for r in inv_rows} >= {"INV-2026-001", "CUT-2026-001", "CUT-2026-003"} and next(r for r in inv_rows if r["invoice"] == "INV-2026-001")["status"] == "paid")
    rec_rows = list(csv.DictReader((out / "receivables.csv").open(encoding="utf-8-sig")))
    check("receivables.csv has the unpaid invoice with days past due", any(r["invoice"] == "INV-2026-002" and r["days_past_due"] == "44" and float(r["owed_at_month_end"]) == 200 for r in rec_rows), str(rec_rows))
    check("the Citadel-history invoice is not counted as owed", not any(r["invoice"] == "CUT-2026-004" for r in rec_rows))
    wo = list(csv.DictReader((out / "writeoffs.csv").open(encoding="utf-8-sig")))
    check("writeoffs.csv has the 20 shortfall", wo[0]["invoice"] == "CUT-2026-003" and float(wo[0]["written_off"]) == 20)

    # ---- an unconverted currency
    CD.log_cash(SLUG, 50, "commission", "NGN client", "2026-11-23", "NGN")
    t2 = B.build(SLUG, "2026-11", "USD", TODAY)
    rc2 = list(csv.DictReader((out / "receipts.csv").open(encoding="utf-8-sig")))
    check("a currency with no rate is NOT converted, left blank, listed with the command that fixes it, and flagged", next(r for r in rc2 if r["note"] == "NGN client")["base_amount"] == "" and "NOT converted: 50 NGN on 2026-11-23" in t2 and "fx add zz-books --from NGN --to USD" in t2 and "no exchange rate and are not converted" in t2, t2)
    check("the dollar total is unchanged by the unconverted money", "in USD: $1,735" in t2 and "excluding money with no exchange rate" in t2)

    # ---- Cash Desk is currency aware
    cash = CD.build(SLUG, "2026-11", today=D(2026, 11, 30))
    check("the Cash Desk counts converted pounds and says at what rate, and lists the NGN as not counted", "£" not in cash.split("Received")[0] and "GBP 300.00 received, counted as $375" in cash and "Not counted: NGN 50.00" in cash, cash[:900])
    md = CD.month_data(SLUG, D(2026, 11, 1), D(2026, 11, 30))
    check("month_data separates what is converted from what is not", md["by_currency"]["GBP"] == 300.0 and any(u["currency"] == "NGN" for u in md["unconverted"]) and md["received"] == 1735.0, str(md["received"]))

    # ---- errors and options
    check("bad base and future month refused", raises(B.build, SLUG, "2026-11", "dollars", TODAY) is not None and raises(B.build, SLUG, "2027-06", "USD", TODAY) is not None and raises(B.build, SLUG, "Nov", "USD", TODAY) is not None)
    t3 = B.build(SLUG, "2026-11", "GBP", TODAY)
    check("another base currency uses your rates the other way (GBP base: USD payments via the inverse of GBP to USD)", "Base currency GBP" in t3 and "inverse" not in t3 and "NOT converted: 50 NGN" in t3)
    check("the default month is the last complete one", B.last_complete(D(2026, 12, 5)) == "2026-11" and B.last_complete(D(2027, 1, 3)) == "2026-12")
    mar = B.build(SLUG, "2026-03", "USD", TODAY)
    check("a month with nothing says so cleanly", "0 payment(s): none" in mar and "- none issued" in mar and "- none" in mar.split("## Written off")[1], mar[:400])
    check("no em dash in the summary or the csv files", all(chr(0x2014) not in x for x in (text, t2, t3, (out / "receipts.csv").read_text(encoding="utf-8"))))
finally:
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(ROOT / "engines" / "zz-books-old", ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
