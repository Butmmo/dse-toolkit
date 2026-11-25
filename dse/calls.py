"""The Call Desk: prepare for a booked call and document an agreed next step afterward.

    python dse.py call prep <engine> --source 2026-11-09 --row 7          a one-page brief for that lead (and a notes sheet)
    python dse.py call after <engine> --source 2026-11-09 --row 7 --outcome follow_up|sold|no_sale|no_show [--problem "..."] [--cost-month 4000] [--price 1500] [--agreed "..."] [--stop]

prep builds engines/<engine>/calls/<date>-<lead>/prep.md and notes.md from YOUR records only: the lead's row on your send list, the message you sent, the reply they wrote (in their
words), what the website check or the enrichment found, and what you need in hand before you speak. Every fact names where it came from. Where something is not known it says "not found"
and where to look: nothing about the lead is ever invented. The question plan follows the same five headings as your call scorecard (Situation, Problem, Cost, Result wanted, Next step).

after turns what you typed into the next steps, in after.md: a recap you may send at the time and through the channel you agreed (not a template of promises), the scorecard command to run,
and for a call that should lead to a proposal, the proposal command already filled in with what they told you. A call you won or lost is written into the send log so your results stay true.
--stop adds them to your do-not-contact list (when they asked not to be contacted). Nothing is sent.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from . import callscore, desklog as dl, replies
from .common import ROOT
from .engines import engine_dir, load
from .importer import clean_domain

OUTCOMES = ("follow_up", "sold", "no_sale", "no_show")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "lead"


def find_row(slug: str, source: str, row: str) -> dict:
    for r in dl.load_lists(slug):
        if r["_source"] == source and r["_row_id"] == str(row):
            return r
    have = ", ".join(sorted({r["_source"] for r in dl.load_lists(slug)})[-5:]) or "none"
    raise ValueError(f"I could not find row {row} on list {source} in engine {slug}. Lists: {have}. The Send Desk shows the list name and row number.")


def events_for(slug: str, row: dict) -> list[dict]:
    return dl.history(slug).get((row["_source"], row["_row_id"]), [])


def enrichment_for(slug: str, domain: str) -> dict:
    """The newest enriched row for this website (from `dse.py enrich`), or {}."""
    if not domain:
        return {}
    files = sorted(list((ROOT / "my-lists").glob("*enriched*.csv")) + list((engine_dir(slug) / "imports").glob("*.csv")), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        try:
            with p.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    site = clean_domain(r.get("website") or r.get("Website") or r.get("domain") or "")
                    if site and site == domain and (r.get("decision_maker") or r.get("site_description") or r.get("booking_tool") or r.get("tech_stack") or r.get("lead_why")):
                        return {**r, "_file": p.name}
        except (OSError, csv.Error):
            continue
    return {}


def facts_for(row: dict, ev: list[dict], en: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """[(fact, where it came from)] in the order worth opening with, and what is not known."""
    facts: list[tuple[str, str]] = []
    reply = next((e for e in reversed(ev) if e.get("reply")), None)
    if reply and reply.get("reply", "").strip():
        facts.append((f"They wrote: \"{reply['reply'].strip()[:200]}\"", f"their reply, logged {str(reply.get('logged_at', ''))[:10]}"))
    if row.get("gap_used"):
        facts.append((f"Your check found: {row['gap_used'].strip()}", f"your send list ({row['_source']}, row {row['_row_id']})"))
    if en.get("decision_maker"):
        facts.append((f"{en['decision_maker']} is named" + (f" as {en['decision_maker_title']}" if en.get("decision_maker_title") else "") + " on their site", en.get("decision_maker_source") or f"enrichment ({en['_file']})"))
    elif row.get("contact_name"):
        facts.append((f"Your contact is {row['contact_name']}" + (f", {row['contact_title']}" if row.get("contact_title") else ""), "your send list"))
    if en.get("site_description"):
        facts.append((f"Their site says: \"{en['site_description'][:160]}\"", f"their homepage ({en['_file']})"))
    if en.get("booking_tool"):
        facts.append((f"They already use an online booking tool ({en['booking_tool']})", f"their site ({en['_file']})"))
    if en.get("tech_stack"):
        facts.append((f"Their site is built with {en['tech_stack']}", f"their site ({en['_file']})"))
    if row.get("city") or row.get("category"):
        facts.append((f"{row.get('business', 'They')} is " + (f"a {row['category']}" if row.get("category") else "a business") + (f" in {row['city']}" if row.get("city") else ""), "your send list"))
    first_msg = (row.get("opener") or "").strip()
    unknown = []
    if not en:
        unknown.append("No website facts yet: run python dse.py enrich --site " + (row.get("website") or "<their site>") + " to see what their own site says.")
    elif not en.get("decision_maker"):
        unknown.append("Who decides is not named on their site: ask at the start of the call.")
    if not any(f[0].startswith("They wrote") for f in facts):
        unknown.append("No written reply is logged for this row (the call may have been booked another way): note why they agreed to talk.")
    if not first_msg:
        unknown.append("Your first message is not on the row: find what you sent so you do not repeat yourself.")
    return facts, unknown


def prep(slug: str, source: str, row_id: str, today: dt.date | None = None) -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    row = find_row(slug, source, row_id)
    ev = events_for(slug, row)
    en = enrichment_for(slug, clean_domain(row.get("website", "")))
    facts, unknown = facts_for(row, ev, en)
    name = row.get("business") or row.get("name") or f"row {row_id}"
    contact = en.get("decision_maker") or row.get("contact_name") or ""
    folder = engine_dir(slug) / "calls" / f"{today.isoformat()}-{slugify(name)}"
    folder.mkdir(parents=True, exist_ok=True)
    sender = (cfg.get("sender_name") or "").strip() or "[your name]"
    cal = (cfg.get("calendar_url") or cfg.get("calendar") or "").strip()
    booked = next((e for e in reversed(ev) if e.get("status") == "booked"), None)
    L = [f"# Call prep: {name}", "", f"Prepared {today.isoformat()} from your own records. List {source}, row {row_id}" + (f"; call booked {str(booked['logged_at'])[:10]}" if booked else "") + ".", ""]
    L += ["## Who", f"- {name}" + (f", {row['city']}" if row.get("city") else "") + (f", {row['website']}" if row.get("website") else ""), f"- Talking to: {contact or 'not known yet: ask who decides'}"]
    for k, lab in (("email", "Email"), ("phone", "Phone")):
        if row.get(k) or en.get(k + "_found" if k == "phone" else "best_email"):
            L.append(f"- {lab}: {row.get(k) or en.get('phone_found' if k == 'phone' else 'best_email')}")
    L += ["", "## What they said and what you sent"]
    if row.get("opener"):
        L.append(f"- You sent ({row.get('channel', '')}): \"{row['opener'].strip()[:300]}\"")
    for e in ev:
        if e.get("reply"):
            L.append(f"- They replied ({str(e.get('logged_at', ''))[:10]}{', ' + e['category'] if e.get('category') else ''}): \"{e['reply'].strip()[:300]}\"")
    if L[-1] == "## What they said and what you sent":
        L.append("- nothing logged")
    L += ["", "## Open with three facts (each shows where it came from)"]
    for fct, src in facts[:3]:
        L.append(f"- {fct} ({src})")
    if len(facts) < 3:
        L.append(f"- You have {len(facts)} real fact(s). Find {3 - len(facts)} more before the call: their website, Google reviews, their social pages.")
    if facts[3:]:
        L += ["", "Also known: " + "; ".join(f"{f} ({s})" for f, s in facts[3:6])]
    L += ["", "## Your question plan (the same five headings as your scorecard; they should talk about 60% of the time)", "",
          "1. Situation: \"Tell me what you are doing today to get new customers.\" and \"How long has it been that way?\""]
    gap = (row.get("gap_used") or "").strip().rstrip(".")
    L.append(f"2. Problem: " + (f"\"I noticed {gap}. What happens today when that comes up?\" then \"What have you tried?\"" if gap else "\"What is not working about that?\" then \"What have you tried?\""))
    L += ["3. Cost (get a number): \"What does that cost you each month, in money, time or lost customers?\" and \"If nothing changes, where are you in a year?\"",
          "4. Result wanted: \"If we fixed this, what would be different? How would you know it worked?\"",
          "5. Next step: agree what yes, no or a next step looks like BEFORE you present. Ask who else decides, the budget range and when they want it fixed.", ""]
    L += ["## Open the call with an up-front contract (60 to 90 seconds)",
          "\"Thanks for jumping on. We have 30 minutes, does that still work? What would you like help with today? I would like to ask a few questions about where you are now, then tell you honestly if I can help. Is it okay if I ask those questions? At the end we will decide together: yes, no, or a clear next step.\"", ""]
    L += ["## In hand before you speak", "- [ ] The price, what is included and what is NOT included, written down (never guess these on a call)", "- [ ] The payment or contract link" + ("" if cal else " and your calendar link (not set in your engine settings)"),
          "- [ ] A notes sheet open: " + str((folder / "notes.md").relative_to(ROOT).as_posix()) + (f"\n- Your calendar: {cal}" if cal else "")]
    if unknown:
        L += ["", "## Not known (do not pretend otherwise)"] + [f"- {u}" for u in unknown]
    L += ["", "## When it ends", f"python dse.py call after {slug} --source {source} --row {row_id} --outcome follow_up --problem \"...\" --cost-month N --price N", "Nothing was sent."]
    text = "\n".join(L) + "\n"
    (folder / "prep.md").write_text(text, encoding="utf-8")
    notes = [f"# Call notes: {name}", f"{today.isoformat()}, with {contact or '[who]'}", "", "(Start time: ____   Planned length: 30 minutes. Talk about 40% of the time.)", "",
             "## Situation", "", "## Problem (in their words)", "", "## Cost (the number they gave, per month)", "", "## Result they want", "", "## Who decides, budget range, timing", "", "## Next step we agreed (with a date)", "",
             "## Scorecard areas to rate afterwards (0 to 2)"] + [f"- {a[1]}" for a in callscore.AREAS] + [""]
    (folder / "notes.md").write_text("\n".join(notes), encoding="utf-8")
    return f"{text}\nSaved: {folder.relative_to(ROOT).as_posix()}/prep.md and notes.md\n"


def after(slug: str, source: str, row_id: str, outcome: str, problem: str = "", cost_month: float = 0, price: float = 0, agreed: str = "", stop: bool = False,
          today: dt.date | None = None, name: str = "") -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    if outcome not in OUTCOMES:
        raise ValueError("Outcome is one of: " + ", ".join(OUTCOMES) + ".")
    row = find_row(slug, source, row_id)
    en = enrichment_for(slug, clean_domain(row.get("website", "")))
    biz = row.get("business") or row.get("name") or f"row {row_id}"
    contact = name or en.get("decision_maker") or row.get("contact_name") or ""
    first = (contact.split(" ")[0] if contact else "") or "there"
    sender = (cfg.get("sender_name") or "").strip() or "[your name]"
    problem, agreed = re.sub(r"\s+", " ", problem or "").strip(), re.sub(r"\s+", " ", agreed or "").strip()
    if cost_month < 0 or price < 0:
        raise ValueError("Cost and price cannot be negative.")
    folder = engine_dir(slug) / "calls" / f"{today.isoformat()}-{slugify(biz)}"
    folder.mkdir(parents=True, exist_ok=True)
    L = [f"# After the call: {biz}", "", f"Outcome: {outcome.replace('_', ' ')}", ""]
    notes = []
    if outcome == "no_show":
        L += ["## If appropriate, offer a reschedule", f"If they invited a reschedule message, you can send: Hi {first}, I had us down for a call today and missed you. No problem. If you would like to reschedule, here is my calendar{': ' + (cfg.get('calendar_url') or '') if cfg.get('calendar_url') else ' (or tell me a time that suits you)'}. {sender}", ""]
        L += [f"Log it: python dse.py callscore {slug} --offer \"{biz}\" --outcome no_show"]
    elif outcome == "no_sale":
        L += ["## Optional recap, if useful and welcome", f"Hi {first}, thank you for your time today. I will not follow up unless you ask me to" + (f" or as we agreed ({agreed})" if agreed else "") + f". {sender}", ""]
        L += [f"Log it: python dse.py callscore {slug} --offer \"{biz}\" --outcome no_sale --scores 1,1,1,1,1,1,1,1   (rate each area 0 to 2, honestly)"]
    else:
        L += ["## Optional recap to send only as agreed",
              f"Hi {first}, thank you for the time today. Here is what I heard: " + (f"{problem}. " if problem else "[the problem, in their words]. ") + (f"You said it costs about ${cost_month:,.0f} a month. " if cost_month else "[what they said it costs per month]. ")
              + f"What we agreed: " + (f"{agreed}" if agreed else "[the next step and its date]") + f". {sender}", ""]
        if outcome == "follow_up":
            L += ["## Your proposal, ready to fill", ("python dse.py proposal " + slug + f" --client \"{biz}\"" + (f" --contact {first}" if first != "there" else "") + f" --problem \"{problem or '[their problem in their own words]'}\" --offer \"[what you will do]\" "
                   + (f"--price {price:g} " if price else "--price [your price] ") + "--deliverables \"[a; b; c]\" --weeks [N]" + (f" --cost-month {cost_month:g}" if cost_month else "")), "", f"Log the call: python dse.py callscore {slug} --offer \"{biz}\" --outcome follow_up --scores ..."]
        else:
            L += ["## Next: they said yes", f"python dse.py callscore {slug} --offer \"{biz}\" --outcome sold --cash {price:g} --commission [your %] --scores ...", f"Then: python dse.py client won {slug} --proposal <the proposal you sent>"]
    missing = [m for m, v in (("the problem in their words", problem), ("what they said it costs per month", cost_month), ("the price", price if outcome in ("follow_up", "sold") else 1), ("the agreed next step", agreed)) if not v]
    if missing and outcome in ("follow_up", "sold"):
        L += ["", "## Not filled in yet (the message above has [brackets] where these go)", "- " + "\n- ".join(missing)]
    events = []
    if outcome in ("sold", "no_sale"):
        events.append({"logged_at": dl.local_now(), "list_date": row["_date"], "source": row["_source"], "row_id": row["_row_id"], "name": biz, "channel": row.get("channel", ""), "touch": row.get("touch", ""),
                       "status": "won" if outcome == "sold" else "lost", "category": "call", "reply": agreed[:200], "next_step": "", "value": f"{price:g}" if outcome == "sold" and price else ""})
    if events:
        dl.append_events(slug, events)
        notes.append(f"Recorded in your send log as {'won' if outcome == 'sold' else 'lost'}, so your results stay true.")
    if stop:
        em = en.get("best_email") or row.get("email") or ""
        added = replies.add_dnc(slug, em, "asked not to be contacted (after a call)", today) if em else False
        site = clean_domain(row.get("website", ""))
        added2 = replies.add_dnc(slug, site, "asked not to be contacted (after a call)", today) if site else False
        notes.append("Do-not-contact list: " + (", ".join(x for x, ok in ((em, added), (site, added2)) if ok) or "nothing new to add (no address known, or already listed)") + ".")
    if notes:
        L += [""] + [f"- {n}" for n in notes]
    L += ["", "Nothing was sent. You send the message yourself."]
    text = "\n".join(L) + "\n"
    (folder / "after.md").write_text(text, encoding="utf-8")
    return text


def attention(slug: str, today: dt.date) -> list[dict]:
    """Booked calls in the last 7 days with no prep sheet yet: [{name, source, row}]."""
    out = []
    hist = dl.history(slug)
    rows = {(r["_source"], r["_row_id"]): r for r in dl.load_lists(slug)}
    for key, ev in hist.items():
        r = rows.get(key)
        if not r or dl.status_of_row(hist, r) != "booked":
            continue
        b = next((e for e in reversed(ev) if e.get("status") == "booked"), None)
        if not b or str(b.get("logged_at", ""))[:10] < (today - dt.timedelta(days=7)).isoformat():
            continue
        name = r.get("business") or r.get("name") or key[1]
        calls = engine_dir(slug) / "calls"
        if not (calls.is_dir() and any(p.name.endswith("-" + slugify(name)) and (p / "prep.md").exists() for p in calls.iterdir())):
            out.append({"name": name, "source": key[0], "row": key[1]})
    return out
