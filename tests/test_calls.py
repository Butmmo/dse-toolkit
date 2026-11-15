"""Tests for the Call Desk: the prep sheet, the notes sheet, and what to do the minute a call ends.   python tests/test_calls.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import callscore, calls as C, desklog as dl, replies, review as RV  # noqa: E402

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


SLUG = "zz-calls"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Calls test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "calendar_url": "https://cal.example/bolu", "archived": False}), encoding="utf-8")
LST = "2026-11-09"
COLS = ["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "website", "email", "category", "contact_name", "contact_title"]
with (d / "send-lists" / f"{LST}.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerow({"row": 1, "business": "Acme Dental", "city": "Tampa", "channel": "Email", "where": "info@acme.example", "gap_used": "there is no way to book online after hours", "variant": "v", "website": "https://www.acme.example/",
                "opener": "Hi, I noticed there is no way to book online after hours at Acme Dental. I fix that for dental practices. Bolu", "email": "info@acme.example", "category": "dentist", "contact_name": "", "contact_title": ""})
    w.writerow({"row": 2, "business": "Beta Co", "city": "Austin", "channel": "Instagram DM", "where": "@betaco", "gap_used": "", "variant": "v", "website": "", "opener": "", "email": "", "category": "", "contact_name": "", "contact_title": ""})
dl.append_events(SLUG, [
    {"logged_at": "2026-11-09T10:00:00", "list_date": LST, "source": LST, "row_id": "1", "status": "sent", "name": "Acme Dental"},
    {"logged_at": "2026-11-10T09:00:00", "list_date": LST, "source": LST, "row_id": "1", "status": "replied", "name": "Acme Dental", "reply": "Yes, call me tomorrow. We lose a lot of patients who phone after hours."},
    {"logged_at": "2026-11-10T09:30:00", "list_date": LST, "source": LST, "row_id": "1", "status": "booked", "name": "Acme Dental"},
    {"logged_at": "2026-11-09T10:05:00", "list_date": LST, "source": LST, "row_id": "2", "status": "sent", "name": "Beta Co"},
    {"logged_at": "2026-11-11T08:00:00", "list_date": LST, "source": LST, "row_id": "2", "status": "booked", "name": "Beta Co"},
])
enriched = ROOT / "my-lists" / "zz-calls-enriched-test.csv"
enriched.parent.mkdir(exist_ok=True)
with enriched.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["Company", "website", "decision_maker", "decision_maker_title", "decision_maker_source", "best_email", "phone_found", "booking_tool", "tech_stack", "site_description", "lead_why"])
    w.writeheader()
    w.writerow({"Company": "Acme Dental", "website": "acme.example", "decision_maker": "Maria Lopez", "decision_maker_title": "Owner", "decision_maker_source": "https://acme.example/about",
                "best_email": "maria@acme.example", "phone_found": "(813) 555-0142", "booking_tool": "calendly.com", "tech_stack": "WordPress, Calendly", "site_description": "Family dental care in Tampa since 1998.", "lead_why": "owner named"})
TODAY = dt.date(2026, 11, 12)
try:
    # ---- prep
    t = C.prep(SLUG, LST, "1", TODAY)
    folder = d / "calls" / "2026-11-12-acme-dental"
    check("prep.md and notes.md are written in the engine's calls folder", (folder / "prep.md").exists() and (folder / "notes.md").exists())
    check("it says what they wrote, in their exact words, with the date", 'They replied (2026-11-10): "Yes, call me tomorrow. We lose a lot of patients who phone after hours."' in t and "call booked 2026-11-10" in t, t[:600])
    check("it shows the message you sent", 'You sent (Email): "Hi, I noticed there is no way to book online after hours' in t)
    facts_part = t.split("## Open with three facts")[1].split("##")[0]
    check("three facts to open with, each naming where it came from", facts_part.count("\n- ") == 3 and "(their reply, logged 2026-11-10)" in facts_part and "(your send list (2026-11-09, row 1))" in facts_part and "https://acme.example/about" in facts_part, facts_part)
    check("the owner is named from the enrichment, with the page it came from", "Maria Lopez is named as Owner on their site (https://acme.example/about)" in t or "Maria Lopez is named as Owner" in t)
    check("who you are talking to uses the named decision maker; phone and email come from the enrichment", "Talking to: Maria Lopez" in t and "(813) 555-0142" in t)
    check("more facts are listed as 'also known' (site description, booking tool)", "Family dental care in Tampa since 1998" in t and "calendly" in t)
    check("the question plan follows the scorecard's five headings and weaves in YOUR gap, in your words", all(h in t for h in ("1. Situation", "2. Problem", "3. Cost", "4. Result wanted", "5. Next step")) and "I noticed there is no way to book online after hours. What happens today when that comes up?" in t, t)
    check("the up-front contract script and the 'in hand before you speak' checklist are there, with the calendar link", "up-front contract" in t.lower() and "What would you like help with today?" in t and "The price, what is included and what is NOT included" in t and "https://cal.example/bolu" in t)
    check("it points to the exact command for after the call", f"python dse.py call after {SLUG} --source {LST} --row 1" in t)
    nt = (folder / "notes.md").read_text(encoding="utf-8")
    check("the notes sheet has the five scorecard headings and lists the scorecard areas to rate", all(h in nt for h in ("## Situation", "## Problem", "## Cost", "## Result they want", "## Next step")) and all(a[1] in nt for a in callscore.AREAS))
    check("no unknowns are reported for a well-known lead", "## Not known" not in t, t[-400:])

    # a lead we know almost nothing about: nothing is invented
    t2 = C.prep(SLUG, LST, "2", TODAY)
    check("a thin lead says what is NOT known, instead of inventing facts", "## Not known (do not pretend otherwise)" in t2 and "No website facts yet" in t2 and "No written reply is logged" in t2 and "Your first message is not on the row" in t2, t2)
    check("and says how many facts to find before the call", "Find" in t2 and "more before the call" in t2)
    check("a missing contact says to ask who decides", "not known yet: ask who decides" in t2)
    check("the generic question plan has no invented gap", "I noticed" not in t2 and "What is not working about that?" in t2)
    check("no gap, no enrichment: still no invented decision maker", "is named" not in t2)

    # ---- errors
    check("an unknown row is explained with the lists that exist", LST in (raises(C.prep, SLUG, LST, "99", TODAY) or "") and "could not find row 99" in (raises(C.prep, SLUG, LST, "99", TODAY) or ""))
    check("an unknown outcome or negative numbers are refused", raises(C.after, SLUG, LST, "1", "maybe") is not None and raises(C.after, SLUG, LST, "1", "follow_up", price=-5) is not None)

    # ---- the review sees a booked call with no prep
    shutil.rmtree(d / "calls" / "2026-11-12-beta-co")          # Beta Co's sheet above was only to read it: start this check with it unprepared
    at = C.attention(SLUG, TODAY)
    check("a call booked in the last week with no prep sheet is flagged (Beta Co); Acme has one", [x["name"] for x in at] == ["Beta Co"], str(at))
    mv = RV.moves(RV.gather(SLUG, TODAY))
    check("the Weekly Review's booked-call move names the unprepared lead and gives the prep command", any(m["rank"] == 2 and "No prep sheet yet for Beta Co" in m["how"] and f"call prep {SLUG} --source {LST} --row 2" in m["how"] for m in mv), str([m["how"][:140] for m in mv if m["rank"] == 2]))
    C.prep(SLUG, LST, "2", TODAY)
    check("once prepared, the flag disappears", C.attention(SLUG, TODAY) == [])
    check("a call booked more than a week ago is not nagged about", C.attention(SLUG, dt.date(2026, 12, 20)) == [])

    # ---- after the call
    a1 = C.after(SLUG, LST, "1", "follow_up", "patients phone after hours and we miss them", 4000, 1500, "I send the proposal Thursday and we talk Friday", False, TODAY)
    check("a follow-up call: the recap uses their problem and their number, and the agreed next step, signed", "patients phone after hours and we miss them" in a1 and "$4,000 a month" in a1 and "I send the proposal Thursday and we talk Friday" in a1 and "Bolu Ade" in a1 and "Hi Maria" in a1, a1)
    check("the proposal command comes pre-filled with their words, the cost and the price, and [brackets] for what only you know", f'python dse.py proposal {SLUG} --client "Acme Dental" --contact Maria --problem "patients phone after hours and we miss them"' in a1 and "--price 1500" in a1 and "--cost-month 4000" in a1 and "--offer \"[what you will do]\"" in a1, a1)
    check("the scorecard command is given", f'python dse.py callscore {SLUG} --offer "Acme Dental" --outcome follow_up' in a1)
    check("nothing is missing, so there is no 'not filled in' list", "Not filled in yet" not in a1)
    a2 = C.after(SLUG, LST, "1", "follow_up", "", 0, 0, "", False, TODAY)
    check("a thin follow-up is flagged: what is missing, and the message keeps [brackets] rather than inventing", "Not filled in yet" in a2 and "the problem in their words" in a2 and "the price" in a2 and "[the problem, in their words]" in a2, a2)
    check("a follow-up call is not written into the log as won or lost", not any(e["status"] in ("won", "lost") for e in dl.read_log(SLUG)))
    a3 = C.after(SLUG, LST, "1", "sold", "patients phone after hours", 4000, 1500, "start Monday", False, TODAY)
    ev = [e for e in dl.read_log(SLUG) if e["status"] == "won"]
    check("a sold call is recorded in the send log as won, with the value, so results stay true", len(ev) == 1 and ev[0]["value"] == "1500" and ev[0]["category"] == "call" and "Recorded in your send log as won" in a3, str(ev))
    check("a sold call points to the callscore and client commands", "--outcome sold --cash 1500" in a3 and f"python dse.py client won {SLUG}" in a3)
    a4 = C.after(SLUG, LST, "2", "no_sale", "they are happy with their current agency", 0, 0, "check back in spring", True, TODAY)
    lost = [e for e in dl.read_log(SLUG) if e["status"] == "lost"]
    check("a no-sale call is recorded as lost, and the message is gracious without pushing", len(lost) == 1 and "not the right fit right now" in a4 and "If anything changes" in a4, a4)
    check("--stop with nothing known to block says so plainly", "nothing new to add" in a4)
    a5 = C.after(SLUG, LST, "1", "no_show", "", 0, 0, "", True, TODAY)
    dnc = replies.read_dnc(SLUG)
    check("--stop adds their email and website to the do-not-contact list", {r["value"] for r in dnc} == {"maria@acme.example", "acme.example"} and "Do-not-contact list" in a5, str(dnc))
    check("a no-show message offers another time with your calendar and does not blame", "missed you" in a5 and "https://cal.example/bolu" in a5 and "No problem at all" in a5 and "failed" not in a5.lower())
    check("after.md is saved in the call folder", (d / "calls" / "2026-11-12-acme-dental" / "after.md").exists())
    check("no em dash in the prep, notes or after sheets", all(chr(0x2014) not in x for x in (t, t2, nt, a1, a2, a3, a4, a5)))
finally:
    shutil.rmtree(d, ignore_errors=True)
    enriched.unlink(missing_ok=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
