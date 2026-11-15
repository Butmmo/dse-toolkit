"""The Proposal Builder: after a good call, a clear one-page proposal, a cover email and a follow-up, in your name, in a minute.

    python dse.py proposal <engine> --client "Acme Dental" --contact Dana --problem "patients cannot book online and call after hours" \\
        --cost-month 4000 --offer "Online booking that fills the calendar" --price 1500 --deliverables "Booking page; Reminder emails; Staff training" --weeks 3

Everything in the proposal comes from what you type. It never invents a result, a testimonial or a guarantee:
  * "What it costs you today" is shown only when you give --cost-month (what the problem costs them each month, from the call). The payback is that arithmetic and nothing more.
  * price, deposit, timeline and deliverables are yours. The weeks are split across your deliverables so the plan has dates.
  * with --options "Basic:800:2 pages;Standard:1500:5 pages;Premium:2800:10 pages" it shows a three-way comparison and recommends the middle one (a common way to
    keep the choice about which, not whether)
  * the cover email and the follow-up are short and plain. [Brackets] mark anything only you know; the report lists them so none goes out unfilled.
It saves engines/<slug>/proposals/<date>-<client>.md and a print-ready .html you can save as a PDF from any browser. It never sends anything.
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import math
import re
from pathlib import Path

from .engines import engine_dir, load

SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
BRACKET = re.compile(r"\[[^\]]{2,60}\]")


def clean(s: str, n: int = 200) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()[:n]


def money(x: float, sym: str) -> str:
    return f"{sym}{x:,.0f}" if abs(x - round(x)) < 0.005 else f"{sym}{x:,.2f}"


def parse_options(s: str) -> list[dict]:
    out = []
    for part in [p for p in (s or "").split(";") if p.strip()]:
        bits = [b.strip() for b in part.split(":")]
        if len(bits) < 2 or not re.fullmatch(r"\d+(\.\d+)?", bits[1].replace(",", "")):
            raise ValueError(f"Each option is Name:price or Name:price:what you get, separated by semicolons. I could not read: {part.strip()[:40]}")
        out.append({"name": clean(bits[0], 30), "price": float(bits[1].replace(",", "")), "note": clean(":".join(bits[2:]), 80)})
    if out and not 2 <= len(out) <= 4:
        raise ValueError("Give 2 to 4 options, or none.")
    return sorted(out, key=lambda o: o["price"])


def schedule(items: list[str], weeks: int, start: dt.date) -> list[tuple[str, str]]:
    """Spread the deliverables over the weeks, in order: [(when, what)]."""
    n = len(items)
    rows = []
    for i, it in enumerate(items):
        w1 = i * weeks // n + 1
        w2 = max(w1, (i + 1) * weeks // n)
        a = start + dt.timedelta(weeks=w1 - 1)
        b = start + dt.timedelta(weeks=w2) - dt.timedelta(days=3)
        rows.append((f"Week {w1}" + (f" to {w2}" if w2 > w1 else "") + f" ({a.strftime('%b %d').replace(' 0', ' ')} to {b.strftime('%b %d').replace(' 0', ' ')})", it))
    return rows


def next_monday(today: dt.date) -> dt.date:
    return today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)


def build_data(slug: str, client: str, contact: str, problem: str, offer: str, price: float, deliverables: str, weeks: int, cost_month: float = 0, options: str = "",
               deposit: int = 50, currency: str = "USD", excludes: str = "", start: str = "", today: dt.date | None = None, with_quotes: bool = False) -> dict:
    cfg = load(slug)
    today = today or dt.date.today()
    client, contact, problem, offer = clean(client, 80), clean(contact, 40), clean(problem, 300), clean(offer, 120)
    if len(client) < 2 or len(problem) < 8 or len(offer) < 4:
        raise ValueError("I need the client's name, the problem in their own words (at least a short sentence) and what you will do for them.")
    items = [clean(x, 100) for x in (deliverables or "").split(";") if clean(x)]
    if not 1 <= len(items) <= 12:
        raise ValueError("List 1 to 12 deliverables, separated by semicolons.")
    if not 1 <= weeks <= 26:
        raise ValueError("The timeline is 1 to 26 weeks.")
    if currency not in SYMBOLS:
        raise ValueError("Currency is USD, GBP or EUR.")
    if not 0 <= deposit <= 100:
        raise ValueError("The deposit is a percentage from 0 to 100.")
    opts = parse_options(options)
    if opts:
        price = opts[len(opts) // 2]["price"] if len(opts) > 2 else opts[0]["price"]
    if not 1 <= price <= 10_000_000:
        raise ValueError("Give the price (more than 0).")
    if cost_month < 0 or cost_month > 100_000_000:
        raise ValueError("The monthly cost of the problem must be a sensible number (or empty).")
    st = dt.date.fromisoformat(start) if start else next_monday(today)
    sender = (cfg.get("sender_name") or "").strip() or "[your name]"
    brand = (cfg.get("brand_name") or cfg.get("name") or "").strip()
    sym = SYMBOLS[currency]
    said = []
    if with_quotes:
        from . import proof          # only approved, consented quotes that agreed to proposals; their exact words, with the attribution THEY chose
        for q in proof.load_data(slug)["quotes"]:
            if not proof.usable_reason(q, "proposals"):
                said.append({"text": q.get("excerpt") or q["text"], "by": proof.attribution(q), "numbers": [c["text"] for c in proof.verified_claims(q)]})
        said = said[:2]
    d = {"quotes": said, "slug": slug, "client": client, "contact": contact, "problem": problem, "offer": offer, "price": price, "items": items, "weeks": weeks, "cost_month": cost_month, "options": opts,
         "deposit": deposit, "currency": currency, "sym": sym, "excludes": clean(excludes, 200), "start": st, "today": today, "valid": today + dt.timedelta(days=14), "sender": sender, "brand": brand,
         "calendar": (cfg.get("calendar_url") or cfg.get("calendar") or "").strip(), "notes": []}
    if cost_month:
        d["payback_months"] = price / cost_month
        d["year_cost"] = cost_month * 12
        if price > d["year_cost"]:
            d["notes"].append(f"Your price ({money(price, sym)}) is more than a full year of the problem ({money(d['year_cost'], sym)}). Check the cost figure with them, or the price, before you send.")
    else:
        d["notes"].append("No monthly cost was given, so the proposal has no 'what it costs you today' section. Ask them on your next call: 'What does that cost you each month?'")
    return d


def markdown(d: dict) -> str:
    s, sym = d["sender"], d["sym"]
    hi = d["contact"] or "there"
    L = [f"# Proposal for {d['client']}", "", f"Prepared for {d['contact'] or d['client']} by {s}" + (f", {d['brand']}" if d["brand"] else "") + f" on {d['today'].strftime('%B %d, %Y').replace(' 0', ' ')}. Valid until {d['valid'].strftime('%B %d, %Y').replace(' 0', ' ')}.", "",
         "## What you told me", d["problem"], ""]
    if d["cost_month"]:
        L += ["## What it costs you today", f"You estimated the problem costs about {money(d['cost_month'], sym)} a month. That is about {money(d['year_cost'], sym)} a year if nothing changes.", ""]
    L += ["## What I will do", d["offer"] + ".", "", "| When | What you get |", "|---|---|"]
    L += [f"| {w} | {it} |" for w, it in schedule(d["items"], d["weeks"], d["start"])]
    L += ["", f"Work starts {d['start'].strftime('%B %d').replace(' 0', ' ')} and takes {d['weeks']} week{'s' if d['weeks'] != 1 else ''}.", ""]
    if d.get("quotes"):
        L += ["## What clients say"]
        for q in d["quotes"]:
            L += [f"\"{q['text']}\"", f"{q['by']}" + (f" (numbers they confirmed or that match my records: {'; '.join(q['numbers'])})" if q["numbers"] else ""), ""]
    L += ["## Not included", (d["excludes"] or "[List what you will not do]") + " Anything not listed above is not included.", ""]
    L += ["## Investment"]
    if d["options"]:
        L += ["| Option | Price | What you get |", "|---|---|---|"]
        rec = d["options"][len(d["options"]) // 2]["name"] if len(d["options"]) > 2 else d["options"][0]["name"]
        L += [f"| {o['name']}{' (recommended)' if o['name'] == rec else ''} | {money(o['price'], sym)} | {o['note']} |" for o in d["options"]]
        L.append("")
    else:
        L += [f"{money(d['price'], sym)} for everything above.", ""]
    dep = d["price"] * d["deposit"] / 100
    L += [f"Payment: {d['deposit']}% ({money(dep, sym)}) to start, the balance ({money(d['price'] - dep, sym)}) when the work is delivered." if 0 < d["deposit"] < 100
          else ("Payment: in full when the work is delivered." if d["deposit"] == 0 else "Payment: in full to start."), ""]
    if d["cost_month"]:
        pb = d["payback_months"]
        L += [f"At the cost you described, the work pays for itself in about {pb:.1f} month{'s' if abs(pb - 1) > 0.05 else ''} if it removes the problem. That is arithmetic on your own figure, not a promise of results.", ""]
    L += ["## Next step", f"Reply \"yes\" to this message and I will send a short agreement and the first invoice." + (f" Or pick a time to talk it through: {d['calendar']}" if d["calendar"] else ""), "", f"{s}"]
    return "\n".join(L) + "\n"


def cover_email(d: dict) -> str:
    hi = d["contact"] or "there"
    cost = f" You mentioned it costs about {money(d['cost_month'], d['sym'])} a month, so I kept the plan short and the price clear." if d["cost_month"] else ""
    return (f"Subject: Your proposal: {d['offer']}\n\nHi {hi},\n\nThank you for your time on our call. As promised, the proposal is attached: what I heard, what I will do, when, and the price.{cost}\n\n"
            f"If it looks right, reply \"yes\" and I will send a short agreement. If anything is off, tell me what and I will change it. The proposal is valid until {d['valid'].strftime('%B %d').replace(' 0', ' ')}.\n\n{d['sender']}\n")


def follow_up(d: dict) -> str:
    hi = d["contact"] or "there"
    return (f"Send on {(d['today'] + dt.timedelta(days=3)).isoformat()} if there is no answer:\n\nHi {hi}, did you get a chance to look at the proposal? I am happy to answer any question or change anything. "
            f"If the timing is wrong, tell me when to check back and I will.\n\n{d['sender']}\n")


def html_page(d: dict, md: str) -> str:
    body, in_table = [], False
    for ln in md.splitlines():
        if ln.startswith("# "):
            body.append(f"<h1>{htmllib.escape(ln[2:])}</h1>")
        elif ln.startswith("## "):
            body.append(f"<h2>{htmllib.escape(ln[3:])}</h2>")
        elif ln.startswith("|---"):
            continue
        elif ln.startswith("|"):
            cells = [htmllib.escape(c.strip()) for c in ln.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                body.append("<table>")
                in_table = True
            body.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        else:
            if in_table:
                body.append("</table>")
                in_table = False
            if ln.strip():
                body.append(f"<p>{htmllib.escape(ln)}</p>")
    if in_table:
        body.append("</table>")
    css = ("body{font:16px/1.55 Georgia,serif;max-width:720px;margin:40px auto;padding:0 20px;color:#222}h1{font-size:28px;margin-bottom:4px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
           "table{border-collapse:collapse;width:100%;margin:10px 0}th,td{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}th{background:#f4f1ea}@media print{body{margin:0}}")
    return f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Proposal for {htmllib.escape(d['client'])}</title><style>{css}</style></head><body>" + "\n".join(body) + "</body></html>"


def report(slug: str, client: str, contact: str, problem: str, offer: str, price: float, deliverables: str, weeks: int, cost_month: float = 0, options: str = "", deposit: int = 50,
           currency: str = "USD", excludes: str = "", start: str = "", today: dt.date | None = None, with_quotes: bool = False) -> str:
    d = build_data(slug, client, contact, problem, offer, price, deliverables, weeks, cost_month, options, deposit, currency, excludes, start, today, with_quotes)
    md, mail, fu = markdown(d), cover_email(d), follow_up(d)
    folder = engine_dir(slug) / "proposals"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{d['today'].isoformat()}-{re.sub(r'[^a-z0-9]+', '-', d['client'].lower()).strip('-')[:40]}"
    (folder / f"{stem}.md").write_text(md + "\n---\nCover email\n\n" + mail + "\n---\nFollow-up\n\n" + fu, encoding="utf-8")
    (folder / f"{stem}.html").write_text(html_page(d, md), encoding="utf-8")
    (folder / f"{stem}.json").write_text(json.dumps({"client": d["client"], "contact": d["contact"], "problem": d["problem"], "offer": d["offer"], "price": d["price"], "currency": d["currency"],
                                                     "deposit": d["deposit"], "start": d["start"].isoformat(), "weeks": d["weeks"], "items": d["items"], "cost_month": d["cost_month"],
                                                     "created": d["today"].isoformat(), "stem": stem}, indent=1), encoding="utf-8")
    brackets = sorted(set(BRACKET.findall(md + mail + fu)))
    out = [f"# Proposal saved: {d['client']}", "", f"engines/{slug}/proposals/{stem}.md  (text, with the cover email and the follow-up)", f"engines/{slug}/proposals/{stem}.html  (open in a browser, then Print > Save as PDF)", "", md.rstrip(), "",
           "## Cover email", mail.rstrip(), "", "## Follow-up", fu.rstrip(), ""]
    if brackets:
        out += ["## Before you send", "Fill these in yourself (I cannot know them): " + "; ".join(brackets)]
    for n in d["notes"]:
        out.append("Note: " + n)
    out.append("Nothing was sent. You send it yourself.")
    return "\n".join(out) + "\n"
