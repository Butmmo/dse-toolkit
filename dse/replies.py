"""The Reply Desk: paste a reply you received, see what kind it is, get an honest draft answer, and log it so the thread stops being chased.

    python dse.py reply <engine> --text "Thanks but we already have an agency" [--name Dana] [--source 2026-11-09 --row 7] [--log] [--email dana@acme.com]
    python dse.py dnc <engine>                                    the do-not-contact list for this engine

What it does, in plain rules (no AI model, nothing invented, nothing sent):
  1. Classifies the reply: interested, question, price objection, already have someone, not now, not interested, wrong person, referral, unsubscribe,
     out of office, or unclear (then it says so and you read it yourself). The words that decided it are shown.
  2. Drafts a short, polite answer in your sender name, with [brackets] where only you know the facts. You send it yourself; this tool never sends.
  3. Reads dates: when a not-now reply says "next quarter" or "in March", or an out-of-office says when they are back, it works out the day to follow up.
  4. With --log (and --source/--row of the message it answers) it writes the reply into the engine's log, so follow-ups stop for that thread, and it adds
     unsubscribes and "no thanks" to the engine's do-not-contact list (engines/<slug>/data/do-not-contact.csv). Outreach Preflight checks every list against it.

A real person asking to stop is a legal and a trust matter (CAN-SPAM in the US, PECR and GDPR in the UK): an unsubscribe is honoured at once and never re-added.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from . import desklog as dl
from .engines import engine_dir, load

CATEGORIES = ["interested", "question", "price", "already_have", "not_now", "not_interested", "wrong_person", "referral", "unsubscribe", "out_of_office", "unclear"]
LABEL = {"interested": "interested", "question": "asks a question", "price": "price objection", "already_have": "already has someone", "not_now": "not now",
         "not_interested": "not interested", "wrong_person": "wrong person", "referral": "points to someone else", "unsubscribe": "asks to stop",
         "out_of_office": "out of office", "unclear": "unclear"}
DESK_CATEGORY = {**{k: v for k, v in LABEL.items()}, "out_of_office": "out of office"}     # the Send Desk's own spelling for the out-of-office reply
PRIORITY = ["unsubscribe", "out_of_office", "wrong_person", "referral", "not_interested", "already_have", "not_now", "price", "interested", "question"]
RX = {
    "unsubscribe": [r"\bunsubscribe\b", r"\b(remove|take) me (off|from)\b", r"\bstop (emailing|messaging|contacting|sending|texting|dm)", r"\bdo not (contact|email|message|call)\b", r"\bdon'?t (contact|email|message) me\b",
                    r"\bopt[- ]?out\b", r"\bnever (contact|email|message|write)\b", r"\breport(ing)? (you|this) (as )?spam\b", r"\bgdpr\b", r"\bleave me alone\b", r"\bstop\.?$"],
    "out_of_office": [r"\bout of (the )?office\b", r"\bauto[- ]?(reply|response|matic reply)\b", r"\bautomatic reply\b", r"\bon (annual |maternity |paternity )?(leave|vacation|holiday)\b",
                      r"\bi (will|am going to) be (away|out|travelling|traveling)\b", r"\bwill (respond|reply|return|be back) (on|after|when)\b", r"\blimited access to (email|my email)\b", r"\bcurrently away\b"],
    "wrong_person": [r"\b(not|wrong) the (right|correct) (person|contact)\b", r"\bwrong (person|contact|department|email)\b", r"\bno longer (works?|with|at|employed)\b", r"\bleft the (company|firm|business)\b",
                     r"\bdoes(n'?t| not) work here\b", r"\bnot (my|our) (area|department|role|job)\b", r"\bi don'?t (handle|manage|deal with) (that|this)\b"],
    "referral": [r"\b(talk|speak|reach out|get in touch|contact|email|write) (to|with) [A-Z][a-z]+", r"\b(you should|you could|you might want to) (talk|speak|contact|email|reach)", r"\bforward(ed|ing)? (this|your|it) (to|email)\b",
                 r"\bcc'?(ing|d)? \w+", r"\b(try|ask) [A-Z][a-z]+ (in|on|at|from)\b", r"\bmy (colleague|partner|manager|boss|assistant)\b.*\b(handles|is in charge|runs)\b", r"\bpassed (this|your) (on|along) to\b"],
    "not_interested": [r"\bnot interested\b", r"\bno,? thanks?\b", r"\bno thank you\b", r"\bwe'?re (all )?(good|set|fine)\b", r"\bnot (for|a fit for) us\b", r"\bpass(ing)? on this\b", r"\bnot (a )?(priority|need)\b",
                       r"\bdon'?t need (this|it|any|that)\b", r"\bnot looking\b", r"\bno need\b", r"\bplease don'?t\b", r"\bnot (right now and )?(ever|interested)\b"],
    "already_have": [r"\balready (have|use|work(ing)? with|got|hired|using|partner)", r"\bwe (have|use) (an |a |our )?(in-?house|agency|provider|vendor|team|someone|consultant)\b", r"\bhandled in-?house\b",
                     r"\bunder contract\b", r"\bhappy with (our|my|the) (current|existing)\b", r"\bwe (currently )?work with\b"],
    "not_now": [r"\bnot (right )?now\b", r"\bmaybe (later|next|in)\b", r"\b(circle|check|touch|follow) back\b", r"\bnext (quarter|month|year|season)\b", r"\bin (a few|\d+|two|three|four|six|couple of) (more )?(weeks?|months?)\b",
                r"\b(too|really|very) busy\b", r"\bbad (time|timing)\b", r"\bnot the (right )?time\b", r"\bafter (the )?(holidays?|summer|q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december|new year)\b",
                r"\bcontact me (again )?(in|after|next)\b", r"\breach out (again )?(in|after|next)\b", r"\bcome back (to me )?(in|after|next)\b"],
    "price": [r"\btoo (expensive|much|pricey)\b", r"\bout of (our|my) budget\b", r"\bno budget\b", r"\bcan'?t afford\b", r"\b(what|how much) (does|do|is|would|will) (it|this|that|the (price|cost|service))\b.*\b(cost|price)\b",
              r"\bhow much\b", r"\bpricing\b", r"\bprice\b", r"\bcost(s)?\b", r"\brates?\b", r"\bquote\b", r"\bcheaper\b", r"\bbudget\b", r"\bfee(s)?\b"],
    "interested": [r"\binterested\b", r"\bsounds (good|great|interesting|helpful)\b", r"\blet'?s (talk|chat|connect|schedule|set up|do it|book|have a call)\b", r"\b(yes|yeah|yep|sure|absolutely|definitely)\b", r"\bhappy to (chat|talk|connect|jump|hop|meet)\b",
                   r"\b(book|schedule|set up) (a |the )?(call|time|meeting|demo)\b", r"\bsend (me )?(some )?(times|availability|a link|your calendar)\b", r"\b(i'?m|i am|we'?re|we are) (free|available|open)\b", r"\bwould love to\b",
                   r"\bgive me a call\b", r"\bcall me\b", r"\bwhen (are you|can we|could we)\b", r"\bpick a time\b", r"\bcalendar\b"],
    "question": [r"\?", r"\bhow (does|do|would|will|long|many|can)\b", r"\bwhat (is|are|does|do|kind|exactly)\b", r"\b(can|could) you (send|share|tell|explain|give|show)\b", r"\bmore (info|information|details)\b", r"\btell me more\b",
                 r"\bdo you (work|offer|have|serve|do)\b", r"\bwho (are|is)\b", r"\bwhere (are|is)\b", r"\bexamples?\b", r"\bcase stud(y|ies)\b", r"\bportfolio\b", r"\breferences?\b"],
}
RX = {k: [re.compile(p, re.I) for p in v] for k, v in RX.items()}
# 'referral' patterns need a real name case; recompile that group without the ignore-case flag for the capitalised-name ones
RX["referral"] = [re.compile(p, 0 if "[A-Z]" in p else re.I) for p in [x.pattern for x in RX["referral"]]]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
WORDNUM = {"a": 1, "one": 1, "two": 2, "couple": 2, "three": 3, "four": 4, "five": 5, "six": 6, "few": 3}


def classify(text: str) -> dict:
    t = re.sub(r"\s+", " ", text or "").strip()
    hits: dict[str, list[str]] = {}
    for cat, pats in RX.items():
        for p in pats:
            m = p.search(t)
            if m:
                hits.setdefault(cat, []).append(m.group(0).strip())
    if not hits:
        return {"category": "unclear", "also": [], "signals": [], "text": t}
    primary = next(c for c in PRIORITY if c in hits)
    if primary == "price" and "interested" in hits and not {"not_interested", "already_have", "not_now"} & set(hits) and not any(
            re.search(r"too (expensive|much|pricey)|out of (our|my) budget|no budget|can'?t afford", h, re.I) for h in hits["price"]):
        primary = "interested"          # "sounds good, what does it cost?" is a yes with a question
    if primary == "question" and re.search(r"\b(not|no)\b[^.?!]{0,20}\b(interested|thanks)\b", t, re.I):
        primary = "not_interested"
    also = [c for c in PRIORITY if c in hits and c != primary][:2]
    return {"category": primary, "also": also, "signals": hits[primary][:3], "text": t}


def _num(s: str) -> int:
    return int(s) if s.isdigit() else WORDNUM.get(s.lower(), 1)


def follow_up_date(category: str, text: str, today: dt.date) -> dt.date | None:
    """When to come back: 'in 3 months', 'next quarter', 'after the holidays', 'in March', 'back on Nov 20'. None when the reply gives no clue."""
    t = (text or "").lower()
    if category == "out_of_office":
        m = re.search(r"\b(?:back|return(?:ing)?|returns?|available|in the office|until|till|through)[^.]{0,25}?\b(?:on|by|from|after)?\s*(?:monday|tuesday|wednesday|thursday|friday)?,?\s*(?:the\s+)?(?:(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)|"
                      r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?)", t)
        if m:
            day, mon = (int(m.group(1)), MONTHS[m.group(2)]) if m.group(1) else (int(m.group(4)), MONTHS[m.group(3)])
            try:
                d = dt.date(today.year, mon, day)
                d = d if d >= today else dt.date(today.year + 1, mon, day)
                return d + dt.timedelta(days=1)
            except ValueError:
                return None
        m = re.search(r"\b(?:back|return(?:ing)?)[^.]{0,25}?\b(\d{4}-\d{2}-\d{2})\b", t)
        if m:
            try:
                return dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=1)
            except ValueError:
                return None
        m = re.search(r"\b(?:for|until|next)\s+(\d+|a|one|two|three|couple|few)\s+(day|week)s?\b", t)
        if m:
            return today + dt.timedelta(days=_num(m.group(1)) * (7 if m.group(2) == "week" else 1) + 1)
        return None
    if category != "not_now":
        return None
    m = re.search(r"\bin (?:a )?(\d+|a|one|two|three|four|five|six|couple of|few|a few)\s*(?:more )?(week|month)s?\b", t)
    if m:
        n = _num(m.group(1).replace("couple of", "couple").replace("a few", "few"))
        return today + dt.timedelta(days=n * (7 if m.group(2) == "week" else 30))
    if re.search(r"\bnext quarter\b", t):
        q_start = ((today.month - 1) // 3 + 1) * 3 + 1
        y = today.year + (1 if q_start > 12 else 0)
        return dt.date(y, q_start - 12 if q_start > 12 else q_start, 1) + dt.timedelta(days=7)
    if re.search(r"\bnext month\b", t):
        y, mo = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return dt.date(y, mo, 1)
    if re.search(r"\bnext (year|season)\b", t):
        return dt.date(today.year + 1, 1, 8)
    if re.search(r"\bafter (the )?(holidays|new year)\b", t):
        return dt.date(today.year + (1 if today.month >= 6 else 0), 1, 8)
    m = re.search(r"\b(?:in|after|around|come back in|reach out in|circle back in)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b", t)
    if m:
        mo = MONTHS[m.group(1)]
        d = dt.date(today.year, mo, 1)
        return (d if d > today else dt.date(today.year + 1, mo, 1)) + dt.timedelta(days=(0 if "after" in m.group(0) else 7))
    if re.search(r"\bnext week\b", t):
        return today + dt.timedelta(days=7)
    return today + dt.timedelta(days=60)           # "not now" with no clue: ask again in about two months, and say that this was the default


TEMPLATES = {
    "interested": "Hi {first}, great to hear from you. {schedule} {sender}",
    "question": "Hi {first}, thanks for asking. [Answer their question in one or two plain sentences here.] If it is easier to talk it through, I am happy to do a short call. {sender}",
    "price": "Hi {first}, fair question. The price depends on [what they need]. Before I give a number: what would solving [their problem] be worth to you each month? Then I can tell you honestly whether it makes sense. {sender}",
    "already_have": "Thanks for telling me, {first}. Most people I talk to already have someone. If it ever helps to have a second opinion on [their area], I can send a one-page comparison. No pressure either way. {sender}",
    "not_now": "No problem, {first}, thank you for the honest answer. I will check back around {date}. If anything changes before then, just reply here. {sender}",
    "not_interested": "Understood, {first}, thank you for letting me know. I will not contact you again about this. All the best with [their business]. {sender}",
    "wrong_person": "Thanks, {first}, and sorry for the interruption. Could you point me to the right person for [the topic]? A name or an email is plenty. {sender}",
    "referral": "Thank you, {first}, that is kind of you. May I mention that you suggested I get in touch? I will keep it short. {sender}",
    "unsubscribe": "Done, {first}. You are removed and you will not hear from me again. Sorry for the bother. {sender}",
    "out_of_office": "",
    "unclear": "",
}
ADVICE = {
    "interested": "Answer the same day. Offer one clear next step with a time, not a menu.",
    "question": "Answer the question first, then offer a call. A question is a buying signal.",
    "price": "Do not drop the price. Ask what the problem costs them each month, then answer honestly.",
    "already_have": "Not a no. Stay polite, keep the door open, and follow up in 60 to 90 days.",
    "not_now": "A timing answer, not a refusal. Reply once, then follow up on the date below.",
    "not_interested": "Reply once, thank them, and stop. They are added to your do-not-contact list when you log it.",
    "wrong_person": "Ask once for the right contact. Every referral is a warm start.",
    "referral": "Ask permission to use their name, then write to the person they named.",
    "unsubscribe": "Honour it at once. Do not pitch. Do not ask why. They go on the do-not-contact list when you log it.",
    "out_of_office": "Do not reply to an auto-reply. It is not an answer: the thread stays open and the follow-up waits.",
    "unclear": "The words did not match any pattern. Read it yourself. If it looks like a yes, answer fast.",
}


def sender_info(slug: str) -> tuple[str, str, str]:
    cfg = load(slug)
    return (cfg.get("sender_name") or "").strip(), (cfg.get("brand_name") or "").strip(), (cfg.get("calendar_url") or cfg.get("calendar") or "").strip()


def draft(category: str, first: str, sender: str, calendar: str, when: dt.date | None) -> str:
    tpl = TEMPLATES.get(category, "")
    if not tpl:
        return ""
    schedule = (f"Here is my calendar so you can pick a time that suits you: {calendar}. If it is easier, tell me two times and I will confirm." if calendar
                else "Would a 15-minute call this week suit you? Tell me a time that works and I will confirm.")
    date_text = when.strftime("%B %d").replace(" 0", " ") if when else "[a date you agree]"
    return tpl.replace(" {sender}", "\n\n{sender}").format(first=first or "there", sender=sender or "[your name]", schedule=schedule, date=date_text).replace("  ", " ")


def dnc_path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "do-not-contact.csv"


def read_dnc(slug: str) -> list[dict]:
    p = dnc_path(slug)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def add_dnc(slug: str, value: str, reason: str = "", today: dt.date | None = None) -> bool:
    """Add an email or a domain. Returns False if it was already there. Never removed by any tool."""
    v = (value or "").strip().lower()
    if not v or not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|[a-z0-9.-]+\.[a-z]{2,}", v):
        return False
    kind = "email" if "@" in v else "domain"
    if any(r["value"] == v for r in read_dnc(slug)):
        return False
    p = dnc_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "kind", "value", "reason"])
        if fresh:
            w.writeheader()
        w.writerow({"date": (today or dt.date.today()).isoformat(), "kind": kind, "value": v, "reason": re.sub(r"[\r\n,]+", " ", reason)[:80]})
    return True


def on_dnc(slug: str, email: str = "", website: str = "") -> str:
    """The reason string if this email or its domain is on the engine's do-not-contact list, else ''."""
    e = (email or "").strip().lower()
    d = re.sub(r"^https?://(www\.)?", "", (website or "").strip().lower()).split("/")[0] or (e.split("@")[1] if "@" in e else "")
    for r in read_dnc(slug):
        if r["value"] == e or (r["kind"] == "domain" and d and (d == r["value"] or d.endswith("." + r["value"]))):
            return f"{r['value']} ({r['reason']}, {r['date']})"
    return ""


def find_row(slug: str, source: str, row: str) -> dict | None:
    for r in dl.load_lists(slug):
        if r["_source"] == source and r["_row_id"] == str(row):
            return r
    return None


def report(slug: str, text: str, name: str = "", source: str = "", row: str = "", log: bool = False, email: str = "", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    text = (text or "").strip()
    if len(text) < 2:
        raise ValueError("Paste the reply you received.")
    if len(text) > 4000:
        raise ValueError("That reply is long (over 4000 characters). Paste the part that answers you.")
    r = classify(text)
    cat = r["category"]
    when_cat = cat if cat in ("not_now", "out_of_office") else ("not_now" if "not_now" in r["also"] else cat)
    when = follow_up_date(when_cat, text, today)
    sender, brand, calendar = sender_info(slug)
    target = find_row(slug, source, row) if (source or row) else None
    if (source or row) and not target:
        raise ValueError(f"I could not find row {row} on list {source} for this engine. Open the Send Desk to see the list name and row number.")
    first = (name or "").strip().split(" ")[0] if name else ""
    if not first and target:
        first = (target.get("contact_first") or (target.get("contact_name") or "").split(" ")[0] or "").strip()
    out = [f"# Reply Desk: {slug}", "", f"Kind: {LABEL[cat]}" + (f" (also sounds like: {', '.join(LABEL[a] for a in r['also'])})" if r["also"] else ""),
           "Because it says: " + (", ".join(f'"{s}"' for s in r["signals"]) if r["signals"] else "nothing I recognise"), "", f"What to do: {ADVICE[cat]}"]
    if when:
        label = "Follow up after they are back, on" if cat == "out_of_office" else "Come back to them on"
        out.append(f"{label}: {when.isoformat()}" + (" (a default of about two months: they gave no date)" if when_cat == "not_now" and not re.search(r"\b(in |next |after |around )", text.lower()) else ""))
    d = draft(cat, first, sender, calendar, when)
    if d:
        out += ["", "Draft answer (you send it yourself):", "", d]
        if "[" in d:
            out += ["", "Fill the [brackets] with real facts before you send. I cannot know them."]
    elif cat == "out_of_office":
        out += ["", "No answer needed."]
    if cat in ("unsubscribe", "not_interested") and not log:
        out += ["", "Add --log (with --source and --row, or --email) to record it and put them on the do-not-contact list."]
    if log:
        if not target and not email:
            raise ValueError("To log it I need the message it answers: --source <list name> --row <number>, or at least --email for a do-not-contact entry.")
        notes = []
        if target:
            status_note = f"{cat} " + (f"-> {when.isoformat()}" if when else "")
            dl.append_events(slug, [{"logged_at": dl.local_now(), "list_date": target["_date"], "source": target["_source"], "row_id": target["_row_id"], "name": target.get("business") or "",
                                     "channel": target.get("channel", ""), "touch": target.get("touch", ""), "status": "replied", "category": DESK_CATEGORY[cat],
                                     "reply": text[:300], "next_step": status_note.strip()}])
            notes.append(f"Logged in the engine's send log as a reply ({DESK_CATEGORY[cat]}).")
        if cat in ("unsubscribe", "not_interested"):
            em = (email or (target or {}).get("email") or "").strip().lower()
            site = (target or {}).get("website") or ""
            added = []
            if em and add_dnc(slug, em, LABEL[cat], today):
                added.append(em)
            if cat == "unsubscribe" and site and add_dnc(slug, re.sub(r"^https?://(www\.)?", "", site.lower()).split("/")[0], LABEL[cat], today):
                added.append(site)
            notes.append("Do-not-contact list: " + (", ".join(added) + " added." if added else "nothing new to add (already listed, or no email known)."))
        out += ["", *notes]
    return "\n".join(out) + "\n"


def dnc_report(slug: str) -> str:
    load(slug)
    rows = read_dnc(slug)
    if not rows:
        return "The do-not-contact list is empty. Unsubscribes and 'no thanks' replies are added here when you log them with the Reply Desk.\n"
    return "\n".join([f"{r['date']}  {r['kind']:<7} {r['value']:<40} {r['reason']}" for r in rows] + [f"\n{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}. No tool removes an entry: edit engines/{slug}/data/do-not-contact.csv by hand if you must."]) + "\n"
