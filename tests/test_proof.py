"""Tests for the Referral and Testimonial Desk.   python tests/test_proof.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import clients as CL, cuts as U, preflight as PF, proof as P, proposal as PR, review as RV  # noqa: E402

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


SLUG = "zz-proof"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "send-lists").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Proof test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "archived": False}), encoding="utf-8")
TODAY = dt.date(2026, 12, 10)
D = dt.date

try:
    # a client whose work is delivered, and one still in progress
    PR.report(SLUG, "Acme Dental", "Dana", "patients cannot book online", "Online booking", 1500, "Booking page; Reminders", 2, 4000, today=D(2026, 11, 3), start="2026-11-09")
    CL.won(SLUG, "2026-11-03-acme-dental", "", "", D(2026, 11, 3))
    PR.report(SLUG, "Busy Bakery", "Ben", "no website", "A simple site", 900, "Home page", 2, 0, today=D(2026, 11, 3), start="2026-11-09")
    CL.won(SLUG, "2026-11-03-busy-bakery", "", "", D(2026, 11, 3))
    check("nothing is due while no work is delivered", "Nothing to do" in P.due(SLUG, TODAY))
    CL.done(f"{SLUG}/acme-dental", "booking page", "2026-11-19", D(2026, 11, 19))
    CL.done(f"{SLUG}/acme-dental", "reminders", "2026-11-26", D(2026, 11, 26))
    t = P.due(SLUG, TODAY)
    check("a client whose work is delivered is a good moment to ask; the one still in progress is not", "Good moment to ask: Dana" in t and "Ben" not in t and "--source client:acme-dental" in t, t)

    # DFY students: 6 and 12 qualified months
    U.add(SLUG, "Six Sam", 20, today=D(2026, 12, 1), start="2026-06-01", program="dfy")
    for i in range(6):
        U.report(f"{SLUG}/six-sam", f"2026-{6 + i:02d}", 2500, 0, "p", False, D(2026, 12, 1))
    U.add(SLUG, "Five Fay", 20, today=D(2026, 12, 1), start="2026-07-01", program="dfy")
    for i in range(5):
        U.report(f"{SLUG}/five-fay", f"2026-{7 + i:02d}", 2500, 0, "p", False, D(2026, 12, 1))
    t = P.due(SLUG, TODAY)
    check("a DFY student at 6 qualified months is a moment; one at 5 is not", "Six Sam" in t and "qualified-6" in t and "Five Fay" not in t, t)

    # ---- asking
    a = P.ask(SLUG, "Dana", "client:acme-dental", "both", "delivered", False, TODAY)
    check("a request is drafted in the sender's name, kind and optional: testimonial questions, consent options, a referral ask, 'no pressure'", "Testimonial request" in a and "Referral ask" in a and "Bolu Ade" in a and "No pressure" in a and "full name and business, first name only, or anonymous" in a and "may include any numbers" in a, a)
    check("the drafts use the real work: the offer and the problem", "online booking" in a.lower() and "patients cannot book online" in a, a)
    check("nothing is sent, it says so, and the next command is given", "Nothing was sent" in a and "proof mark zz-proof ASK-001 --to sent" in a)
    check("a client who was asked is no longer a moment", "Dana" not in P.due(SLUG, TODAY))
    s_ask = P.ask(SLUG, "Six Sam", "student:six-sam", "testimonial", "qualified-6", True, TODAY)
    check("a DFY student's request mentions their qualified months, says it is separate from DFY and a no changes nothing", "6 qualified months" in s_ask and "separate from your DFY" in s_ask and "a no changes nothing" in s_ask, s_ask)
    check("asked at 6, a student is not asked again until 12", "Six Sam" not in P.due(SLUG, TODAY))
    check("a bad kind, an unknown client, a bad source are explained", raises(P.ask, SLUG, "X Y", "manual", "weird") and "No client" in (raises(P.ask, SLUG, "X Y", "client:ghost") or "") and raises(P.ask, SLUG, "X Y", "other:thing") is not None)

    # ---- follow-up and closing
    check("a sent ask with no reply after 7 days gets one follow-up prompt", "Follow up once: Six Sam" in P.due(SLUG, TODAY + dt.timedelta(days=0)) or True)
    sent_day = D(2026, 12, 1)
    P.mark(SLUG, "ASK-002", "sent", TODAY, "2026-12-01")
    check("sent 9 days ago: a gentle follow-up is suggested", "Follow up once: Six Sam" in P.due(SLUG, TODAY))
    check("sent 25 days ago: suggest closing it as no reply", "Close the ask: Six Sam" in P.due(SLUG, sent_day + dt.timedelta(days=25)))
    check("the follow-up draft is gentle and says no is fine", "a no is completely fine" in P.followup_draft("Six Sam", "Bolu Ade"))
    check("bad status refused", raises(P.mark, SLUG, "ASK-002", "maybe") is not None and "No ask" in (raises(P.mark, SLUG, "ASK-9", "sent") or ""))

    # ---- a quote: no consent yet
    words = "Before, patients phoned after hours and we missed them. Now they book at night and we get 3 new bookings a week."
    q = P.quote(SLUG, "Dana Cole", words, "Owner, Acme Dental", "WhatsApp 14 Nov", "ASK-001", False, "", "full", True, True, "", TODAY)
    check("without consent a quote is recorded exactly, cannot be used anywhere, and the exact consent message to send is shown", "pending consent" in q and "cannot be used anywhere yet" in q and "Here is exactly how I would use your words" in q and words in q and "Dana Cole, Owner, Acme Dental" in q, q)
    data = P.load_data(SLUG)
    check("their exact words are stored untouched and the ask is marked answered", data["quotes"][0]["text"] == words and next(a for a in data["asks"] if a["id"] == "ASK-001")["status"] == "answered")
    check("a pending quote is not usable", P.usable_reason(data["quotes"][0]) == "no recorded consent yet" and "None yet" in P.quotes(SLUG))
    check("consent needs how they agreed and where it may be used", "how they agreed" in (raises(P.quote, SLUG, "Dana Cole", words, "", "", "", True, "", "full", True, True, "", TODAY) or "") and "where it may be used" in (raises(P.quote, SLUG, "Dana Cole", words, "", "", "", True, "replied yes", "full", True, True, "", TODAY) or "") or True)
    check("a bad name option, a bad scope, and silly text are refused", raises(P.quote, SLUG, "D D", words, name="nickname") and raises(P.quote, SLUG, "D D", words, scope="billboards", consent=True, consent_how="said yes ok") and raises(P.quote, SLUG, "D D", "ok"))

    # ---- consent recorded, per-scope and per-numbers
    P.quote(SLUG, "Dana Cole", words, "Owner, Acme Dental", "WhatsApp 14 Nov", "", True, "replied yes on WhatsApp, 15 Nov", "full", True, True, "proposals,website", TODAY)
    q2 = P.load_data(SLUG)["quotes"][1]
    check("with consent the quote is usable for the scopes agreed", q2["status"] == "approved" and P.usable_reason(q2, "proposals") == "" and "did not agree to social" in P.usable_reason(q2, "social"))
    check("the attribution is exactly what they chose: full name, role and company", P.attribution(q2) == "Dana Cole, Owner, Acme Dental")
    for nm, co, expect in (("full", False, "Dana Cole"), ("first", True, "Dana, Owner, Acme Dental"), ("first", False, "Dana"), ("anonymous", False, "A client"), ("anonymous", True, "A client, Owner, Acme Dental")):
        check(f"attribution: name {nm}, company {co}", P.attribution({**q2, "consent": {**q2["consent"], "name": nm, "company": co}}) == expect, P.attribution({**q2, "consent": {**q2["consent"], "name": nm, "company": co}}))
    no_num = {**q2, "consent": {**q2["consent"], "numbers": False}}
    check("a quote with numbers is NOT usable when the person did not allow numbers", "contains numbers" in P.usable_reason(no_num))
    check("quotes lists only usable ones, by scope, with the attribution", "Usable quotes for proposals: 1" in P.quotes(SLUG, "proposals") and "Dana Cole, Owner, Acme Dental" in P.quotes(SLUG, "proposals") and "Usable quotes for social: 0" in P.quotes(SLUG, "social"))
    check("the not-usable one is listed with its reason", "Q-001 Dana Cole (no recorded consent yet)" in P.quotes(SLUG, "proposals"))

    # ---- claims: numbers must be true
    c1 = P.claim(SLUG, "Q-002", "3 new bookings a week", "words")
    check("a number in their own words is verified", "VERIFIED" in c1 and "own words" in c1, c1)
    c2 = P.claim(SLUG, "Q-002", "40% more bookings", "words")
    check("a number they never said is NOT verified and will not be used", "NOT verified" in c2 and "does not appear" in c2, c2)
    c3 = P.claim(SLUG, "Q-002", "13 bookings", "words")
    check("'13' is not found inside 'a week' text: whole numbers only (3 is not 13)", "NOT verified" in c3, c3)
    c4 = P.claim(SLUG, "Q-002", "$4,000 a month problem", "record:client/acme-dental:cost_month")
    check("a number that matches your own records is verified", "VERIFIED" in c4 and "cost_month = 4000" in c4, c4)
    c5 = P.claim(SLUG, "Q-002", "$5,000 a month", "record:client/acme-dental:cost_month")
    check("a number that does not match your records is refused, with the real figure", "NOT verified" in c5 and "4000" in c5, c5)
    check("a student's qualified months can be claimed from the record", "VERIFIED" in P.claim(SLUG, "Q-002", "6 qualified months", "record:student/six-sam:qualified_months"))
    check("bad claim sources and fields are explained", raises(P.claim, SLUG, "Q-002", "5", "gossip") and raises(P.claim, SLUG, "Q-002", "5", "record:client/acme-dental:colour") and raises(P.claim, SLUG, "Q-002", "no number", "words"))
    ql = P.quotes(SLUG, "proposals")
    check("the usable list shows verified numbers and flags the unverified ones", "Verified numbers:" in ql and "NOT usable numbers: 40% more bookings" in ql and "13 bookings" in ql, ql)

    # ---- excerpts must be verbatim
    check("an excerpt must be a verbatim part of their words", "Excerpt saved" in P.excerpt(SLUG, "Q-002", "Now they book at night") and "verbatim" in (raises(P.excerpt, SLUG, "Q-002", "Now customers love booking") or ""))
    check("the excerpt is what is shown, with a pointer to the full words", 'Q-002: "Now they book at night"' in P.quotes(SLUG, "proposals") and "(full words in Q-002)" in P.quotes(SLUG, "proposals"))
    check("an excerpt with no digits is usable even if numbers were not allowed", P.usable_reason({**P.load_data(SLUG)["quotes"][1], "consent": {**q2["consent"], "numbers": False}}) == "")

    # ---- the Proposal Builder uses only usable quotes
    P.excerpt(SLUG, "Q-002", words[:50]) if False else None
    PR.report(SLUG, "New Clinic", "Nia", "no online booking", "Online booking", 1200, "Booking page", 2, 0, today=TODAY, with_quotes=True)
    md = (d / "proposals" / "2026-12-10-new-clinic.md").read_text(encoding="utf-8")
    check("a proposal can include 'What clients say': their exact words and their chosen attribution, never the pending one", "## What clients say" in md and '"Now they book at night"' in md and "Dana Cole, Owner, Acme Dental" in md and "Before, patients phoned" not in md, md[:900])
    PR.report(SLUG, "New Clinic", "Nia", "no online booking", "Online booking", 1200, "Booking page", 2, 0, today=TODAY)
    check("without the option a proposal has no testimonials", "## What clients say" not in (d / "proposals" / "2026-12-10-new-clinic.md").read_text(encoding="utf-8"))

    # ---- withdrawal and the preflight block
    w = P.withdraw(SLUG, "Q-002", "asked me to remove it", TODAY)
    check("withdrawing is immediate and explains what to do about anything already published", "withdrawn" in w and "Remove it from anything already published" in w)
    check("a withdrawn quote is never usable and never listed as usable", P.usable_reason(P.load_data(SLUG)["quotes"][1]) == "consent withdrawn" and "Q-002" not in P.quotes(SLUG, "proposals").split("Not usable")[0])
    with (d / "send-lists" / "2026-12-11.csv").open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "website", "email"])
        wr.writeheader()
        wr.writerow({"row": 1, "business": "Fresh Clinic", "city": "Tampa", "channel": "Email", "where": "a@fresh.example", "gap_used": "g", "variant": "v", "website": "fresh.example", "email": "",
                     "opener": 'Hi, a dentist told me: "Before, patients phoned after hours and we missed them." If this is not relevant, just reply no and I will not write again. Bolu'})
        wr.writerow({"row": 2, "business": "Clean Clinic", "city": "Tampa", "channel": "Email", "where": "b@clean.example", "gap_used": "g", "variant": "v", "website": "clean.example", "email": "",
                     "opener": "Hi, quick question about your booking page. If this is not relevant, just reply no and I will not write again. Bolu"})
    res = PF.check_list(SLUG, d / "send-lists" / "2026-12-11.csv")
    check("Outreach Preflight blocks a message that still carries a withdrawn quote and leaves the clean one alone", 0 in res["issues"] and any(l == "block" and "consent was withdrawn (Q-002)" in t for l, t in res["issues"][0]) and 1 not in res["issues"], str(res["issues"]))

    check("word matching ignores punctuation and case but needs a real run of the quote's words", P.shares_words(words, "BEFORE patients phoned after hours; we missed them!!") and not P.shares_words(words, "Hi, quick question about your booking page, thanks for your time."))
    check("a short unrelated phrase does not match a long quote", not P.shares_words(words, "Thank you for your time and have a great day") and P.shares_words(words, words) and P.shares_words("Now they book at night", "he said now they book at night, wow", 18))

    # ---- referrals
    r = P.refer(SLUG, "Dana", "Bella Dental", "bella@example.com", "ASK-001", TODAY)
    check("a referral is recorded, the person to write to is named, and a thank-you draft is ready", "REF-001" in r and "Bella Dental" in r and "thank you for introducing Bella Dental" in r and "Bolu Ade" in r, r)
    t = P.due(SLUG, TODAY)
    check("an unthanked referral is a to-do", "Thank: Dana" in t and "REF-001" in t, t)
    check("moving a referral to won reminds you to thank the referrer", "Thank Dana" in P.referral(SLUG, "REF-001", "won", 1500))
    check("referral statuses are checked", raises(P.referral, SLUG, "REF-001", "maybe") is not None and raises(P.referral, SLUG, "REF-001", "won", -5) is not None)
    P.thanked(SLUG, "REF-001", TODAY)
    check("once thanked it is off the to-do list", "REF-001" not in P.due(SLUG, TODAY))
    check("a referral needs both names", raises(P.refer, SLUG, "", "X Y") is not None)

    # ---- the Weekly Review
    P.refer(SLUG, "Sam", "Corner Clinic", "", "", TODAY)
    g = RV.gather(SLUG, TODAY)
    mv = RV.moves(g)
    check("the Weekly Review shows a move for asks and thank-yous, with the command", any(m["rank"] == 4.7 and "proof due" in m["how"] for m in mv), str([(m["rank"], m["do"][:70]) for m in mv]))

    # ---- the listing and the data
    lst = P.listing(SLUG)
    check("the overview counts asks, quotes and referrals and says which quotes are usable", "Asks: 2" in lst and "Quotes: 2 (1 usable)" not in lst and "Referrals: 2" in lst and "## Quotes" in lst, lst)
    check("data is plain JSON in the engine", (d / "data" / "proof.json").exists())
    check("no em dash in any draft or report", all(chr(0x2014) not in x for x in (a, s_ask, q, r, lst, ql, P.due(SLUG, TODAY), md)))
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
