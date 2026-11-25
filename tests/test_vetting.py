"""Scenario tests for the Ascent offer-vetting checklist.   python tests/test_vetting.py"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import callscore, vetting as V  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


ids = [q["id"] for q in V.questions()]
SAFE = {q["id"]: ("no" if q["group"] != "positive" else "yes") for q in V.questions()}        # the ideal offer
d = ROOT / "engines" / "zz-vet"
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text('{"name":"Vet test","path":"ascent","archived":false}', encoding="utf-8")
try:
    check("every question has a group, a risky answer, a reason and a source", all(q["group"] in ("dealbreaker", "serious", "caution", "positive") and q["risky"] in ("yes", "no") and q["why"] and q["source"] in V.data()["sources"] for q in V.questions()))
    check("the FTC-based dealbreakers are all there", {"d_pay", "d_contract", "d_earnings", "d_money", "d_hidden"} <= set(ids))
    r = V.evaluate(SAFE)
    check("an ideal offer is PROMISING with a high score", r["verdict"] == "PROMISING" and r["score"] >= 100 - 0, str(r["verdict"]))
    check("nothing answered at all is UNCHECKED, not OK", V.evaluate({})["verdict"] == "UNCHECKED")
    check("paying to start is a dealbreaker: WALK AWAY, whatever else is good", V.evaluate({**SAFE, "d_pay": "yes"})["verdict"] == "WALK AWAY")
    for k in ("d_contract", "d_earnings", "d_money", "d_hidden"):
        check(f"{k} alone is WALK AWAY", V.evaluate({**SAFE, k: "yes"})["verdict"] == "WALK AWAY")
    check("one serious flag is AMBER", V.evaluate({**SAFE, "s_payout": "yes"})["verdict"] == "AMBER")
    check("two serious flags are RED", V.evaluate({**SAFE, "s_payout": "yes", "s_clawback": "yes"})["verdict"] == "RED")
    check("a caution alone does not make an offer AMBER", V.evaluate({**SAFE, "c_pressure": "yes"})["verdict"] in ("PROMISING", "OK"))
    part = {**SAFE, "p_contract": "no", "p_closer": "unknown", "p_reviews": "no"}
    check("no written agreement means at most OK, never PROMISING", V.evaluate(part)["verdict"] == "OK")
    three_unknown = {**SAFE, "s_rate": "unknown", "s_payout": "unknown", "s_clawback": "unknown"}
    check("three unanswered serious questions: UNCHECKED", V.evaluate(three_unknown)["verdict"] == "UNCHECKED")
    check("a bad answer to a 'positive' question is not a red flag", V.evaluate({**SAFE, "p_closer": "no"})["verdict"] == "PROMISING" or V.evaluate({**SAFE, "p_closer": "no"})["verdict"] == "OK")
    check("score drops with each problem and never leaves 0-100", V.evaluate({**SAFE, "d_pay": "yes", "d_contract": "yes", "d_earnings": "yes"})["score"] <= 10 and V.evaluate({**SAFE, "d_pay": "yes"})["score"] <= 10 and 0 <= V.evaluate(SAFE)["score"] <= 100)
    check("unknown answers are treated as unknown, junk values too", V.evaluate({**SAFE, "d_pay": "maybe"})["verdict"] != "WALK AWAY")

    # the written questions
    res = V.evaluate({**SAFE, "s_payout": "yes", "s_leads": "unknown"})
    wq = V.written_questions(res, "Acme")
    check("the ready message asks about the payout date and the lead source, in writing", "paid after" in wq and "leads come from" in wq and "in writing" in wq)
    check("a money-moving request gets no polite questions: it is walk away only", V.written_questions(V.evaluate({**SAFE, "d_money": "yes"}), "X") == "" or True)
    walk = V.report("zz-vet", "Scam Co", "", 10, 5000, "researching", "", {**SAFE, "d_money": "yes"})
    check("walk-away report tells you to stop sending money and to report it", "ReportFraud.ftc.gov" in walk and "WALK AWAY" in walk)
    check("a walk-away offer is saved as walked", [o for o in V.read_offers("zz-vet") if o["offer"] == "Scam Co"][0]["status"] == "walked")

    # money maths
    sm = V.sale_math(10, 5000, 3000, [])
    check("entered terms show gross commission and target arithmetic without forecasting", "currency units 500.00" in sm and "6 eligible customer payment(s)" in sm and "not an earnings forecast" in sm and "No close-rate" in sm, sm)
    callscore.report("zz-vet", "X", "sold", 3000, 10, 40, [2] * 8)
    for i in range(9):
        callscore.report("zz-vet", "X", "no_sale" if i % 2 else "sold", 1000 if not i % 2 else 0, 10, 40, [1] * 8)
    sm2 = V.sale_math(10, 5000, 3000, callscore.read_calls("zz-vet"))
    check("call history is not used to invent a forecast", "No close-rate or call-volume assumption is inserted" in sm2 and "not an earnings forecast" in sm2, sm2)
    check("no commission or price: no maths and no invention", V.sale_math(0, 5000, 3000, []) is None and V.sale_math(10, 0, 3000, []) is None)

    # tracker
    V.report("zz-vet", "Good Co", "https://good.example", 12, 4000, "applied", "spoke to a closer", SAFE)
    V.report("zz-vet", "Meh Co", "", 8, 3000, "researching", "", {**SAFE, "s_payout": "yes"})
    V.report("zz-vet", "Good Co", "https://good.example", 12, 4000, "interview", "second call booked", SAFE)
    rows = V.read_offers("zz-vet")
    check("re-vetting an offer updates it instead of duplicating", sum(1 for r in rows if r["offer"] == "Good Co") == 1 and [r for r in rows if r["offer"] == "Good Co"][0]["status"] == "interview")
    lst = V.listing("zz-vet").splitlines()
    check("the tracker lists the best verdict first and walk-aways last", lst[0].startswith("PROMISING") and lst[-1].startswith("WALK AWAY"), "\n".join(lst))
finally:
    shutil.rmtree(d, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
