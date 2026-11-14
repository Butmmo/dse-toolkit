"""Tests for the Cut Desk: the percentage cut students owe, from agreement to money received.   python tests/test_cuts.py"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cashdesk as CD, cuts as U, review as RV  # noqa: E402

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


SLUG = "zz-cut"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Cut test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "postal_address": "1 Main St", "archived": False}), encoding="utf-8")
DEC3 = dt.date(2026, 12, 3)
NOV14 = dt.date(2026, 11, 14)
ADA = f"{SLUG}/ada-obi"
try:
    # ---- add
    for name, kw in {"no name": {"name": " "}, "percent 0": {"percent": 0}, "percent 70": {"percent": 70}, "bad basis": {"basis": "x"}, "bad currency": {"currency": "NGN"},
                     "bad method": {"method": "cash"}, "bad email": {"email": "nope"}, "due days 99": {"due_days": 99}}.items():
        args = {"name": "Ada Obi", "percent": 10, **kw}
        check(f"add refused: {name}", raises(U.add, SLUG, today=NOV14, **args) is not None)
    t = U.add(SLUG, "Ada Obi", 10, "gross", "USD", "grey", "ada@example.com", 7, "2026-09-01", NOV14)
    s = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    check("student saved with the agreement terms", s["percent"] == 10 and s["basis"] == "gross" and s["method"] == "grey" and s["start"] == "2026-09-01" and s["status"] == "active")
    ag = (d / "cuts" / "ada-obi" / "agreement.md").read_text(encoding="utf-8")
    check("agreement: company and RC number, the percent and basis, reporting day, fees borne by the student, placeholders and the not-legal-advice line",
          "RC 8867648" in ag and "10% of the gross amount" in ag and "7th of each month" in ag and "You cover the transfer fees" in ag and "[the law that applies" in ag and "not legal advice" in ag, ag[:300])
    check("add says nothing was sent and flags missing payment details", "Nothing was sent" in t and "payment-details-grey.txt" in t)
    check("the same student twice refused", "already set up" in (raises(U.add, SLUG, "Ada Obi", 10, today=NOV14) or ""))
    check("net basis agreement wording", "after the platform's own fees" in U.agreement(SLUG, {**s, "basis": "net"}, {"name": "x"}))
    (d / "payment-details-grey.txt").write_text("Grey USD account: use the details shown in your Grey app", encoding="utf-8")

    # ---- report: gross basis
    r = U.report(ADA, "2026-09", 3200, 0, "Sept statement in /proofs/ada-sep.png", False, dt.date(2026, 10, 3))
    s = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    check("cut = 10% of 3,200 = 320; invoice CUT-2026-001 due 7 days after", s["statements"][0]["cut"] == 320 and s["invoices"][0]["id"] == "CUT-2026-001" and s["invoices"][0]["due"] == "2026-10-10", r)
    page = (d / "cuts" / "ada-obi" / "invoices" / "CUT-2026-001.html").read_text(encoding="utf-8")
    check("invoice page: company details, the student, the amount, the Grey details from the local file", "Bolu Ade" in page and "Ada Obi" in page and "$320" in page and "Grey USD account" in page and "payment-details" not in page)
    check("report says nothing was sent", "Nothing was sent" in r)
    check("the month cannot be reported twice", "already reported" in (raises(U.report, ADA, "2026-09", 100, 0, "p", False, DEC3) or ""))
    check("future month, before the start, bad month, silly numbers: all refused", raises(U.report, ADA, "2027-05", 1, 0, "p", False, NOV14) and raises(U.report, ADA, "2026-08", 1, 0, "p", False, NOV14) and raises(U.report, ADA, "Nov", 1, 0, "p", False, NOV14)
          and raises(U.report, ADA, "2026-10", -5, 0, "p", False, NOV14) and raises(U.report, ADA, "2026-10", 100, 200, "p", False, NOV14))
    r = U.report(ADA, "2026-10", 3000, 0, "", False, dt.date(2026, 11, 4))
    check("no proof is noted, plainly", "No proof noted" in r)
    r = U.report(ADA, "2026-11", 1000, 0, "Nov statement", False, DEC3)
    check("a drop to under half the recent average gets a friendly prompt, not an accusation", "less than half of their recent average ($3,100)" in r and "friendly question" in r and "fraud" not in r.lower(), r)
    U.add(SLUG, "Dee Drift", 10, "gross", "USD", "grey", "", 7, "2026-01-01", NOV14)
    for mth, amt in (("2026-01", 5000), ("2026-02", 100), ("2026-03", 100), ("2026-04", 100)):
        U.report(f"{SLUG}/dee-drift", mth, amt, 0, "p", False, DEC3)
    r = U.report(f"{SLUG}/dee-drift", "2026-05", 80, 0, "p", False, DEC3)
    check("the recent average uses only the last three months (100, 100, 100), so 80 is no drop", "less than half" not in r, r)
    U.set_status(f"{SLUG}/dee-drift", "ended")

    # ---- zero month
    U.add(SLUG, "Zed Zero", 15, "gross", "USD", "payoneer", "", 7, "2026-11-01", NOV14)
    r = U.report(f"{SLUG}/zed-zero", "2026-11", 0, 0, "Nov statement shows 0", False, DEC3)
    check("a zero report is valid and creates no invoice", "no invoice" in r.lower() and json.loads((d / "cuts" / "zed-zero" / "student.json").read_text(encoding="utf-8"))["invoices"] == [])

    # ---- net basis
    U.add(SLUG, "Ben Net", 10, "net", "GBP", "payoneer", "", 14, "2026-11-01", NOV14)
    r = U.report(f"{SLUG}/ben-net", "2026-11", 1000, 200, "Nov statement", False, DEC3)
    bs = json.loads((d / "cuts" / "ben-net" / "student.json").read_text(encoding="utf-8"))
    check("net basis: 10% of (1,000 - 200) = 80, in pounds, due in 14 days", bs["statements"][0]["cut"] == 80 and bs["invoices"][0]["due"] == "2026-12-17" and "£80" in r, r)
    check("no payoneer details: the report says where to put them", "payment-details-payoneer.txt" in r)
    (d / "payment-details.txt").write_text("Fallback details", encoding="utf-8")
    check("payment-details.txt is the fallback for any method", "Fallback details" in __import__("dse.clients", fromlist=["x"]).payment_details(SLUG, "payoneer"))

    # ---- replace
    r = U.report(f"{SLUG}/ben-net", "2026-11", 1500, 300, "Corrected statement", True, DEC3)
    bs = json.loads((d / "cuts" / "ben-net" / "student.json").read_text(encoding="utf-8"))
    check("replace corrects an unpaid month: one statement, one invoice, new amount 120", len(bs["statements"]) == 1 and len(bs["invoices"]) == 1 and bs["invoices"][0]["amount"] == 120, str(bs))

    # ---- paid
    inv1 = "CUT-2026-001"
    r = U.paid(ADA, inv1, 300, "2026-11-10", False, NOV14)
    check("a payment that comes in short says so and offers to ask the student or write it off", "short" in r and "$20" in r and "--writeoff" in r, r)
    cash = CD.read_cash(SLUG)
    check("the Cash Desk got 300 as commission with the invoice, student and month in the note", cash and cash[0]["amount"] == "300.00" and cash[0]["kind"] == "commission" and "CUT-2026-001" in cash[0]["note"] and "Ada Obi" in cash[0]["note"] and "2026-09" in cash[0]["note"], str(cash))
    check("overpaying is refused", "at most what is still owed" in (raises(U.paid, ADA, inv1, 50, "", False, NOV14) or ""))
    check("an unknown invoice is explained", "CUT-2026-001" in (raises(U.paid, ADA, "CUT-1", 0, "", False, NOV14) or ""))
    r = U.paid(ADA, inv1, 20, "2026-11-12", False, NOV14)
    check("the rest settles it", "settled" in r)
    check("a settled invoice cannot be paid again", "already settled" in (raises(U.paid, ADA, inv1, 5, "", False, NOV14) or ""))
    check("a paid month cannot be replaced", "cannot be replaced" in (raises(U.report, ADA, "2026-09", 100, 0, "p", True, DEC3) or ""))
    r = U.paid(ADA, "CUT-2026-002", 290, "2026-12-05", True, dt.date(2026, 12, 5))
    ai = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))["invoices"][1]
    check("--writeoff accepts the shortfall (300 - 290 = 10) on the record", ai["writeoff"] == 10 and "written off" in r and "settled" in r, r)
    ben_id = json.loads((d / "cuts" / "ben-net" / "student.json").read_text(encoding="utf-8"))["invoices"][0]["id"]
    r = U.paid(f"{SLUG}/ben-net", ben_id, 0, "2026-12-10", False, dt.date(2026, 12, 10))
    check("GBP payments say they wait for an exchange rate, with the command", "recorded in GBP" in r and "fx add" in r, r)
    dec = lambda: CD.month_data(SLUG, dt.date(2026, 12, 1), dt.date(2026, 12, 31))  # noqa: E731
    check("without a rate the 120 GBP is NOT added to the dollars: December = 290, and it is listed as not counted", dec()["received"] == 290.0 and len(dec()["unconverted"]) == 1 and dec()["by_currency"] == {"USD": 290.0, "GBP": 120.0}, str(dec()["by_currency"]))
    from dse import fx as FX  # noqa: E402
    FX.add_rate(SLUG, "GBP", "USD", 1.25, "2026-12-01", "test rate", dt.date(2026, 12, 12))
    check("with a rate you entered the pounds count: 290 + 120 x 1.25 = 440", dec()["received"] == 440.0 and not dec()["unconverted"], str(dec()["received"]))

    # ---- quiet students, deadlines, status
    s2 = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    s2["statements"] = [x for x in s2["statements"] if x["month"] == "2026-09"]
    check("missing months: September reported, October overdue to report on 14 Nov (deadline 7 Nov), November not yet", U.missing_months(s2, NOV14) == ["2026-10"], str(U.missing_months(s2, NOV14)))
    check("before the 7th the previous month is not yet late", U.missing_months(s2, dt.date(2026, 11, 5)) == [])
    s2["status"] = "paused"
    check("a paused student is never chased", U.missing_months(s2, NOV14) == [])
    check("status change and refusal", "ended" in U.set_status(ADA, "ended") and "ended" in (raises(U.report, ADA, "2026-11", 1, 0, "p", False, DEC3) or "") and "active" in U.set_status(ADA, "active") and raises(U.set_status, ADA, "boss"))

    # ---- list / show / attention / review
    U.add(SLUG, "Quiet Quinn", 10, "gross", "USD", "grey", "", 7, "2026-09-01", NOV14)
    lst = U.listing(SLUG, NOV14)
    check("list shows each student, the totals and what each needs", "Ada Obi" in lst and "Quiet Quinn" in lst and "report for 2026-09, 2026-10" in lst and "Totals" in lst, lst)
    sh = U.show(ADA, DEC3)
    check("show: months with earnings, cut and invoice state", "2026-09: earned $3,200, cut $320; CUT-2026-001 settled" in sh and "no proof noted" in sh, sh)
    att = U.attention(SLUG, DEC3)
    check("attention: Quinn is quiet; Ben's invoice (due Dec 17) is not overdue on Dec 3", [q["student"] for q in att["quiet"]] == ["Quiet Quinn"] and att["overdue"] == [], str(att))
    att2 = U.attention(SLUG, dt.date(2027, 3, 1))
    check("later, Ada's unpaid November invoice (100, due Dec 10) is overdue", any(i["student"] == "Ada Obi" and i["owed"] == 100 for i in att2["overdue"]), str(att2["overdue"]))
    g = RV.gather(SLUG, DEC3)
    mv = RV.moves(g)
    check("Weekly Review: students who have not reported (rank 3.6) with the next step", any(m["rank"] == 3.6 and "Quiet Quinn" in m["do"] and "cut report" in m["how"] for m in mv), str([(m["rank"], m["do"]) for m in mv]))
    check("Weekly Review order stays sorted", [m["rank"] for m in mv] == sorted(m["rank"] for m in mv))
    check("resolve errors are explained", "engine/student-name" in (raises(U.resolve, "ada") or "") and "No student" in (raises(U.resolve, f"{SLUG}/ghost") or "") and raises(U.resolve, "../../x/student.json") is not None)
    check("no em dash in the agreement, report, list or invoice", all(chr(0x2014) not in x for x in (ag, r, lst, sh, page)))
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
