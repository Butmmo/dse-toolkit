"""The Call Desk: prepare for a booked call and document an agreed next step afterward.

    python dse.py call prep <engine> --source 2026-11-09 --row 7          a one-page brief for that lead (and a notes sheet)
    python dse.py call after <engine> --source 2026-11-09 --row 7 --outcome follow_up|sold|no_sale|no_show [--problem "..."] [--cost-month 4000] [--price 1500] [--agreed "..."] [--stop]

prep builds engines/<engine>/calls/<date>-<lead>/prep.md and notes.md from YOUR records only: the lead's row on your send list, the message you sent, the reply they wrote (in their
words), what the website check or the enrichment found, and what you need in hand before you speak. Every fact names where it came from. Where something is not known it says "not found"
and where to look: nothing about the lead is ever invented. The question plan follows the same participant-respecting behaviors as your call scorecard.

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
    L += ["## Who", f"- {name}" + (f", {row['city']}" if row.get("city") else "") + (f", {row['website']}" if row.get("website") else ""), f"- Contact in your records: {contact or 'not specified'}"]
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
    L += ["", "## Relevant, sourced context (use only what helps this conversation)"]
    for fct, src in facts[:3]:
        L.append(f"- {fct} ({src})")
    if not facts:
        L.append("- No relevant verified facts found. It is fine to begin with an open question; do not invent details or gather extra personal information just to fill a quota.")
    if facts[3:]:
        L += ["", "Also known: " + "; ".join(f"{f} ({s})" for f, s in facts[3:6])]
    L += ["", "## Flexible conversation plan (skip anything irrelevant; the other person can decline any question)", "",
          "1. Context: \"What would be useful for us to cover today?\" Let them set or correct the agenda."]
    gap = (row.get("gap_used") or "").strip().rstrip(".")
    L.append("2. Understand: " + (f"If useful, check the public observation \"{gap}\" as a question, not a diagnosis. Ask what they have noticed and listen without steering toward a problem." if gap else "Ask an open question about the situation they chose to discuss. Do not assume there is a problem."))
    L += ["3. Impact (optional): ask whether they want to explore practical impact. Do not request sensitive financial details, insist on a number, or use fear about what might happen.",
          "4. Fit: explain relevant requirements, limitations, evidence and known costs accurately. Ask about constraints only when needed and with permission; uncertainty is a valid answer.",
          "5. Close: summarize what you heard and ask whether they want any next step, including no further action. Follow up only as agreed.", ""]
    L += ["## Open with a shared agenda and permission",
          "\"Thanks for making time. Is this still a good time, and what would be useful to cover? I can ask a few questions, then explain what I know and what I cannot confirm. You can skip anything or stop at any point. We do not need to decide anything today. Does that sound okay?\"", ""]
    L += ["## In hand before you speak", "- [ ] Accurate details about the offer, scope, eligibility, known costs and limitations relevant to this call; say when anything is not yet confirmed",
          "- [ ] A notes sheet open: " + str((folder / "notes.md").relative_to(ROOT).as_posix()) + (f"\n- Your calendar link, if scheduling another conversation was requested: {cal}" if cal else "")]
    if unknown:
        L += ["", "## Not known (do not pretend otherwise)"] + [f"- {u}" for u in unknown]
    L += ["", "## When it ends", f"python dse.py call after {slug} --source {source} --row {row_id} --outcome follow_up --problem \"...\" --price N", "Use --cost-month only for an impact estimate they volunteered and agreed you may record. Nothing was sent."]
    text = "\n".join(L) + "\n"
    (folder / "prep.md").write_text(text, encoding="utf-8")
    notes = [f"# Call notes: {name}", f"{today.isoformat()}, with {contact or '[who]'}", "", "(Start time: ____   Planned length: ____   Topics they chose: ____)", "",
             "## Shared agenda and permission", "", "## Context and what they chose to discuss", "", "## Impact (only if they wanted to discuss it)", "", "## Fit, evidence, limitations and known costs", "", "## Questions or corrections", "", "## Next step they chose (or none)", "",
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
              f"Hi {first}, thank you for the time today. Here is what I heard: " + (f"{problem}. " if problem else "[brief summary, if useful]. ") + (f"You estimated the impact at about ${cost_month:,.0f} a month. " if cost_month else "")
              + f"What we agreed: " + (f"{agreed}" if agreed else "[the next step and its date]") + f". {sender}", ""]
        if outcome == "follow_up":
            L += ["## Your proposal, ready to fill", ("python dse.py proposal " + slug + f" --client \"{biz}\"" + (f" --contact {first}" if first != "there" else "") + f" --problem \"{problem or '[their problem in their own words]'}\" --offer \"[what you will do]\" "
                   + (f"--price {price:g} " if price else "--price [your price] ") + "--deliverables \"[a; b; c]\" --weeks [N]" + (f" --cost-month {cost_month:g}" if cost_month else "")), "", f"Log the call: python dse.py callscore {slug} --offer \"{biz}\" --outcome follow_up --scores ..."]
        else:
            L += ["## Next: they said yes", f"python dse.py callscore {slug} --offer \"{biz}\" --outcome sold --cash {price:g} --commission [your %] --scores ...", f"Then: python dse.py client won {slug} --proposal <the proposal you sent>"]
    missing = [m for m, v in (("a brief summary, if useful", problem), ("the price", price if outcome in ("follow_up", "sold") else 1), ("the agreed next step", agreed)) if not v]
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
