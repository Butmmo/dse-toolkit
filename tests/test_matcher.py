"""Tests for the Statement Matcher.   python tests/test_matcher.py"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cashdesk as CD, clients as CL, cuts as U, matcher as M, proposal as PR  # noqa: E402

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


# ---- parsing
check("amounts: plain, thousands, European, brackets, symbols, signs, junk", [M.parse_amount(x) for x in ("1,234.56", "1.234,56", "(50.00)", "$1,000", "12,50", "-5", "abc", "", "750.00 USD", "1,000")]
      == [1234.56, 1234.56, -50.0, 1000.0, 12.5, -5.0, None, None, 750.0, 1000.0])
check("dates: ISO, day first, month first, words, junk", [M.parse_date(x, True) for x in ("2026-11-10", "15/11/2026", "03/04/2026", "10 Nov 2026", "Nov 10, 2026", "x", "")]
      == [dt.date(2026, 11, 10), dt.date(2026, 11, 15), dt.date(2026, 4, 3), dt.date(2026, 11, 10), dt.date(2026, 11, 10), None, None] and M.parse_date("03/04/2026", False) == dt.date(2026, 3, 4))
check("column aliases", M.find_columns(["Transaction Date", "Details", "Credit", "Debit", "Currency", "Status", "Name"]) == {"date": "Transaction Date", "description": "Details", "amount": "Credit", "debit": "Debit", "currency": "Currency", "status": "Status", "sender": "Name"})

SLUG = "zz-match"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "statements").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Match test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "archived": False}), encoding="utf-8")
NOV5, NOV20 = dt.date(2026, 11, 5), dt.date(2026, 11, 20)
for name, pct in (("Ada Obi", 10), ("Bola Ade", 10), ("Cara Dunn", 10), ("Dan Dunn", 10), ("Dee Dunn", 10)):
    U.add(SLUG, name, pct, "gross", "USD", "grey", "", 7, "2026-10-01", NOV5)
U.report(f"{SLUG}/ada-obi", "2026-10", 6000, 0, "p", False, NOV5)       # CUT-2026-001: 600
U.report(f"{SLUG}/bola-ade", "2026-10", 3000, 0, "p", False, NOV5)      # CUT-2026-002: 300
U.report(f"{SLUG}/cara-dunn", "2026-10", 10000, 0, "p", False, NOV5)    # CUT-2026-003: 1000
U.report(f"{SLUG}/dan-dunn", "2026-10", 5000, 0, "p", False, NOV5)      # CUT-2026-004: 500
U.report(f"{SLUG}/dee-dunn", "2026-10", 5000, 0, "p", False, NOV5)      # CUT-2026-005: 500
PR.report(SLUG, "Acme Dental", "Dana", "patients cannot book online", "Online booking", 1500, "Booking page; Reminders", 2, 0, today=NOV5, start="2026-11-09")
CL.won(SLUG, "2026-11-05-acme-dental", "", "", NOV5)                    # INV-2026-001: 750 deposit

GREY = """Date,Description,Amount,Currency,Status
2026-11-10,Payment from Ada Obi CUT-2026-001,600.00,USD,Completed
2026-11-11,Transfer from Bola Ade ref CUT 2026 002,295.00,USD,Completed
2026-11-12,ACME DENTAL LLC,750.00,USD,Completed
2026-11-13,Mystery sender,123.45,USD,Completed
2026-11-14,Withdrawal to bank,-500.00,USD,Completed
2026-11-14,Pending payment from Cara Dunn,1000.00,USD,Pending
2026-11-15,Cara Dunn payment,1000.00,USD,Completed
2026-11-16,Payment CUT-2026-003 from someone,400.00,USD,Completed
2026-11-17,Dan and Dee Dunn,500.00,USD,Completed
2026-11-18,Payment CUT-2026-004 Dan Dunn,500.00,GBP,Completed
"""
(d / "statements" / "grey.csv").write_text(GREY, encoding="utf-8")
try:
    t = M.report(SLUG, "grey.csv", today=NOV20)
    check("reads 8 credits and ignores the debit and the pending line", "8 credit(s) read" in t and "1 debit(s)" in t and "1 not completed" in t, t[:300])
    check("SURE: number + exact amount + name", "CUT-2026-001 Ada Obi" in t.split("## Sure matches")[1].split("## Likely")[0] and "the invoice number is in the line" in t)
    check("SURE: the number written 'CUT 2026 002' and 295 against 300 is short by a normal fee, and says so", "CUT-2026-002 Bola Ade" in t and "$5 short, within a normal transfer fee" in t and "Short by $5" in t, t)
    check("LIKELY: name + exact amount without a number comes with the command to run", "ACME DENTAL LLC" in t.split("## Likely")[1] and "python dse.py client paid zz-match/acme-dental --invoice INV-2026-001 --amount 750 --date 2026-11-12" in t, t)
    check("LIKELY: a number with the wrong amount is flagged, not applied", "CUT-2026-003 Cara Dunn" in t and "part of the $1,000 owed" in t.replace("$400", "$400"), t)
    check("Cara's name + exact 1,000 is also likely", "Cara Dunn payment" in t.split("## Likely")[1], t)
    check("two Dunns for the same amount: asks which", "Could be more than one invoice" in t and "CUT-2026-004" in t.split("Could be more than one")[1] and "CUT-2026-005" in t.split("Could be more than one")[1], t)
    check("a credit in a different currency is never matched to a USD invoice", "2026-11-18" in t.split("No invoice fits")[1], t)
    check("an unknown sender is listed as no invoice fits", "Mystery sender" in t.split("No invoice fits")[1])
    check("nothing is applied without --apply", CD.read_cash(SLUG) == [] and not M.read_ledger(SLUG))
    check("the report is saved next to the statement", (d / "statements" / "grey-match.md").exists())
    check("dates like 2026-11-10 raise no ambiguity note", "ambiguous" not in t)

    # apply: only the SURE ones
    t2 = M.report(SLUG, "grey.csv", apply=True, today=NOV20)
    cash = CD.read_cash(SLUG)
    check("--apply records the two SURE matches (600 and 295) in the Cash Desk, nothing else", sorted(float(c["amount"]) for c in cash) == [295.0, 600.0] and "## Applied (2)" in t2, str(cash))
    ada = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    check("the invoice shows the payment on the credit's own date", ada["invoices"][0]["payments"][0]["date"] == "2026-11-10" and U.owed(ada["invoices"][0]) == 0)
    bola = json.loads((d / "cuts" / "bola-ade" / "student.json").read_text(encoding="utf-8"))
    check("a fee-short payment is recorded as received (295) and the 5 stays owed, for you to decide", U.owed(bola["invoices"][0]) == 5.0 and "short" in t2.lower())
    check("the likely ones were left alone", json.loads((d / "clients" / "acme-dental" / "client.json").read_text(encoding="utf-8"))["invoices"][0]["payments"] == [] if (d / "clients").exists() else True)
    t3 = M.report(SLUG, "grey.csv", apply=True, today=NOV20)
    check("running --apply again applies nothing and shows the lines as seen before", "Seen before (2)" in t3 and len(CD.read_cash(SLUG)) == 2 and "## Applied" not in t3, t3)

    # the payment already recorded by hand
    CL.paid(f"{SLUG}/acme-dental", "INV-2026-001", 750, "2026-11-15", NOV20)
    (d / "statements" / "late.csv").write_text("Date,Description,Amount,Currency,Status\n2026-11-16,Payment from the dental practice,750.00,USD,Completed\n", encoding="utf-8")
    t4 = M.report(SLUG, "late.csv", today=NOV20)
    check("a credit matching a payment you already recorded (same amount, within 3 days) is not treated as new income", "Already recorded" in t4 and "INV-2026-001" in t4 and "No invoice fits" not in t4, t4)

    # Payoneer-like: semicolons, day first, separate credit and debit, European decimals
    PAYONEER = "Transaction Date;Description;Debit;Credit;Currency;Status\n15/11/2026;Payment from Cara Dunn CUT-2026-003;;1000,00;USD;Completed\n20/11/2026;Withdrawal fee;12,00;;USD;Completed\n"
    (d / "statements" / "payoneer.csv").write_text(PAYONEER, encoding="utf-8")
    t5 = M.report(SLUG, "payoneer.csv", today=NOV20)
    check("semicolons, day-first dates (20/11 proves it), European decimals and a separate credit column all read; the fee line is a debit", "1 credit(s) read" in t5 and "1 debit(s)" in t5 and "CUT-2026-003 Cara Dunn" in t5.split("## Sure matches")[1].split("##")[0], t5)

    # signed amounts with a Type column
    TYPED = "Date,Type,Amount,Description,Status\n2026-11-10,Credit,500.00,Payment CUT-2026-004 Dan Dunn,Completed\n2026-11-10,Debit,500.00,Payout,Completed\n2026-11-11,Transfer out,40.00,Withdrawal,Completed\n"
    (d / "statements" / "typed.csv").write_text(TYPED, encoding="utf-8")
    t6 = M.report(SLUG, "typed.csv", today=NOV20)
    check("a Type column separates credits from debits", "1 credit(s) read" in t6 and "2 debit(s)" in t6 and "CUT-2026-004 Dan Dunn" in t6, t6)

    # ambiguous dates
    (d / "statements" / "amb.csv").write_text("Date,Description,Amount\n03/04/2026,Payment CUT-2026-005 Dee Dunn,500\n", encoding="utf-8")
    check("dates that could be either way are read day first and the report says so", "read day first" in M.report(SLUG, "amb.csv", today=NOV20))
    check("--monthfirst reads them the other way", "read day first" not in M.report(SLUG, "amb.csv", monthfirst=True, today=NOV20))

    # before the invoice was issued
    (d / "statements" / "early.csv").write_text("Date,Description,Amount,Currency\n2026-11-01,Payment CUT-2026-005 Dee Dunn,500.00,USD\n", encoding="utf-8")
    t7 = M.report(SLUG, "early.csv", today=NOV20)
    check("a credit from before the invoice was issued is never SURE: it is shown as likely, with the reason", "arrived before the invoice was issued" in t7 and "Sure matches" not in t7 and "## Likely" in t7, t7)

    # two credits for one invoice
    (d / "statements" / "twice.csv").write_text("Date,Description,Amount,Currency\n2026-11-12,CUT-2026-005 Dee Dunn,500.00,USD\n2026-11-13,CUT-2026-005 Dee Dunn,500.00,USD\n", encoding="utf-8")
    t8 = M.report(SLUG, "twice.csv", today=NOV20)
    check("two credits for one 500 invoice: only the first is SURE, the second finds nothing owed", t8.count("-> CUT-2026-005") == 1 and "No invoice fits" in t8, t8)

    # DFY months: applying also tells Citadel
    class Fake:
        def __init__(self):
            self.calls = []

        def rpc(self, n, p):
            self.calls.append((n, p))
            return {"ok": True}
    ds = json.loads((d / "cuts" / "dee-dunn" / "student.json").read_text(encoding="utf-8"))
    ds["statements"][0]["citadel_id"] = "m-77"
    (d / "cuts" / "dee-dunn" / "student.json").write_text(json.dumps(ds), encoding="utf-8")
    fk = Fake()
    (d / "statements" / "dfy.csv").write_text("Date,Description,Amount,Currency\n2026-11-14,CUT-2026-005 Dee Dunn,500.00,USD\n", encoding="utf-8")
    M.report(SLUG, "dfy.csv", apply=True, api=fk, today=NOV20)
    check("applying a DFY month tells Citadel it was received", any(c[0] == "hq_dfy_mark_received" and c[1]["p_month_id"] == "m-77" for c in fk.calls), str(fk.calls))

    # errors
    check("a missing statement lists what is there", "grey.csv" in (raises(M.report, SLUG, "nope.csv") or ""))
    (d / "statements" / "bad.csv").write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    check("a file without date and amount columns says what it found", "Foo" in (raises(M.report, SLUG, "bad.csv") or ""))
    check("a bad tolerance is refused", raises(M.report, SLUG, "grey.csv", tolerance=500) is not None)
    (d / "statements" / "empty.csv").write_text("Date,Description,Amount\n", encoding="utf-8")
    check("a statement with no credits says so", "no credits" in M.report(SLUG, "empty.csv", today=NOV20))
    (d / "statements" / "tol.csv").write_text("Date,Description,Amount,Currency\n2026-11-19,CUT-2026-003 Cara Dunn,960.00,USD\n", encoding="utf-8")
    check("40 short on 1,000 is more than the default fee allowance (20): LIKELY, not SURE", "Sure matches" not in M.report(SLUG, "tol.csv", today=NOV20) and "## Likely" in M.report(SLUG, "tol.csv", today=NOV20))
    check("with --tolerance 50 the same credit is SURE and short by 40", "$40 short, within a normal transfer fee" in M.report(SLUG, "tol.csv", tolerance=50, today=NOV20))
    (ROOT / "engines" / "zz-match2").mkdir(exist_ok=True)
    (ROOT / "engines" / "zz-match2" / "engine.json").write_text(json.dumps({"name": "m2", "path": "smb"}), encoding="utf-8")
    check("an engine with no invoices is explained", "no invoices yet" in (raises(M.report, "zz-match2", str(d / "statements" / "grey.csv")) or ""))
    shutil.rmtree(ROOT / "engines" / "zz-match2", ignore_errors=True)
    check("no em dash in any report", all(chr(0x2014) not in x for x in (t, t2, t4, t5, t6, t7, t8)))
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
