"""The Proposal Builder: after a good call, a clear one-page proposal, a cover email and a follow-up, in your name, in a minute.

    python dse.py proposal <engine> --client "Acme Dental" --contact Dana --problem "patients cannot book online and call after hours" \\
        --cost-month 4000 --offer "Online booking that fills the calendar" --price 1500 --deliverables "Booking page; Reminder emails; Staff training" --weeks 3

Everything in the proposal comes from what you type. It never invents a result, a testimonial or a guarantee:
  * an optional impact estimate appears only when the person volunteered it and agreed it may be recorded; annualized arithmetic is not a savings or payback forecast
  * price, agreed payment terms, proposed timing and deliverables are yours. The weeks are split across deliverables as a draft schedule to confirm together.
  * with --options "Basic:800:2 pages;Standard:1500:5 pages;Premium:2800:10 pages" it presents a comparison without choosing for the client; the client selects an option when they accept
  * the cover email and the follow-up are short and plain. [Brackets] mark anything only you know; the report lists them so none goes out unfilled.
There is no default expiry or follow-up date. Follow up only when requested or mutually agreed. It saves engines/<slug>/proposals/<date>-<client>.md and a print-ready .html you can save as a PDF from any browser. It never sends anything. This is a service-project tool, not a job or commission proposal.
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
               deposit: int | None = None, currency: str = "USD", excludes: str = "", start: str = "", today: dt.date | None = None, with_quotes: bool = False) -> dict:
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
    currency = (currency or "USD").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Currency is a 3-letter code such as USD, GBP, EUR, NGN or CAD.")
    if deposit is not None and not 0 <= deposit <= 100:
        raise ValueError("The deposit is a percentage from 0 to 100.")
    opts = parse_options(options)
    if opts and price:
        raise ValueError("With options, leave the single price at 0. The client chooses an option; record it when converting an accepted proposal.")
    if not opts and not 1 <= price <= 10_000_000:
        raise ValueError("Give a price greater than 0, or provide two to four options.")
    if cost_month < 0 or cost_month > 100_000_000:
        raise ValueError("The monthly cost of the problem must be a sensible number (or empty).")
    st = dt.date.fromisoformat(start) if start else next_monday(today)
    sender = (cfg.get("sender_name") or "").strip() or "[your name]"
    brand = (cfg.get("brand_name") or cfg.get("name") or "").strip()
    sym = SYMBOLS.get(currency, currency + " ")          # a currency of your own shows its code: NGN 1,500
    said = []
    if with_quotes:
        from . import proof          # only approved, consented quotes that agreed to proposals; their exact words, with the attribution THEY chose
        for q in proof.load_data(slug)["quotes"]:
            if not proof.usable_reason(q, "proposals"):
                said.append({"text": q.get("excerpt") or q["text"], "by": proof.attribution(q), "numbers": [c["text"] for c in proof.verified_claims(q)]})
        said = said[:2]
    d = {"quotes": said, "slug": slug, "client": client, "contact": contact, "problem": problem, "offer": offer, "price": price if price else None, "items": items, "weeks": weeks, "cost_month": cost_month, "options": opts,
         "deposit": deposit, "currency": currency, "sym": sym, "excludes": clean(excludes, 200), "start": st, "today": today, "sender": sender, "brand": brand,
         "calendar": (cfg.get("calendar_url") or cfg.get("calendar") or "").strip(), "notes": []}
    if cost_month:
        d["year_cost"] = cost_month * 12
    else:
        d["notes"].append("No optional impact estimate was provided; the proposal omits impact arithmetic. Do not request financial details unless they are relevant and the person is comfortable sharing them.")
    return d


def markdown(d: dict) -> str:
    s, sym = d["sender"], d["sym"]
    hi = d["contact"] or "there"
    L = [f"# Proposal for {d['client']}", "", f"Prepared for {d['contact'] or d['client']} by {s}" + (f", {d['brand']}" if d["brand"] else "") + f" on {d['today'].strftime('%B %d, %Y').replace(' 0', ' ')}.", "",
         "## What you told me", d["problem"], ""]
    if d["cost_month"]:
        L += ["## Optional impact estimate you shared", f"You estimated the impact at about {money(d['cost_month'], sym)} a month. If it stayed constant, that would be {money(d['year_cost'], sym)} over a year. This is your estimate, not verified savings or a result forecast.", ""]
    L += ["## Proposed work", d["offer"] + ".", "", "| Proposed timing | What you get |", "|---|---|"]
    L += [f"| {w} | {it} |" for w, it in schedule(d["items"], d["weeks"], d["start"])]
    L += ["", f"Proposed start date: {d['start'].strftime('%B %d').replace(' 0', ' ')} (confirm together). Estimated delivery period: {d['weeks']} week{'s' if d['weeks'] != 1 else ''}, subject to the agreed scope and dependencies.", ""]
    if d.get("quotes"):
        L += ["## What clients say"]
        for q in d["quotes"]:
            L += [f"\"{q['text']}\"", f"{q['by']}" + (f" (numbers they confirmed or that match my records: {'; '.join(q['numbers'])})" if q["numbers"] else ""), ""]
    L += ["## Not included", (d["excludes"] or "[List what you will not do]") + " Anything not listed above is not included.", ""]
    L += ["## Price and payment terms"]
    if d["options"]:
        L += ["| Option | Price | What you get |", "|---|---|---|"]
        L += [f"| {o['name']} | {money(o['price'], sym)} | {o['note']} |" for o in d["options"]]
        L.append("")
    else:
        L += [f"{money(d['price'], sym)} for everything above.", ""]
    if d["deposit"] is None:
        L += ["Payment schedule: [Agree and record payment milestones before work starts].", ""]
    elif d["options"]:
        L += [f"Payment schedule: {d['deposit']}% at the agreed start milestone, with the balance at the agreed completion milestone. Confirm the schedule in writing for the option selected.", ""]
    else:
        dep = d["price"] * d["deposit"] / 100
        L += [f"Payment schedule: {d['deposit']}% ({money(dep, sym)}) at the agreed start milestone, with the balance ({money(d['price'] - dep, sym)}) at the agreed completion milestone." if 0 < d["deposit"] < 100
              else ("Payment schedule: full payment at the agreed completion milestone." if d["deposit"] == 0 else "Payment schedule: full payment at the agreed start milestone."), ""]
    if d["cost_month"]:
        L += [f"The annualized figure is simple arithmetic from your estimate ({money(d['cost_month'], sym)} × 12). It assumes the estimate stays constant and is not a forecast of savings, results, or payback.", ""]
    L += ["## Next step", "Review the scope, timing, price, exclusions, and payment schedule. If you want to proceed, tell me which option you prefer (if options are shown) and what needs clarification. We can confirm the agreement and payment milestones together before work starts. You may request changes, take time, or decline. No action is required if this is not a fit." + (f" If you would like to discuss it, you can choose a time: {d['calendar']}" if d["calendar"] else ""), "", f"{s}"]
    return "\n".join(L) + "\n"


def cover_email(d: dict) -> str:
    hi = d["contact"] or "there"
    cost = f" The optional impact estimate you shared is shown as arithmetic only; it is not a result or savings promise." if d["cost_month"] else ""
    return (f"Subject: Proposal for your review: {d['offer']}\n\nHi {hi},\n\nThank you for the conversation. I have attached the proposed scope, timing, price, and exclusions.{cost}\n\n"
            f"Please review it when convenient. You can ask for changes, more time, or decide not to proceed. I will follow up only if you asked me to or we agreed a check-in.\n\n{d['sender']}\n")


def follow_up(d: dict) -> str:
    hi = d["contact"] or "there"
    return ("Optional follow-up draft. Send only if they requested it or you agreed on a check-in date and channel. If no check-in was agreed, do not send.\n\n"
            f"Hi {hi}, I am following up as we agreed. Would you like any clarification or changes to the proposal? If you have decided not to proceed, I will respect that and close this out.\n\n{d['sender']}\n")


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


def report(slug: str, client: str, contact: str, problem: str, offer: str, price: float, deliverables: str, weeks: int, cost_month: float = 0, options: str = "", deposit: int | None = None,
           currency: str = "USD", excludes: str = "", start: str = "", today: dt.date | None = None, with_quotes: bool = False) -> str:
    d = build_data(slug, client, contact, problem, offer, price, deliverables, weeks, cost_month, options, deposit, currency, excludes, start, today, with_quotes)
    md, mail, fu = markdown(d), cover_email(d), follow_up(d)
    folder = engine_dir(slug) / "proposals"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{d['today'].isoformat()}-{re.sub(r'[^a-z0-9]+', '-', d['client'].lower()).strip('-')[:40]}"
    (folder / f"{stem}.md").write_text(md + "\n---\nCover email\n\n" + mail + "\n---\nFollow-up\n\n" + fu, encoding="utf-8")
    (folder / f"{stem}.html").write_text(html_page(d, md), encoding="utf-8")
    (folder / f"{stem}.json").write_text(json.dumps({"client": d["client"], "contact": d["contact"], "problem": d["problem"], "offer": d["offer"], "price": d["price"], "options": d["options"], "currency": d["currency"],
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
