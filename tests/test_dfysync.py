"""Tests for the DFY terms in the Cut Desk and the bridge with Citadel's DFY Tracker (fake Citadel, no network).   python tests/test_dfysync.py"""
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cashdesk as CD, cuts as U, dfysync as S  # noqa: E402

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


class FakeApi:
    def __init__(self, months=None):
        self.months, self.calls, self.fail, self.published = months or [], [], False, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        if name == "hq_dfy_pull":
            return self.months
        if name == "hq_dfy_mark_received":
            if self.fail:
                raise RuntimeError("down")
            return {"ok": True}
        if name == "hq_set_payout_accounts":
            self.published = params["p_accounts"]
            return {"published": len(self.published)}
        if name == "hq_get_payout_accounts":
            return [{"currency": a["currency"], "label": a["label"]} for a in self.published]
        raise RuntimeError("unknown " + name)


def month(i, user, email, name, period, net, status="submitted", paid=False):
    return {"id": f"m-{i}", "user_id": user, "email": email, "full_name": name, "period_month": period + "-01", "net_income_usd": net, "qualified": net >= 2000,
            "remittance_owed_usd": round(net * 0.2, 2), "remittance_paid": paid, "status": status, "notes": None}


TODAY = dt.date(2026, 12, 3)
SLUG = "zz-dfy"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "DFY test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "archived": False}), encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="dfy-test-"))
S.CONFIG = TMP / "dfy-sync.json"
try:
    # ---- the DFY terms
    t = U.add(SLUG, "Terms Tester", 99, "gross", "GBP", "grey", "", 7, "2026-01-01", TODAY, program="dfy")
    s = json.loads((d / "cuts" / "terms-tester" / "student.json").read_text(encoding="utf-8"))
    check("program dfy forces the real terms: 20%, net basis, USD, cap 18,000, qualified at 2,000, 12 months", s["percent"] == 20 and s["basis"] == "net" and s["currency"] == "USD" and s["cap"] == 18000 and s["threshold"] == 2000 and s["months_target"] == 12 and s["program"] == "dfy")
    ag = (d / "cuts" / "terms-tester" / "agreement.md").read_text(encoding="utf-8")
    check("the DFY agreement carries Citadel's disclosure word for word", U.DFY_DISCLOSURE in ag and "RC 8867648" in ag and "$2,000 or more" in ag and "not legal advice" in ag, ag[:200])
    check("add explains the terms", "20% of net income, capped at $18,000" in t)
    check("an unknown program is refused", raises(U.add, SLUG, "X Y", 10, today=TODAY, program="weird") is not None)
    T = f"{SLUG}/terms-tester"
    r = U.report(T, "2026-01", 3000, 0, "p", False, TODAY)
    st = json.loads((d / "cuts" / "terms-tester" / "student.json").read_text(encoding="utf-8"))
    check("3,000 net: cut 600, a qualified month, progress shown", st["statements"][0]["cut"] == 600 and st["statements"][0]["qualified"] and "1 of 12 qualified months" in r, r)
    r = U.report(T, "2026-02", 1999, 0, "p", False, TODAY)
    st = json.loads((d / "cuts" / "terms-tester" / "student.json").read_text(encoding="utf-8"))
    check("1,999 net: cut 399.80 and NOT a qualified month", st["statements"][1]["cut"] == 399.8 and not st["statements"][1]["qualified"] and "1 of 12" in r, r)
    check("DFY has no platform fees to enter", "no platform fees" in (raises(U.report, T, "2026-03", 3000, 100, "p", False, TODAY) or ""))

    # twelve qualified months end it
    U.add(SLUG, "Twelve Months", 20, today=TODAY, start="2025-12-01", program="dfy")
    T12 = f"{SLUG}/twelve-months"
    last = ""
    for m in ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]:
        last = U.report(T12, m, 2000, 0, "p", False, TODAY)
    check("the 12th qualified month completes the DFY", "12 qualified months reached" in last and "complete" in last, last)
    check("status becomes completed", json.loads((d / "cuts" / "twelve-months" / "student.json").read_text(encoding="utf-8"))["status"] == "completed")
    check("nothing more can be reported once complete", "complete" in (raises(U.report, T12, "2026-12", 2000, 0, "p", False, TODAY) or ""))
    check("a completed student is not chased for reports", U.missing_months(json.loads((d / "cuts" / "twelve-months" / "student.json").read_text(encoding="utf-8")), dt.date(2027, 6, 1)) == [])

    # the cap ends it, and the last month is cut down to the room left
    U.add(SLUG, "Cap Hitter", 20, today=TODAY, start="2026-01-01", program="dfy")
    TC = f"{SLUG}/cap-hitter"
    for m in ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]:
        U.report(TC, m, 10000, 0, "p", False, TODAY)               # 8 x 2,000 = 16,000
    r = U.report(TC, "2026-09", 12000, 0, "p", False, TODAY)       # would be 2,400; only 2,000 left
    cs = json.loads((d / "cuts" / "cap-hitter" / "student.json").read_text(encoding="utf-8"))
    check("the 9th month is cut to the 2,000 left under the $18,000 cap and says why", cs["statements"][-1]["cut"] == 2000 and "cap leaves only $2,000 of this month's $2,400" in r, r)
    check("the cap completes the DFY, with 9 qualified months", cs["status"] == "completed" and "cap is reached" in r.lower())
    check("total remitted is exactly 18,000", sum(x["cut"] for x in cs["statements"]) == 18000)

    # ---- sync from Citadel
    S_ = FakeApi([
        month(1, "u1", "ada@x.example", "Ada Obi", "2026-09", 3000),
        month(2, "u1", "ada@x.example", "Ada Obi", "2026-10", 2500, "remittance_paid", True),
        month(3, "u2", "bola@x.example", "Bola Ade", "2026-11", 1000),
        month(4, "u1", "ada@x.example", "Ada Obi", "2026-08", 1800, "disputed"),
        {"id": "bad", "period_month": "nonsense"},
        {"nope": 1},
    ])
    out = S.sync(SLUG, S_.months, S_, TODAY)
    ada = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    check("two new students are created with the DFY terms and their Citadel ids", "Ada Obi" in out and "Bola Ade" in out and ada["program"] == "dfy" and ada["citadel_user_id"] == "u1" and ada["email"] == "ada@x.example")
    check("each filed month becomes a statement (3,000 net -> 600) tied to the Citadel month", [x["month"] for x in ada["statements"]] == ["2026-09", "2026-10"] and ada["statements"][0]["cut"] == 600 and ada["statements"][0]["citadel_id"] == "m-1" and ada["statements"][0]["source"] == "citadel")
    check("a month Citadel already shows as paid is recorded as paid here, as history", ada["invoices"][1]["payments"][0]["from_citadel"] and U.owed(ada["invoices"][1]) == 0 and "history" in out)
    check("history is NOT added to the Cash Desk again", CD.read_cash(SLUG) == [])
    check("a disputed month is listed, not invoiced", "Disputed" in out and "2026-08" in out and all(x["month"] != "2026-08" for x in ada["statements"]))
    check("rows without the needed fields are ignored", len(ada["statements"]) == 2)
    check("a month that starts before the agreement start moves the start back", ada["start"] <= "2026-09-01")
    sep_id = ada["statements"][0]["invoice"]
    bola_id = json.loads((d / "cuts" / "bola-ade" / "student.json").read_text(encoding="utf-8"))["statements"][0]["invoice"]
    out2 = S.sync(SLUG, S_.months, S_, TODAY)
    check("running it again finds nothing new and changes nothing", "Nothing new" in out2 and len(json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))["statements"]) == 2)

    # a student changes a figure
    S_.months[0] = month(1, "u1", "ada@x.example", "Ada Obi", "2026-09", 3500)
    S_.months[1] = month(2, "u1", "ada@x.example", "Ada Obi", "2026-10", 2600, "remittance_paid", True)
    out3 = S.sync(SLUG, S_.months, S_, TODAY)
    ada = json.loads((d / "cuts" / "ada-obi" / "student.json").read_text(encoding="utf-8"))
    check("an unpaid month whose figure changed is updated, with the same invoice number", ada["statements"][0]["earned"] == 3500 and ada["statements"][0]["cut"] == 700 and next(i for i in ada["invoices"] if i["id"] == sep_id)["amount"] == 700 and len(ada["invoices"]) == 2 and "updated" in out3, out3)
    check("a PAID month whose figure changed is flagged and left alone", ada["statements"][1]["earned"] == 2500 and "Check with them" in out3, out3)

    # recording money pushes to Citadel
    S_.calls.clear()
    r = U.paid(f"{SLUG}/ada-obi", sep_id, 0, "2026-12-02", False, TODAY, S_)
    check("paying an invoice tells Citadel the month is received, with the month's id", ("hq_dfy_mark_received", {"p_month_id": "m-1", "p_note": "Received via grey (HQ Cut Desk)"}) in S_.calls and "Marked received in Citadel" in r, r)
    cash = CD.read_cash(SLUG)
    check("and the Cash Desk got the 700", len(cash) == 1 and cash[0]["amount"] == "700.00" and cash[0]["kind"] == "commission", str(cash))
    S_.calls.clear()
    out4 = S.sync(SLUG, S_.months, S_, TODAY)
    check("no second push for a month already marked", not any(c[0] == "hq_dfy_mark_received" for c in S_.calls))

    # a short payment is recorded but does NOT tell Citadel the month is paid
    U.add(SLUG, "Short Payer", 20, today=TODAY, program="dfy", start="2026-11-01", email="short@x.example")
    S_.months.append(month(30, "u7", "short@x.example", "Short Payer", "2026-11", 5000))
    S.sync(SLUG, S_.months, S_, TODAY)
    sp = json.loads((d / "cuts" / "short-payer" / "student.json").read_text(encoding="utf-8"))
    S_.calls.clear()
    r = U.paid(f"{SLUG}/short-payer", sp["statements"][0]["invoice"], 950, "2026-12-03", False, TODAY, S_)
    check("a short payment is recorded but Citadel is not told the month is paid", "short" in r and not any(c[0] == "hq_dfy_mark_received" for c in S_.calls), r)
    r = U.paid(f"{SLUG}/short-payer", sp["statements"][0]["invoice"], 0, "2026-12-04", True, TODAY, S_)
    check("settling the rest tells Citadel once", sum(1 for c in S_.calls if c[0] == "hq_dfy_mark_received") == 1 and "Marked received in Citadel" in r, r)
    check("show displays the DFY progress", "qualified months" in U.show(f"{SLUG}/short-payer", TODAY) and "of $18,000" in U.show(f"{SLUG}/short-payer", TODAY))

    # a failed push is queued and retried
    bola = f"{SLUG}/bola-ade"
    S_.fail = True
    r = U.paid(bola, bola_id, 0, "2026-12-03", False, TODAY, S_)
    b = json.loads((d / "cuts" / "bola-ade" / "student.json").read_text(encoding="utf-8"))
    check("if Citadel cannot be reached the payment is still recorded and the push is queued", "retry at the next sync" in r and b["statements"][0]["push_pending"] and not b["statements"][0].get("citadel_paid") and U.owed(b["invoices"][0]) == 0, r)
    S_.fail = False
    out5 = S.sync(SLUG, S_.months, S_, TODAY)
    b = json.loads((d / "cuts" / "bola-ade" / "student.json").read_text(encoding="utf-8"))
    check("the next sync pushes it and says so", b["statements"][0]["citadel_paid"] and not b["statements"][0]["push_pending"] and "Marked received in Citadel after an earlier failure" in out5, out5)
    S_.months[2] = {**S_.months[2], "remittance_paid": True}
    S.get_api = lambda: None
    U.add(SLUG, "No Link", 20, today=TODAY, program="dfy", start="2026-11-01")
    U.report(f"{SLUG}/no-link", "2026-11", 4000, 0, "p", False, TODAY)
    nl = json.loads((d / "cuts" / "no-link" / "student.json").read_text(encoding="utf-8"))
    check("a hand-entered student has no Citadel month, so nothing is pushed", not nl["statements"][0]["citadel_id"] and "Citadel" not in U.paid(f"{SLUG}/no-link", nl["invoices"][0]["id"], 0, "2026-12-03", False, TODAY, None))

    # a hand-entered month that Citadel also has
    U.add(SLUG, "Both Ways", 20, today=TODAY, program="dfy", start="2026-10-01", email="both@x.example")
    U.report(f"{SLUG}/both-ways", "2026-10", 3000, 0, "by hand", False, TODAY)
    out6 = S.sync(SLUG, [month(9, "u9", "both@x.example", "Both Ways", "2026-10", 3000)], FakeApi(), TODAY)
    bw = json.loads((d / "cuts" / "both-ways" / "student.json").read_text(encoding="utf-8"))
    check("a student is matched by email, and a month already entered by hand is left alone with a note", "already entered this month by hand" in out6 and len(bw["statements"]) == 1 and bw["citadel_user_id"] == "u9", out6)

    # after completion
    out7 = S.sync(SLUG, [month(20, "u3", "twelve@x.example", "Twelve Months", "2026-12", 3000)], FakeApi(), TODAY)
    check("a month filed after the DFY was complete is listed as nothing owed", "nothing owed" in out7 or "Twelve" in out7, out7)

    # ---- connection
    check("sync without a connection explains how to fix it", "not connected" in (raises(S.run, SLUG, None) or ""))
    class Broken:
        def rpc(self, n, p):
            raise RuntimeError("function does not exist")
    check("a missing SQL file is explained", "20261118140000_dfy_bridge_payout_accounts.sql" in (raises(S.run, SLUG, Broken()) or ""))

    # ---- auto
    check("auto on saves the engine, off removes it", "on for engine" in S.set_auto(SLUG, True) and S.auto_engine() == SLUG and "off" in S.set_auto(SLUG, False) and S.auto_engine() == "")

    # ---- payout accounts
    GOOD = [{"currency": "USD", "method": "grey", "label": "Grey USD account", "bank_name": "Grey", "account_name": "D'Famocious Ltd", "account_number": "12345678", "extra": [{"label": "ACH Routing", "value": "0123"}], "note": ""},
            {"currency": "USD", "method": "payoneer", "label": "Payoneer", "bank_name": "Payoneer", "account_name": "D'Famocious Ltd", "account_number": "pay@example.com"}]
    v = S.validate_accounts(GOOD)
    check("good accounts validate and are cleaned", len(v) == 2 and v[0]["extra"][0]["label"] == "ACH Routing" and v[1]["extra"] == [] and v[0]["active"] is True)
    bad = {"placeholder": [{**GOOD[0], "account_number": "[from your app]"}], "no usd": [{**GOOD[0], "currency": "NGN"}], "bad method": [{**GOOD[0], "method": "cash"}], "bad currency": [{**GOOD[0], "currency": "EUR"}],
           "missing field": [{**GOOD[0], "account_name": ""}], "empty": [], "too many": [GOOD[0]] * 9, "extra placeholder": [{**GOOD[0], "extra": [{"label": "A", "value": "[x]"}]}], "not a list": {"a": 1}}
    for name, items in bad.items():
        check(f"refused: {name}", raises(S.validate_accounts, items) is not None)
    check("the example file is refused as it stands (it is full of placeholders)", raises(S.validate_accounts, json.loads(S.EXAMPLE.read_text(encoding="utf-8"))) is not None)
    check("no file yet says how to start", "--example" in S.accounts(SLUG))
    check("the example is copied once, then left alone", "Copied the example" in S.accounts(SLUG, add_example=True) and "already exists" in S.accounts(SLUG, add_example=True))
    check("an unfinished file is reported as not ready, not published", "Not ready to publish" in S.accounts(SLUG) and raises(S.accounts, SLUG, True, False, FakeApi()) is not None)
    S.accounts_path(SLUG).write_text(json.dumps(GOOD), encoding="utf-8")
    api = FakeApi()
    out8 = S.accounts(SLUG, False, False, api)
    check("a valid file lists the accounts and offers to publish", "valid: 2 account" in out8 and "--publish" in out8 and not api.published, out8)
    out9 = S.accounts(SLUG, True, False, api)
    check("publishing sends the cleaned list to Citadel", len(api.published) == 2 and api.published[0]["bank_name"] == "Grey" and "Published 2 account" in out9, out9)
    check("afterwards the check shows what students see", "Students currently see" in S.accounts(SLUG, False, False, api) and "Grey USD account" in S.accounts(SLUG, False, False, api))
    S.get_api = lambda: None
    check("publishing without a connection is explained", "not connected" in (raises(S.accounts, SLUG, True) or ""))
    check("no em dash anywhere in the sync output, agreement or example", all(chr(0x2014) not in x for x in (out, out3, out5, out8, ag, S.EXAMPLE.read_text(encoding="utf-8"))))
finally:
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
