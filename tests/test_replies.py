"""Tests for the Reply Desk.   python tests/test_replies.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import desklog as dl, replies as R  # noqa: E402

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


TODAY = dt.date(2026, 11, 14)
CASES = {
    "interested": ["Yes, I'd be happy to chat. Send me some times.", "Sounds good, let's talk next week.", "Interested! Can you call me tomorrow?", "Sure, what's your calendar link?",
                   "We're free Thursday afternoon, would love to hear more.", "Sounds great. What does it cost?", "Yes please, book a call"],
    "question": ["How does this work exactly?", "Can you send more information?", "Do you work with dental practices in Florida?", "What is included in the service?", "Do you have any case studies?",
                 "Who are you and how did you get my email?"],
    "price": ["It's too expensive for us.", "We have no budget for this right now.", "How much do you charge?", "Can you send your pricing?", "That is out of our budget.", "What are your rates?"],
    "already_have": ["Thanks, but we already work with an agency.", "We have an in-house team that handles this.", "We're under contract with another provider.", "Already using someone, happy with our current setup.",
                     "We already have a vendor for that."],
    "not_now": ["Not right now, maybe next quarter.", "Too busy this month, check back in a couple of months.", "Bad timing, reach out again in March.", "Can you circle back after the holidays?",
                "Maybe later in the year.", "Not the right time. Contact me again next year."],
    "not_interested": ["Not interested, thanks.", "No thank you.", "We're all set, thanks.", "This isn't for us. Please don't follow up.", "No need, we're good.", "Please pass on this."],
    "wrong_person": ["I'm not the right person for this.", "Wrong contact, I don't handle marketing.", "She no longer works here.", "You have the wrong email, this is not my department.",
                     "He left the company last year."],
    "referral": ["You should talk to Maria Lopez, she runs marketing.", "Please reach out to John in our finance team.", "I've forwarded your email to our manager."],
    "unsubscribe": ["Unsubscribe me please.", "Please remove me from your list.", "Stop emailing me.", "Do not contact me again.", "I'm reporting this as spam.", "Take me off your list, this is GDPR harassment.", "STOP"],
    "out_of_office": ["I am out of the office until November 20 with limited access to email.", "Automatic reply: I am on annual leave and will be back on 3 December.",
                      "Thank you for your message. I am currently away and will respond when I return.", "Auto-reply: out of office."],
    "unclear": ["ok", "Received.", "Hmm", "Thanks!"],
}
miss = []
for want, texts in CASES.items():
    for t in texts:
        got = R.classify(t)["category"]
        if got != want:
            miss.append(f"{want} <- {got}: {t}")
        check(f"{want}: {t[:62]}", got == want, f"got {got}")

# dates
check("out of office with a date: the day after they are back", R.follow_up_date("out_of_office", "I am back on November 20", TODAY) == dt.date(2026, 11, 21))
check("out of office, day first", R.follow_up_date("out_of_office", "I will be back on 3 December", TODAY) == dt.date(2026, 12, 4))
check("out of office date already past this year rolls to next year", R.follow_up_date("out_of_office", "back on January 5", TODAY) == dt.date(2027, 1, 6))
check("out of office with no date: none", R.follow_up_date("out_of_office", "I am out of office", TODAY) is None)
check("not now: in 3 months = 90 days", R.follow_up_date("not_now", "check back in 3 months", TODAY) == TODAY + dt.timedelta(days=90))
check("not now: in a couple of weeks", R.follow_up_date("not_now", "in a couple of weeks", TODAY) == TODAY + dt.timedelta(days=14))
check("not now: next quarter = 1st week of January", R.follow_up_date("not_now", "next quarter", TODAY) == dt.date(2027, 1, 8))
check("not now: next month", R.follow_up_date("not_now", "next month", TODAY) == dt.date(2026, 12, 1))
check("not now: in March goes to the next March, a week in", R.follow_up_date("not_now", "reach out again in March", TODAY) == dt.date(2027, 3, 8))
check("not now: after the holidays", R.follow_up_date("not_now", "after the holidays", TODAY) == dt.date(2027, 1, 8))
check("not now with no clue defaults to 60 days", R.follow_up_date("not_now", "not now", TODAY) == TODAY + dt.timedelta(days=60))
check("other kinds have no date", R.follow_up_date("interested", "yes in 3 months", TODAY) is None)

# drafts
for cat in R.CATEGORIES:
    check(f"every category has advice: {cat}", cat in R.ADVICE and cat in R.LABEL)
    t = R.draft(cat, "Dana", "Bolu", "", dt.date(2027, 1, 8))
    check(f"draft for {cat}: no em dash, signed, no raw braces", chr(0x2014) not in t and "{" not in t and (not t or "Bolu" in t))
check("calendar link used when the engine has one", "https://cal.example/bolu" in R.draft("interested", "Dana", "Bolu", "https://cal.example/bolu", None))
check("no calendar: proposes a time instead", "15-minute call" in R.draft("interested", "Dana", "Bolu", "", None))
check("not-now draft names the date", "January 8" in R.draft("not_now", "Dana", "Bolu", "", dt.date(2027, 1, 8)))
check("unknown first name is 'there'", R.draft("interested", "", "Bolu", "", None).startswith("Hi there"))
check("out of office gets no draft", R.draft("out_of_office", "x", "y", "", None) == "" and R.draft("unclear", "x", "y", "", None) == "")

# a real engine
SLUG = "zz-reply"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Reply test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "calendar_url": "https://cal.example/bolu", "archived": False}), encoding="utf-8")
L = "2026-11-09"
with (d / "send-lists" / f"{L}.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "website", "email", "instagram", "facebook", "contact_first"])
    w.writeheader()
    w.writerow({"row": 1, "business": "Alpha Dental", "city": "Tampa", "channel": "Email", "where": "a@alpha.example", "gap_used": "g", "variant": "v", "opener": "Hi", "website": "https://www.alpha.example/",
                "email": "dana@alpha.example", "instagram": "", "facebook": "", "contact_first": "Dana"})
    w.writerow({"row": 2, "business": "Beta Dental", "city": "Tampa", "channel": "Email", "where": "b@beta.example", "gap_used": "g", "variant": "v", "opener": "Hi", "website": "beta.example",
                "email": "", "instagram": "", "facebook": "", "contact_first": ""})
dl.append_events(SLUG, [{"logged_at": "2026-11-09T10:00:00", "source": L, "row_id": "1", "status": "sent", "list_date": L}, {"logged_at": "2026-11-09T10:01:00", "source": L, "row_id": "2", "status": "sent", "list_date": L}])
try:
    t = R.report(SLUG, "Sounds good, what does it cost?", source=L, row="1", today=TODAY)
    check("report: kind, signals, advice, draft with the row's first name, the sender and the calendar", "Kind: interested" in t and "Hi Dana" in t and "Bolu Ade" in t and "https://cal.example/bolu" in t, t)
    check("without --log nothing is written", not dl.read_log(SLUG)[2:] and not R.read_dnc(SLUG))
    t = R.report(SLUG, "Not right now, maybe in March", source=L, row="1", log=True, today=TODAY)
    ev = dl.read_log(SLUG)[-1]
    check("logged as a reply with the Send Desk's category and a next step", ev["status"] == "replied" and ev["category"] == "not now" and "2027-03-08" in ev["next_step"] and "Logged" in t, str(ev))
    check("the thread now counts as replied (follow-ups stop)", dl.status_of_row(dl.history(SLUG), dl.load_lists(SLUG)[0]) == "replied")
    check("not-now does not go on the do-not-contact list", R.read_dnc(SLUG) == [])
    t = R.report(SLUG, "Please unsubscribe me, stop emailing", source=L, row="1", log=True, today=TODAY)
    dnc = R.read_dnc(SLUG)
    check("unsubscribe: email AND website domain added to the do-not-contact list", {r["value"] for r in dnc} == {"dana@alpha.example", "alpha.example"}, str(dnc))
    check("on_dnc finds the email, a subdomain and nothing else", R.on_dnc(SLUG, "dana@alpha.example") and R.on_dnc(SLUG, "", "https://shop.alpha.example/x") and not R.on_dnc(SLUG, "x@beta.example", "beta.example"))
    check("the same unsubscribe twice adds nothing new", "nothing new" in R.report(SLUG, "unsubscribe", source=L, row="1", log=True, today=TODAY) and len(R.read_dnc(SLUG)) == 2)
    t = R.report(SLUG, "No thanks, not interested", source=L, row="2", log=True, email="owner@beta.example", today=TODAY)
    check("'no thanks' adds the email only, not the whole domain", any(r["value"] == "owner@beta.example" for r in R.read_dnc(SLUG)) and not any(r["value"] == "beta.example" for r in R.read_dnc(SLUG)))
    t = R.report(SLUG, "I am out of office until 20 December", today=TODAY)
    check("out of office: no draft, follow-up date shown", "No answer needed" in t and "2026-12-21" in t and "Draft answer" not in t, t)
    check("unclear is said plainly", "unclear" in R.report(SLUG, "ok", today=TODAY) and "read it yourself" in R.report(SLUG, "ok", today=TODAY).lower())
    check("a row that does not exist is explained", "could not find row 99" in (raises(R.report, SLUG, "yes", source=L, row="99") or ""))
    check("--log without a row or email is explained", "--source" in (raises(R.report, SLUG, "yes sure", log=True) or ""))
    check("empty and huge replies refused", raises(R.report, SLUG, " ") and raises(R.report, SLUG, "x" * 5000))
    check("dnc report lists entries and says no tool removes them", "No tool removes" in R.dnc_report(SLUG))
    check("add_dnc rejects junk", not R.add_dnc(SLUG, "not an address") and not R.add_dnc(SLUG, ""))
    check("no em dash in any report", all(chr(0x2014) not in R.report(SLUG, x, today=TODAY) for x in ("yes", "ok", "unsubscribe", "too expensive")))
finally:
    shutil.rmtree(d, ignore_errors=True)

if miss:
    print("\nMisclassified:\n  " + "\n  ".join(miss))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
