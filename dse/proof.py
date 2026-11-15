"""The Referral and Testimonial Desk: ask at the right moment, record exactly what people agreed to, and use only what is approved and true.

    python dse.py proof due <engine>                                       who is at a good moment to ask, who needs a follow-up or a thank-you
    python dse.py proof ask <engine> --who Dana --source client:acme-dental [--kind both|testimonial|referral] [--sent]
    python dse.py proof mark <engine> ASK-001 --to sent|answered|declined|no-reply
    python dse.py proof quote <engine> --who "Dana Cole" --role "Owner, Acme Dental" --text "their exact words" --channel "WhatsApp 14 Nov" [--ask ASK-001]
                              [--consent yes --consent-how "replied yes on WhatsApp, 15 Nov" --name full|first|anonymous --company yes|no --numbers yes|no --scope proposals,website]
    python dse.py proof claim <engine> Q-001 --number "3 days to same day" --source words|record:client/acme-dental:cost_month
    python dse.py proof excerpt <engine> Q-001 --text "a part of their exact words"
    python dse.py proof quotes <engine> [--scope proposals]                 only approved, consented, true quotes, with the attribution THEY chose
    python dse.py proof withdraw <engine> Q-001 --reason "asked me to remove it"
    python dse.py proof refer <engine> --from Dana --referred "Bella Dental" [--contact ...] [--ask ASK-001]
    python dse.py proof referral <engine> REF-001 --status contacted|call-booked|won|lost|not-now [--value 1500]
    python dse.py proof thanked <engine> REF-001
    python dse.py proof list <engine>

The rules it keeps:
  * the moment: a client whose work is delivered, a DFY student at 6 and at 12 qualified months. Asking is kind and optional ("no pressure, and no is fine"); you send every message yourself
  * their words are kept EXACTLY as written. A quote is USABLE only when the person's consent is recorded (that you may use the text, how their name is shown, whether numbers may be used,
    where it may appear) and it has not been withdrawn. You may use an excerpt only if it is a verbatim part of their words
  * a NUMBER you want to quote (3 days to same day, 40% more bookings) is usable only if it is in their own words, or it matches a figure in your own records (the price, the weeks, the
    monthly cost they gave you, qualified months, the amount remitted). An unverified number is not used. Demos are labelled as demos; nothing is invented, rounded up or tidied into something they did not say
  * a person can withdraw consent at any time and it is honoured at once; Outreach Preflight blocks a message that still carries a withdrawn quote
  * a DFY student's yes or no here changes nothing about their remittance
Data: engines/<engine>/data/proof.json.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import clients as cl
from . import cuts
from .engines import engine_dir, load

KINDS = ("testimonial", "referral", "both")
ASK_STATUS = ("draft", "sent", "answered", "declined", "no-reply")
REF_STATUS = ("new", "contacted", "call-booked", "won", "lost", "not-now")
SCOPES = ("proposals", "website", "social", "outreach")
NAMES = ("full", "first", "anonymous")
FOLLOW_DAYS, GIVE_UP_DAYS, CONSENT_WAIT_DAYS = 7, 21, 7
FIELDS = {"price": "price", "weeks": "weeks", "deposit_pct": "deposit_pct", "cost_month": "cost_month"}       # client record fields a number can be checked against
STUDENT_FIELDS = ("qualified_months", "total_remitted", "months_filed")


def path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "proof.json"


def load_data(slug: str) -> dict:
    p = path(slug)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in ("asks", "quotes", "referrals"):
                d.setdefault(k, [])
            return d
        except ValueError:
            pass
    return {"asks": [], "quotes": [], "referrals": []}


def save_data(slug: str, d: dict) -> None:
    p = path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def next_id(items: list[dict], prefix: str) -> str:
    n = max((int(i["id"].split("-")[1]) for i in items), default=0)
    return f"{prefix}-{n + 1:03d}"


def clean(s: str, n: int = 200) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()[:n]


def first(name: str) -> str:
    return (name or "").split(" ")[0] or "there"


def date_or_today(s: str, today: dt.date) -> dt.date:
    if not s:
        return today
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError("Dates are YYYY-MM-DD.")
    return dt.date.fromisoformat(s)


def find(items: list[dict], iid: str, what: str) -> dict:
    it = next((x for x in items if x["id"] == (iid or "").upper()), None)
    if not it:
        raise ValueError(f"No {what} '{iid}'. See them with: python dse.py proof list <engine>")
    return it


# ------------------------------------------------------------------ sources (clients and students)

def source_context(slug: str, source: str) -> dict:
    """What a draft needs about the person: name, what the work was or how far they got. source is client:<slug>, student:<slug> or manual."""
    kind, _, name = (source or "manual").partition(":")
    if kind == "client":
        for _f, c in cl.all_clients(slug):
            if c["slug"] == name:
                return {"kind": "client", "who": c.get("contact") or c["client"], "company": c["client"], "offer": c["offer"], "problem": c.get("problem", ""), "status": cl.status(c), "record": c}
        raise ValueError(f"No client '{name}' in this engine. Clients: " + (", ".join(c["slug"] for _f, c in cl.all_clients(slug)) or "none"))
    if kind == "student":
        for _f, s in cuts.all_students(slug):
            if s["slug"] == name:
                total, qn = cuts.dfy_totals(s)
                return {"kind": "student", "who": s["name"], "company": "", "qn": qn, "total": total, "status": s["status"], "record": s}
        raise ValueError(f"No student '{name}' in this engine. Students: " + (", ".join(s["slug"] for _f, s in cuts.all_students(slug)) or "none"))
    if source in ("", "manual"):
        return {"kind": "manual", "who": "", "company": ""}
    raise ValueError("Source is client:<name>, student:<name> or manual.")


# ------------------------------------------------------------------ drafts

def drafts(kind: str, ctx: dict, who: str, sender: str) -> list[tuple[str, str]]:
    f, sig = first(who or ctx.get("who", "")), sender or "[your name]"
    out = []
    if kind in ("testimonial", "both"):
        if ctx["kind"] == "student":
            body = (f"Hi {f}, congratulations on {ctx.get('qn', 0)} qualified month{'s' if ctx.get('qn', 0) != 1 else ''}. I would love to share your story, if you are open to it. "
                    "A few sentences in your own words is plenty: where you started, what changed, and what you would tell someone just beginning. "
                    "If you are happy for me to use it, tell me how you would like your name shown (full name, first name only, or anonymous) and whether I may include any numbers you mention. "
                    "This is completely separate from your DFY, and a no changes nothing.")
        else:
            what = ctx.get("offer") or "the work"
            body = (f"Hi {f}, I am glad {what.rstrip('.').lower() if ctx.get('offer') else what} is done and working for you. Would you be willing to share a few words about working together? "
                    "Three easy questions: 1) What was the problem before? 2) What is different now? 3) Would you recommend me, and to whom? "
                    "A couple of sentences in your own words is plenty. If you are happy for me to use it, tell me how you would like your name shown (full name and business, first name only, or anonymous) "
                    "and whether I may include any numbers you mention. No pressure at all.")
        out.append(("Testimonial request", f"{body}\n\n{sig}"))
    if kind in ("referral", "both"):
        prob = (ctx.get("problem") or "").strip().rstrip(".")
        body = (f"Hi {f}, do you know one or two people who have the same problem" + (f" ({prob[:90]})" if prob else "") + "? "
                "An introduction would mean a lot. I would keep it brief and respectful of their time, and I am happy to thank you properly. If nobody comes to mind, that is completely fine.")
        out.append(("Referral ask", f"{body}\n\n{sig}"))
    return out


def followup_draft(who: str, sender: str) -> str:
    return f"Hi {first(who)}, just a gentle note in case my message got buried. No pressure at all, and a no is completely fine.\n\n{sender or '[your name]'}"


def consent_draft(q: dict, sender: str) -> str:
    return (f"Hi {first(q['who'])}, thank you. Here is exactly how I would use your words:\n\n\"{q['text']}\"\n{attribution(q)}\n\n"
            "Is that OK? Reply yes and I will use it. You can change your mind at any time and I will remove it.\n\n" + (sender or "[your name]"))


def thanks_draft(r: dict, sender: str) -> str:
    return f"Hi {first(r['referrer'])}, thank you for introducing {r['name']}. I will look after them well, and I will let you know how it goes.\n\n{sender or '[your name]'}"


# ------------------------------------------------------------------ attribution and usable quotes

def attribution(q: dict) -> str:
    c = q.get("consent") or {}
    name, comp = c.get("name", "anonymous"), c.get("company", False)
    role = (q.get("role") or "").strip()
    if name == "anonymous":
        return "A client" if not (role and comp) else f"A client, {role}"
    shown = q["who"] if name == "full" else first(q["who"])
    return shown + (f", {role}" if role and comp else "")


def has_digits(t: str) -> bool:
    return bool(re.search(r"\d", t or ""))


def usable_reason(q: dict, scope: str = "") -> str:
    """'' when the quote may be used (for this scope), else the plain reason it may not."""
    c = q.get("consent") or {}
    if q["status"] == "withdrawn":
        return "consent withdrawn"
    if q["status"] != "approved" or not c.get("use_text"):
        return "no recorded consent yet"
    if scope and scope not in c.get("scope", []):
        return f"the person did not agree to {scope}"
    shown = q.get("excerpt") or q["text"]
    if has_digits(shown) and not c.get("numbers"):
        return "it contains numbers and the person did not allow numbers"
    return ""


def verified_claims(q: dict) -> list[dict]:
    return [c for c in q.get("claims", []) if c.get("verified")]


def check_claim(slug: str, q: dict, number: str, source: str) -> tuple[bool, str]:
    """Is this number true? 'words': it is in their exact words. 'record:<client|student>/<name>:<field>': it equals a figure in your own records."""
    num = clean(number, 80)
    if not num:
        raise ValueError("Say the number or claim, for example --number \"3 days to same day\".")
    if source == "words":
        digits = re.findall(r"\d[\d,.]*%?", num)
        if not digits:
            raise ValueError("A claim must contain a number.")
        ok = all(re.search(rf"(?<![\d.,]){re.escape(d.rstrip('%,.'))}(?![\d])", q["text"]) for d in digits)
        return ok, "it is in their own words" if ok else "that number does not appear in their exact words"
    m = re.fullmatch(r"record:(client|student)/([a-z0-9-]{1,40}):([a-z_]+)", source or "")
    if not m:
        raise ValueError("Source is words, or record:client/<name>:<field> (price, weeks, deposit_pct, cost_month) or record:student/<name>:<field> (qualified_months, total_remitted, months_filed).")
    kind, name, fld = m.groups()
    want = re.findall(r"\d[\d,.]*", num)
    if not want:
        raise ValueError("A claim must contain a number.")
    claimed = float(want[0].replace(",", ""))
    if kind == "client":
        ctx = source_context(slug, f"client:{name}")
        if fld not in FIELDS:
            raise ValueError("Client fields: " + ", ".join(FIELDS) + ".")
        have = ctx["record"].get(FIELDS[fld])
    else:
        ctx = source_context(slug, f"student:{name}")
        if fld not in STUDENT_FIELDS:
            raise ValueError("Student fields: " + ", ".join(STUDENT_FIELDS) + ".")
        s = ctx["record"]
        total, qn = cuts.dfy_totals(s)
        have = {"qualified_months": qn, "total_remitted": total, "months_filed": len(s["statements"])}[fld]
    if have is None or (fld == "cost_month" and not have):
        return False, f"your records have no {fld} for {name}"
    ok = abs(float(have) - claimed) < (0.5 if claimed == int(claimed) else 0.005)
    return ok, (f"matches {fld} = {have:g} in your records" if ok else f"your records say {fld} = {have:g}, not {claimed:g}")


# ------------------------------------------------------------------ actions

def ask(slug: str, who: str, source: str = "manual", kind: str = "both", trigger: str = "manual", sent: bool = False, today: dt.date | None = None) -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    if kind not in KINDS:
        raise ValueError("Kind is testimonial, referral or both.")
    ctx = source_context(slug, source)
    name = clean(who or ctx.get("who", ""), 60)
    if len(name) < 2:
        raise ValueError("Say who you are asking (--who Dana).")
    d = load_data(slug)
    a = {"id": next_id(d["asks"], "ASK"), "who": name, "kind": kind, "source": source or "manual", "trigger": trigger, "created": today.isoformat(), "sent_on": "", "status": "draft", "follow_up": False, "notes": ""}
    if sent:
        a["status"], a["sent_on"] = "sent", today.isoformat()
    d["asks"].append(a)
    save_data(slug, d)
    sender = (cfg.get("sender_name") or "").strip()
    out = [f"# Referral and Testimonial Desk: {a['id']} for {name}", "", f"A {kind} request ({a['status']}). Nothing was sent: send it yourself, then run: python dse.py proof mark {slug} {a['id']} --to sent", ""]
    for title, body in drafts(kind, ctx, name, sender):
        out += [f"## {title}", "", body, ""]
    if "[" in "".join(b for _t, b in drafts(kind, ctx, name, sender)):
        out.append("Fill the [brackets] yourself.")
    return "\n".join(out) + "\n"


def mark(slug: str, ask_id: str, to: str, today: dt.date | None = None, date: str = "") -> str:
    load(slug)
    today = today or dt.date.today()
    if to not in ASK_STATUS:
        raise ValueError("Status is " + ", ".join(ASK_STATUS) + ".")
    d = load_data(slug)
    a = find(d["asks"], ask_id, "ask")
    a["status"] = to
    if to == "sent":
        a["sent_on"] = date_or_today(date, today).isoformat()
    save_data(slug, d)
    return f"{a['id']} ({a['who']}) is now {to}.\n" + ("Next: when they reply with words you may use, run proof quote.\n" if to == "answered" else "")


def quote(slug: str, who: str, text: str, role: str = "", channel: str = "", ask_id: str = "", consent: bool = False, consent_how: str = "", name: str = "anonymous", company: bool = False,
          numbers: bool = False, scope: str = "", today: dt.date | None = None) -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    text = (text or "").strip()
    if len(clean(who, 60)) < 2:
        raise ValueError("Say whose words these are (--who).")
    if not 8 <= len(text) <= 1200:
        raise ValueError("Paste their exact words (8 to 1,200 characters).")
    if name not in NAMES:
        raise ValueError("Name is full, first or anonymous.")
    scopes = [x.strip() for x in scope.split(",") if x.strip()]
    if any(x not in SCOPES for x in scopes):
        raise ValueError("Scope is a comma list of: " + ", ".join(SCOPES) + ".")
    if consent and (len(clean(consent_how)) < 5 or not scopes):
        raise ValueError("To record consent say how they agreed (--consent-how \"replied yes on WhatsApp, 15 Nov\") and where it may be used (--scope proposals,website).")
    d = load_data(slug)
    if ask_id:
        find(d["asks"], ask_id, "ask")["status"] = "answered"
    q = {"id": next_id(d["quotes"], "Q"), "who": clean(who, 60), "role": clean(role, 80), "text": text, "channel": clean(channel, 80), "ask": (ask_id or "").upper(), "received_on": today.isoformat(), "excerpt": "",
         "consent": {"use_text": bool(consent), "name": name, "company": bool(company), "numbers": bool(numbers), "scope": scopes if consent else [], "how": clean(consent_how, 160), "given_on": today.isoformat() if consent else ""},
         "claims": [], "status": "approved" if consent else "pending consent"}
    d["quotes"].append(q)
    save_data(slug, d)
    sender = (cfg.get("sender_name") or "").strip()
    out = [f"# Quote {q['id']} from {q['who']}: {q['status']}", "", f"\"{text}\"", ""]
    if consent:
        why = usable_reason(q)
        out.append(f"Consent recorded ({q['consent']['how']}). Shown as: {attribution(q)}. May be used in: {', '.join(scopes)}." + (f" NOT usable yet: {why}." if why else " Usable now."))
    else:
        out += ["No consent recorded, so this quote cannot be used anywhere yet. Send them this, and when they say yes record it with --consent yes --consent-how ... --scope ...:", "", consent_draft({**q, "consent": {"name": name, "company": company}}, sender)]
    if has_digits(text) and not numbers:
        out.append("Note: the quote contains numbers and numbers are not allowed, so it stays unusable until they allow numbers (ask them) or the quote is reduced to an excerpt without them.")
    return "\n".join(out) + "\n"


def claim(slug: str, quote_id: str, number: str, source: str) -> str:
    load(slug)
    d = load_data(slug)
    q = find(d["quotes"], quote_id, "quote")
    ok, why = check_claim(slug, q, number, source)
    q["claims"].append({"text": clean(number, 80), "source": source, "verified": ok, "why": why})
    save_data(slug, d)
    return (f"Claim on {q['id']}: \"{clean(number, 80)}\": " + ("VERIFIED, " if ok else "NOT verified, ") + why + (". It may be quoted." if ok else ". It will not be used until it can be backed up.") + "\n")


def excerpt(slug: str, quote_id: str, text: str) -> str:
    load(slug)
    d = load_data(slug)
    q = find(d["quotes"], quote_id, "quote")
    ex = (text or "").strip()
    if len(ex) < 5:
        raise ValueError("Give the part of their words you want to use.")
    if ex.lower() not in q["text"].lower():
        raise ValueError("An excerpt must be a verbatim part of their exact words. That text is not in the quote, so it cannot be used.")
    q["excerpt"] = q["text"][q["text"].lower().index(ex.lower()):][:len(ex)]
    save_data(slug, d)
    why = usable_reason(q)
    return f"Excerpt saved for {q['id']}: \"{q['excerpt']}\"" + (f". Not usable yet: {why}." if why else ". Usable.") + "\n"


def withdraw(slug: str, quote_id: str, reason: str = "", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    d = load_data(slug)
    q = find(d["quotes"], quote_id, "quote")
    q["status"], q["withdrawn_on"], q["withdrawn_reason"] = "withdrawn", today.isoformat(), clean(reason, 120)
    save_data(slug, d)
    return f"{q['id']} is withdrawn: it will not be used anywhere, and Outreach Preflight blocks any message that still contains it. Remove it from anything already published or sent.\n"


def quotes(slug: str, scope: str = "") -> str:
    load(slug)
    if scope and scope not in SCOPES:
        raise ValueError("Scope is one of: " + ", ".join(SCOPES) + ".")
    d = load_data(slug)
    ok, skipped = [], []
    for q in d["quotes"]:
        why = usable_reason(q, scope)
        (skipped if why else ok).append((q, why))
    out = [f"# Usable quotes{' for ' + scope if scope else ''}: {len(ok)}", ""]
    for q, _w in ok:
        out += [f"{q['id']}: \"{q.get('excerpt') or q['text']}\"", f"   {attribution(q)}" + (f"   (full words in {q['id']})" if q.get("excerpt") else "")]
        nums = verified_claims(q)
        if nums:
            out.append("   Verified numbers: " + "; ".join(f"{c['text']} ({c['why']})" for c in nums))
        bad = [c for c in q.get("claims", []) if not c.get("verified")]
        if bad:
            out.append("   NOT usable numbers: " + "; ".join(c["text"] for c in bad))
        out.append("")
    if not ok:
        out.append("None yet. A quote becomes usable when their consent is recorded and it has not been withdrawn.\n")
    if skipped:
        out += ["Not usable: " + "; ".join(f"{q['id']} {q['who']} ({w})" for q, w in skipped), ""]
    out.append("Use only these, word for word, with the attribution shown. Nothing was sent.")
    return "\n".join(out) + "\n"


def refer(slug: str, from_who: str, name: str, contact: str = "", ask_id: str = "", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    if len(clean(from_who, 60)) < 2 or len(clean(name, 80)) < 2:
        raise ValueError("Say who referred them (--from) and who they referred (--name).")
    d = load_data(slug)
    if ask_id:
        find(d["asks"], ask_id, "ask")
    r = {"id": next_id(d["referrals"], "REF"), "referrer": clean(from_who, 60), "name": clean(name, 80), "contact": clean(contact, 120), "ask": (ask_id or "").upper(), "received_on": today.isoformat(),
         "status": "new", "thanked_on": "", "value": 0.0}
    d["referrals"].append(r)
    save_data(slug, d)
    cfg = load(slug)
    return (f"Referral {r['id']}: {r['name']}, from {r['referrer']}. Write to them this week, and mention who suggested you (they agreed to the introduction).\n\nThank-you draft for {first(r['referrer'])}:\n\n"
            + thanks_draft(r, (cfg.get("sender_name") or "").strip()) + f"\n\nWhen you have thanked them: python dse.py proof thanked {slug} {r['id']}\n")


def referral(slug: str, ref_id: str, status: str, value: float = 0) -> str:
    load(slug)
    if status not in REF_STATUS:
        raise ValueError("Status is " + ", ".join(REF_STATUS) + ".")
    if not 0 <= value <= 10_000_000:
        raise ValueError("Value is the amount of the first sale (or 0).")
    d = load_data(slug)
    r = find(d["referrals"], ref_id, "referral")
    r["status"] = status
    if value:
        r["value"] = value
    save_data(slug, d)
    return f"{r['id']} ({r['name']}) is now {status}." + (" Thank " + r["referrer"] + f" if you have not: python dse.py proof thanked {slug} {r['id']}" if status == "won" and not r["thanked_on"] else "") + "\n"


def thanked(slug: str, ref_id: str, today: dt.date | None = None) -> str:
    load(slug)
    d = load_data(slug)
    r = find(d["referrals"], ref_id, "referral")
    r["thanked_on"] = (today or dt.date.today()).isoformat()
    save_data(slug, d)
    return f"Recorded: {r['referrer']} was thanked for {r['name']}.\n"


# ------------------------------------------------------------------ the moments

def moments(slug: str, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    d = load_data(slug)
    out: list[dict] = []
    for _f, c in cl.all_clients(slug):
        st = cl.status(c)
        if st in ("delivered", "closed") and not any(a["source"] == f"client:{c['slug']}" for a in d["asks"]):
            out.append({"type": "ask", "who": c.get("contact") or c["client"], "why": f"{c['client']}: the work is {st}", "command": f"python dse.py proof ask {slug} --who \"{c.get('contact') or c['client']}\" --source client:{c['slug']} --trigger {st}"})
    for _f, s in cuts.all_students(slug):
        if s.get("program") != "dfy":
            continue
        total, qn = cuts.dfy_totals(s)
        done = {a["trigger"] for a in d["asks"] if a["source"] == f"student:{s['slug']}"}
        for mile in (12, 6):                                  # the highest milestone reached is the moment; one already asked at is not asked again
            if qn >= mile or (mile == 12 and s["status"] == "completed"):
                if f"qualified-{mile}" not in done:
                    out.append({"type": "ask", "who": s["name"], "why": f"{s['name']} has {qn} qualified months", "command": f"python dse.py proof ask {slug} --who \"{s['name']}\" --source student:{s['slug']} --trigger qualified-{mile}"})
                break
    for a in d["asks"]:
        if a["status"] == "sent" and a["sent_on"]:
            days = (today - dt.date.fromisoformat(a["sent_on"])).days
            if days >= GIVE_UP_DAYS:
                out.append({"type": "close", "who": a["who"], "why": f"{a['id']} sent {days} days ago, no reply", "command": f"python dse.py proof mark {slug} {a['id']} --to no-reply"})
            elif days >= FOLLOW_DAYS and not a["follow_up"]:
                out.append({"type": "follow", "who": a["who"], "why": f"{a['id']} sent {days} days ago, no reply: one gentle follow-up", "command": f"python dse.py proof mark {slug} {a['id']} --to sent   (after you send the follow-up)"})
    for q in d["quotes"]:
        if q["status"] == "pending consent" and (today - dt.date.fromisoformat(q["received_on"])).days >= CONSENT_WAIT_DAYS:
            out.append({"type": "consent", "who": q["who"], "why": f"{q['id']} has waited for consent since {q['received_on']}", "command": f"send them the consent message printed by: python dse.py proof quote ... (or ask again)"})
    for r in d["referrals"]:
        if not r["thanked_on"]:
            out.append({"type": "thank", "who": r["referrer"], "why": f"{r['id']} ({r['name']}) has not been thanked", "command": f"python dse.py proof thanked {slug} {r['id']}   (after you thank them)"})
    return out


def due(slug: str, today: dt.date | None = None) -> str:
    load(slug)
    ms = moments(slug, today)
    if not ms:
        return "Nothing to do right now. Asks come up when a client's work is delivered or a DFY student reaches 6 or 12 qualified months.\n"
    names = {"ask": "Good moment to ask", "follow": "Follow up once", "close": "Close the ask", "consent": "Waiting for consent", "thank": "Thank"}
    out = [f"# Referral and Testimonial Desk: {len(ms)} thing(s) to do", ""]
    for m in ms:
        out += [f"- {names[m['type']]}: {m['who']}: {m['why']}", f"    {m['command']}"]
    return "\n".join(out) + "\n"


def attention(slug: str, today: dt.date) -> dict:
    ms = moments(slug, today)
    return {"asks": [m["who"] for m in ms if m["type"] == "ask"], "thanks": [m["who"] for m in ms if m["type"] == "thank"], "follow": [m["who"] for m in ms if m["type"] in ("follow", "consent")]}


def norm_words(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def shares_words(quote_text: str, message: str, shortest: int = 25) -> bool:
    """True when the message carries a run of at least `shortest` characters of the quote's words (punctuation and case ignored)."""
    q, m = norm_words(quote_text), norm_words(message)
    if len(q) < shortest:
        return q != "" and q in m
    return any(q[i:i + shortest] in m for i in range(0, len(q) - shortest + 1, 4)) or q[-shortest:] in m


def withdrawn_texts(slug: str) -> list[tuple[str, str, int]]:
    """(quote id, text, shortest match worth blocking) for every withdrawn quote, its full words and its excerpt, for Outreach Preflight."""
    out = []
    for q in load_data(slug)["quotes"]:
        if q["status"] == "withdrawn":
            out.append((q["id"], q["text"], 25))
            if q.get("excerpt"):
                out.append((q["id"], q["excerpt"], 18))
    return out


def listing(slug: str) -> str:
    load(slug)
    d = load_data(slug)
    L = [f"# Referral and Testimonial Desk: {slug}", "", f"Asks: {len(d['asks'])} ({sum(1 for a in d['asks'] if a['status'] == 'sent')} waiting, {sum(1 for a in d['asks'] if a['status'] == 'answered')} answered). "
         f"Quotes: {len(d['quotes'])} ({sum(1 for q in d['quotes'] if not usable_reason(q))} usable). Referrals: {len(d['referrals'])} ({sum(1 for r in d['referrals'] if r['status'] == 'won')} won).", ""]
    L += ["## Asks"] + ([f"- {a['id']} {a['who']}: {a['kind']}, {a['status']}" + (f" (sent {a['sent_on']})" if a["sent_on"] else "") for a in d["asks"]] or ["- none"])
    L += ["", "## Quotes"] + ([f"- {q['id']} {q['who']}: {q['status']}" + (f", not usable: {usable_reason(q)}" if usable_reason(q) else ", usable") for q in d["quotes"]] or ["- none"])
    L += ["", "## Referrals"] + ([f"- {r['id']} {r['name']} (from {r['referrer']}): {r['status']}" + ("" if r["thanked_on"] else ", not yet thanked") + (f", ${r['value']:,.0f}" if r["value"] else "") for r in d["referrals"]] or ["- none"])
    return "\n".join(L) + "\n"
