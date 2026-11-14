"""Tests for the Student Success Desk: progress, flags with facts, kind drafts, forecast.   python tests/test_success.py"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cashdesk as CD, cuts as U, review as RV, success as S  # noqa: E402

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


SLUG = "zz-success"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Success test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "archived": False}), encoding="utf-8")
TODAY = dt.date(2026, 12, 10)
D9 = dt.date(2026, 12, 9)


def mk(name, start, vals, rep_today=D9, program="dfy", status=""):
    U.add(SLUG, name, 20, today=D9, start=f"{start}-01", program=program)
    t = f"{SLUG}/{name.lower().replace(' ', '-')}"
    for i, v in enumerate(vals):
        U.report(t, S.month_add(start, i), v, 0, "p", False, rep_today)
    if status:
        U.set_status(t, status)
    return t


try:
    # month helpers
    check("month helpers", S.month_add("2026-11", 3) == "2027-02" and S.month_add("2026-01", -1) == "2025-12" and S.month_name("2026-11") == "Nov 2026" and S.last_complete(TODAY) == "2026-11")
    check("elapsed months from the start through last month", S.elapsed_months("2026-06-01", TODAY) == 6 and S.elapsed_months("2026-12-01", TODAY) == 0)

    mk("Steady Sam", "2026-06", [2500, 2600, 2400, 2800, 3000, 3200])
    U.add(SLUG, "Quiet Quinn", 20, today=D9, start="2026-08-01", program="dfy")
    U.report(f"{SLUG}/quiet-quinn", "2026-08", 2500, 0, "p", False, D9)
    mk("Close Cleo", "2026-09", [1800, 1700, 1900])
    mk("Drop Dara", "2026-08", [4000, 4200, 4100, 1500])
    mk("Zero Zed", "2026-09", [0, 0, 0])
    mk("Late Lou", "2026-11", [3000], rep_today=dt.date(2026, 11, 20))          # invoice due Nov 27
    mk("Almost Ann", "2026-02", [2500] * 10)
    mk("Paused Pat", "2026-09", [1000, 1000, 1000], status="paused")
    mk("Capped Cap", "2026-03", [10000] * 8)
    mk("Custom Cory", "2026-09", [500], program="custom")
    U.add(SLUG, "Never Nia", 20, today=D9, start="2026-10-01", program="dfy")

    units = {u["name"]: u for u in S.build_units(SLUG, TODAY)}
    kinds = lambda n: sorted(f["kind"] for f in units[n]["flags"])  # noqa: E731
    fact = lambda n, k: next(f["fact"] for f in units[n]["flags"] if f["kind"] == k)  # noqa: E731

    check("a steady student has no flags", kinds("Steady Sam") == [], str(kinds("Steady Sam")))
    check("quiet: names the months not filed (Sep, Oct, Nov) and is red", kinds("Quiet Quinn") == ["quiet"] and "Sep 2026, Oct 2026, Nov 2026" in fact("Quiet Quinn", "quiet") and units["Quiet Quinn"]["flags"][0]["sev"] == "red", str(units["Quiet Quinn"]["flags"]))
    check("under the line three months running, close to it: an opportunity (info), plus behind pace", kinds("Close Cleo") == ["behind_pace", "under_line"] and "close, an opportunity" in fact("Close Cleo", "under_line") and next(f["sev"] for f in units["Close Cleo"]["flags"] if f["kind"] == "under_line") == "info", str(units["Close Cleo"]["flags"]))
    check("a sharp drop is named with both figures", "drop" in kinds("Drop Dara") and "$1,500" in fact("Drop Dara", "drop") and "$4,100" in fact("Drop Dara", "drop"), str(units["Drop Dara"]["flags"]))
    check("zero months in a row is red", "zero_streak" in kinds("Zero Zed") and next(f["sev"] for f in units["Zero Zed"]["flags"] if f["kind"] == "zero_streak") == "red")
    check("an overdue remittance says how many days and the invoice", "13 day(s) overdue" in fact("Late Lou", "unpaid") and "CUT-2026-" in fact("Late Lou", "unpaid"), str(units["Late Lou"]["flags"]))
    check("overdue by 13 days is amber, by 15 or more red", next(f["sev"] for f in units["Late Lou"]["flags"] if f["kind"] == "unpaid") == "amber" and
          next(f["sev"] for f in S.build_units(SLUG, dt.date(2026, 12, 12)) if f["name"] == "Late Lou" for f in f["flags"] if f["kind"] == "unpaid") == "red")
    check("nearly through DFY: 10 of 12 qualified months is celebrated, not chased", kinds("Almost Ann") == ["near_complete"] and units["Almost Ann"]["flags"][0]["sev"] == "info")
    check("a paused student gets no flags", kinds("Paused Pat") == [])
    check("a student who never filed is told apart from one who went quiet", kinds("Never Nia") == ["no_data"] and "has never filed" in fact("Never Nia", "no_data"), str(units["Never Nia"]["flags"]))
    check("a custom (non-DFY) student gets the general flags only", kinds("Custom Cory") == ["quiet"] or kinds("Custom Cory") == [], str(kinds("Custom Cory")))
    check("progress numbers: qualified months and remitted amount", units["Almost Ann"]["qn"] == 10 and units["Almost Ann"]["total"] == 5000 and units["Capped Cap"]["total"] == 16000, str((units["Almost Ann"]["qn"], units["Almost Ann"]["total"])))

    # drafts
    sender = "Bolu Ade"
    for n, u in units.items():
        for f in u["flags"]:
            t = S.draft(u, f, sender)
            check(f"draft for {n} ({f['kind']}): named, signed, no braces, no em dash, no blame", S.first_name(n) in t and "Bolu Ade" in t and "{" not in t and chr(0x2014) not in t
                  and not any(w in t.lower() for w in ("you failed", "your fault", "lazy", "unacceptable", "must pay now")), t[:160])
    t = S.draft(units["Late Lou"], units["Late Lou"]["flags"][0], sender)
    check("the overdue draft names the month and the due date and offers help if money is tight", "Nov 2026" in t and "2026-11-27" in t and "money is tight" in t, t)
    check("the under-the-line draft quotes their own figures", "$1,800, $1,700, $1,900" in S.draft(units["Close Cleo"], next(f for f in units["Close Cleo"]["flags"] if f["kind"] == "under_line"), sender))

    # forecast
    fc = S.forecast(SLUG, 6, TODAY)
    check("the horizon starts at next month (money arrives the month after it is earned)", fc["months"] == ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"])
    sam = next(r for r in fc["students"] if r["name"] == "Steady Sam")
    check("Steady Sam: LIKELY = average of 2,800, 3,000, 3,200 = 3,000 x 20% = 600 a month", sam["likely_sum"] == 3600.0, str(sam))
    check("Steady Sam: LOW = weakest month 2,800 x 20% = 560 a month", sam["low_sum"] == 3360.0)
    check("Steady Sam finishes DFY when the 12th qualified month is earned (May, arriving June)", sam["likely_done"] == "2027-06", str(sam["likely_done"]))
    cap = next(r for r in fc["students"] if r["name"] == "Capped Cap")
    check("Capped Cap: only the 2,000 the cap leaves, then done (never another 2,000)", cap["likely_sum"] == 2000.0 and cap["low_sum"] == 2000.0, str(cap))
    check("students with fewer than two filed months, paused and custom ones are not forecast; the thin ones are counted", "Quiet Quinn" in fc["skipped"] and "Late Lou" in fc["skipped"] and not any(r["name"] in ("Paused Pat", "Custom Cory") for r in fc["students"]), str(fc["skipped"]))
    jan = fc["per_month"]["2027-01"]
    check("the monthly total adds each student's expected cut", jan["likely"] > 0 and jan["low"] <= jan["likely"] and jan["n"] >= 3, str(jan))
    check("a forecast window must be sensible", raises(S.forecast, SLUG, 0, TODAY) is not None and raises(S.forecast, SLUG, 30, TODAY) is not None)

    # the report
    r = S.report(SLUG, "overview", 6, TODAY)
    check("overview: counts, progress table, flags with facts, a draft for the most urgent, the forecast and the plain disclaimer", all(x in r for x in ("## Progress", "## Flags", "## Draft for the most urgent", "Expected DFY income", "not a promise")) and "Quiet Quinn" in r, r[:400])
    check("flags are listed red before amber before info", r.index("[red]") < r.index("[amber]") < r.index("[info]"))
    check("the progress table shows qualified months and the cap", "10/12" in r and "$16,000/$18,000" in r, r)
    check("the report is saved", (d / "success-desk.md").exists())
    check("drafts view has one message per flag", S.report(SLUG, "drafts", 6, TODAY).count("\nTo ") >= 8)
    check("forecast view shows each month and the total", "Total: likely" in S.report(SLUG, "forecast", 3, TODAY) and "Jan 2027" in S.report(SLUG, "forecast", 3, TODAY))
    check("flags view has no progress table or forecast", "## Progress" not in S.report(SLUG, "flags", 6, TODAY) and "Expected DFY income" not in S.report(SLUG, "flags", 6, TODAY))
    check("bad view refused", raises(S.report, SLUG, "weird", 6, TODAY) is not None)
    check("no em dash in any view", all(chr(0x2014) not in S.report(SLUG, v, 6, TODAY) for v in ("overview", "flags", "drafts", "forecast")))

    # feeds
    att = S.attention(SLUG, TODAY)
    check("attention lists red and amber students, most urgent first, with the reason", att["needs"][0]["sev"] == "red" and any(x["student"] == "Quiet Quinn" for x in att["needs"]) and not any(x["student"] == "Almost Ann" for x in att["needs"]), str(att["needs"]))
    check("attention carries next month's expected income", att["next"]["month"] == "2027-01" and att["next"]["likely"] > 0 and att["next"]["students"] >= 3)
    g = RV.gather(SLUG, TODAY)
    mv = RV.moves(g)
    check("Weekly Review: a check-in move (rank 3.7) naming students, pointing to the drafts", any(m["rank"] == 3.7 and "Quiet Quinn" in m["do"] and "--view drafts" in m["how"] for m in mv), str([(m["rank"], m["do"][:60]) for m in mv]))
    check("Weekly Review headline carries the expected DFY income", "expected DFY income next month: likely" in RV.build(SLUG, today=TODAY))
    cash = CD.build(SLUG, "2026-12", today=TODAY)
    check("the Cash Desk shows the projected DFY income for next month, labelled a projection", "Expected from DFY students next month" in cash and "not a promise" in cash, cash)

    # empty engine
    (ROOT / "engines" / "zz-success2").mkdir(exist_ok=True)
    (ROOT / "engines" / "zz-success2" / "engine.json").write_text(json.dumps({"name": "s2", "path": "smb"}), encoding="utf-8")
    check("an engine with no students says how to get them", "cut sync zz-success2" in S.report("zz-success2", "overview", 6, TODAY))
    shutil.rmtree(ROOT / "engines" / "zz-success2", ignore_errors=True)
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
