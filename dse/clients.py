"""The Client Desk: from "yes" to paid. Onboarding, invoices, delivery and payments for each client, in one place.

    python dse.py client won <engine> --proposal 2026-11-14-acme-dental [--email dana@acme.com] [--address "1 Main St, Tampa FL"]
    python dse.py client list <engine>
    python dse.py client show <engine>/<client>
    python dse.py client done <engine>/<client> --item "Booking page" [--date 2026-11-20]      tick a deliverable or an onboarding task
    python dse.py client invoice <engine>/<client> --kind final|extra [--amount 200 --note "extra page"] [--terms 7]
    python dse.py client paid <engine>/<client> --invoice INV-2026-001 [--amount 750] [--date 2026-11-18]

(<engine>/<client> can also be the path to the client's client.json, which is what the Citadel pickers give.)

What it does, with nothing invented and nothing sent:
  won      turns a saved proposal (engines/<engine>/proposals/<name>.json, written by the Proposal Builder) into a client: price, deposit, timeline and deliverables carry over.
           It writes onboarding.md (a dated checklist, a welcome message in your name, a short agreement outline) and the deposit invoice.
  done     ticks off a deliverable. The proposal's dates make late work visible in the Weekly Review.
  invoice  the final invoice (the balance of the price) or an extra one. Invoices are print-ready pages you send yourself.
  paid     records a payment against an invoice AND adds it to the Cash Desk (cash.csv), so "received" stays true without typing it twice.
Files: engines/<engine>/clients/<client>/client.json, onboarding.md, invoices/INV-<year>-<n>.html.
Payment details never go in a file that syncs: put them in engines/<engine>/payment-details.txt on this PC and the invoices will use them.
Not legal advice: the agreement outline is a starting point to have checked before you rely on it.
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re
from pathlib import Path

from . import cashdesk
from .common import ROOT
from .engines import engine_dir, load

SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
TOL = 0.005


def clients_dir(slug: str) -> Path:
    return engine_dir(slug) / "clients"


def money(x: float, sym: str = "$") -> str:
    return f"{sym}{x:,.0f}" if abs(x - round(x)) < TOL else f"{sym}{x:,.2f}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40]


def parse_date(s: str, today: dt.date) -> dt.date:
    if not s:
        return today
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError("Dates are YYYY-MM-DD.")
    return dt.date.fromisoformat(s)


# ------------------------------------------------------------------ storage

def resolve(target: str) -> Path:
    """The client.json for 'engine/client' or a path to client.json."""
    t = (target or "").replace("\\", "/").strip()
    p = Path(t)
    if not p.is_absolute():
        p = ROOT / t
    if p.name == "client.json" and p.is_file():
        if ROOT.resolve() not in p.resolve().parents:
            raise ValueError("That client file is outside this toolkit.")
        return p
    m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_-]{0,59})/([a-z0-9-]{1,40})", t)
    if m:
        f = clients_dir(m.group(1)) / m.group(2) / "client.json"
        if f.is_file():
            return f
        have = ", ".join(sorted(x.name for x in clients_dir(m.group(1)).iterdir() if x.is_dir())) if clients_dir(m.group(1)).is_dir() else "none yet"
        raise ValueError(f"No client '{m.group(2)}' in engine {m.group(1)}. Clients: {have}.")
    raise ValueError("Name the client as engine/client-name (for example my-engine/acme-dental).")


def load_client(target: str) -> tuple[Path, dict]:
    f = resolve(target)
    return f, json.loads(f.read_text(encoding="utf-8"))


def save(f: Path, c: dict) -> None:
    f.write_text(json.dumps(c, indent=1), encoding="utf-8")


def all_clients(slug: str) -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(clients_dir(slug).glob("*/client.json")) if clients_dir(slug).is_dir() else []:
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ money maths

def paid_total(inv: dict) -> float:
    return round(sum(p["amount"] for p in inv.get("payments", [])), 2)


def outstanding(inv: dict) -> float:
    return round(inv["amount"] - paid_total(inv), 2)


def invoiced(c: dict, kinds=("deposit", "full", "final")) -> float:
    return round(sum(i["amount"] for i in c["invoices"] if i["kind"] in kinds), 2)


def status(c: dict) -> str:
    items = c["items"]
    done = all(i.get("done_on") for i in items)
    all_paid = bool(c["invoices"]) and all(outstanding(i) <= TOL for i in c["invoices"]) and invoiced(c) + TOL >= c["price"]
    if done and all_paid:
        return "closed"
    if done:
        return "delivered"
    if any(i.get("done_on") for i in items) or all(t.get("done_on") for t in c["onboarding"]):
        return "active"
    return "onboarding"


def next_invoice_id(slug: str, today: dt.date) -> str:
    n = 0
    for _f, c in all_clients(slug):
        for i in c["invoices"]:
            m = re.fullmatch(rf"INV-{today.year}-(\d+)", i["id"])
            if m:
                n = max(n, int(m.group(1)))
    return f"INV-{today.year}-{n + 1:03d}"


# ------------------------------------------------------------------ pages

def payment_details(slug: str) -> str:
    p = engine_dir(slug) / "payment-details.txt"
    return p.read_text(encoding="utf-8", errors="replace").strip()[:600] if p.exists() else ""


def invoice_html(slug: str, c: dict, inv: dict) -> str:
    cfg = load(slug)
    sym = c["sym"]
    e = htmllib.escape
    frm = "<br>".join(e(x) for x in (cfg.get("sender_name") or "[your name]", cfg.get("brand_name") or "", cfg.get("postal_address") or "[your postal address]") if x)
    to = "<br>".join(e(x) for x in (c["client"], c.get("contact") or "", c.get("email") or "", c.get("address") or "") if x)
    pay = payment_details(slug)
    pay_html = e(pay).replace("\n", "<br>") if pay else "[Add your payment details: put them in engines/" + e(slug) + "/payment-details.txt on your PC]"
    paid = paid_total(inv)
    css = ("body{font:15px/1.5 Georgia,serif;max-width:720px;margin:40px auto;padding:0 20px;color:#222}h1{font-size:26px}table{border-collapse:collapse;width:100%;margin:16px 0}"
           "th,td{border-bottom:1px solid #ccc;padding:8px;text-align:left}.r{text-align:right}.box{display:flex;gap:40px}.box div{flex:1}@media print{body{margin:0}}")
    rows = f"<tr><td>{e(inv['note'])}</td><td class='r'>{e(money(inv['amount'], sym))}</td></tr>"
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{e(inv['id'])}</title><style>{css}</style></head><body>"
            f"<h1>Invoice {e(inv['id'])}</h1><p>Issued {e(inv['issued'])}. Due {e(inv['due'])}.</p>"
            f"<div class='box'><div><b>From</b><br>{frm}</div><div><b>To</b><br>{to}</div></div>"
            f"<table><tr><th>Description</th><th class='r'>Amount</th></tr>{rows}"
            f"<tr><td><b>Total due</b></td><td class='r'><b>{e(money(inv['amount'] - paid, sym))}</b></td></tr></table>"
            f"<p><b>How to pay</b><br>{pay_html}</p><p>Thank you for your business.</p></body></html>")


def onboarding_md(slug: str, c: dict, today: dt.date) -> str:
    cfg = load(slug)
    sender = (cfg.get("sender_name") or "[your name]")
    start = dt.date.fromisoformat(c["start"])
    sym = c["sym"]
    L = [f"# Onboarding: {c['client']}", "", f"Project: {c['offer']}. Starts {start.strftime('%B %d').replace(' 0', ' ')}, {c['weeks']} week{'s' if c['weeks'] != 1 else ''}.", "",
         "## Checklist (tick with: python dse.py client done " + f"{slug}/{c['slug']} --item \"...\")", ""]
    L += [f"- [ ] {t['task']} (by {t['by']})" for t in c["onboarding"]]
    L += ["", "## Delivery plan", ""] + [f"- [ ] {i['name']} (due {i['due']})" for i in c["items"]]
    L += ["", "## Welcome message (you send it yourself)", "",
          f"Hi {c.get('contact') or 'there'},", "",
          f"Welcome aboard, and thank you for trusting me with {c['offer'].rstrip('.').lower() if c['offer'] else 'this project'}. Here is how we will work:", "",
          f"1. I will send the agreement and the first invoice ({money(c['price'] * c['deposit_pct'] / 100, sym)} to start) now. Work begins {start.strftime('%B %d').replace(' 0', ' ')}, once both are done.",
          "2. To begin I need: " + "; ".join(t["task"].lower() for t in c["onboarding"][2:5]) + ".",
          "3. Please never send passwords by email. Share access through your own password manager or tell me and I will give you a safe way.",
          "4. Send feedback in one list per milestone, so nothing gets lost. I reply within one working day.", "", sender, "",
          "## Short agreement outline (a starting point, not legal advice: have it checked before you rely on it)", "",
          f"- Parties: {sender} and {c['client']}.", f"- What I will do: {c['offer']}. Deliverables: " + "; ".join(i["name"] for i in c["items"]) + ".",
          f"- Timeline: {c['weeks']} week(s) from {start.isoformat()}, if I get what I need from you on time.",
          f"- Price: {money(c['price'], sym)}. {c['deposit_pct']}% to start, the balance on delivery. Late payment: [your late-payment terms].",
          "- Changes: one round of changes per milestone is included. Anything else is quoted before I do it.",
          "- Not included: anything not listed above.", "- Ownership: the finished work is yours when it is paid for in full.",
          "- Ending early: either side can stop with written notice; work done so far is paid for.", "- Confidentiality: I keep your business information private.", ""]
    return "\n".join(L)


ONBOARD = [("Send the agreement and the first invoice", -3), ("Agreement signed and deposit received", -1), ("Get the main contact and who decides", -1), ("Get access to what I need (through their own password manager)", -1),
           ("Collect their content: logo, text, photos, examples they like", 0), ("Book the kickoff call", -2), ("Agree how and how fast we reply to each other", -2)]


def items_with_dates(items: list[str], weeks: int, start: dt.date) -> list[dict]:
    n = len(items)
    out = []
    for i, name in enumerate(items):
        w2 = max(i * weeks // n + 1, (i + 1) * weeks // n)
        out.append({"name": name, "due": (start + dt.timedelta(weeks=w2) - dt.timedelta(days=3)).isoformat(), "done_on": ""})
    return out


# ------------------------------------------------------------------ actions

def won(slug: str, proposal: str, email: str = "", address: str = "", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    prop_dir = (engine_dir(slug) / "proposals").resolve()
    if (proposal or "").endswith(".json"):
        cand = Path(proposal) if Path(proposal).is_absolute() else ROOT / proposal
    else:
        cand = prop_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '', proposal or '')}.json"
    name = cand.stem
    if cand.is_file() and prop_dir not in cand.resolve().parents:
        raise ValueError("A proposal must be one saved in this engine's proposals folder.")
    if not cand.is_file():
        have = ", ".join(sorted(p.stem for p in (engine_dir(slug) / "proposals").glob("*.json"))) if (engine_dir(slug) / "proposals").is_dir() else "none yet"
        raise ValueError(f"No saved proposal '{proposal}'. Proposals with data: {have}. Make one with: python dse.py proposal {slug} ...")
    pr = json.loads(cand.read_text(encoding="utf-8"))
    cslug = slugify(pr["client"])
    folder = clients_dir(slug) / cslug
    if (folder / "client.json").exists():
        raise ValueError(f"{pr['client']} is already a client of this engine. Use: python dse.py client show {slug}/{cslug}")
    if email and not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        raise ValueError("That email address does not look right.")
    start = dt.date.fromisoformat(pr["start"])
    start = max(start, today) if start < today else start
    c = {"slug": cslug, "client": pr["client"], "contact": pr.get("contact", ""), "email": email, "address": re.sub(r"\s+", " ", address or "").strip()[:200], "engine": slug, "offer": pr["offer"],
         "problem": pr.get("problem", ""), "currency": pr["currency"], "sym": SYMBOLS.get(pr["currency"], "$"), "price": float(pr["price"]), "deposit_pct": int(pr["deposit"]), "start": start.isoformat(),
         "weeks": int(pr["weeks"]), "created": today.isoformat(), "proposal": pr.get("stem", name), "items": items_with_dates(pr["items"], int(pr["weeks"]), start), "invoices": [], "onboarding": []}
    c["onboarding"] = [{"task": t, "by": (start + dt.timedelta(days=d)).isoformat(), "done_on": ""} for t, d in ONBOARD]
    notes = []
    if c["deposit_pct"] > 0:
        amt = round(c["price"] * c["deposit_pct"] / 100, 2)
        kind = "full" if c["deposit_pct"] == 100 else "deposit"
        inv = {"id": next_invoice_id(slug, today), "kind": kind, "amount": amt, "issued": today.isoformat(), "due": today.isoformat(),
               "note": f"{'Payment in full' if kind == 'full' else str(c['deposit_pct']) + '% deposit'}: {c['offer']}", "payments": []}
        c["invoices"].append(inv)
        (folder / "invoices").mkdir(parents=True, exist_ok=True)
        (folder / "invoices" / f"{inv['id']}.html").write_text(invoice_html(slug, c, inv), encoding="utf-8")
        notes.append(f"Deposit invoice {inv['id']} for {money(amt, c['sym'])} (print-ready page in clients/{cslug}/invoices/).")
    else:
        notes.append("No deposit: the final invoice is issued when the work is delivered (python dse.py client invoice ... --kind final).")
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / "client.json", c)
    (folder / "onboarding.md").write_text(onboarding_md(slug, c, today), encoding="utf-8")
    if not payment_details(slug):
        notes.append(f"No payment details yet: put them in engines/{slug}/payment-details.txt on this PC (kept off Citadel and Git) and re-issue, or add them to the invoice by hand.")
    if c["currency"] != "USD":
        notes.append(f"The Cash Desk adds amounts as they are and does not convert {c['currency']}.")
    return (f"# Client Desk: {c['client']} is now a client\n\n" + "\n".join(f"- {n}" for n in notes) + f"\n- Onboarding checklist, welcome message and agreement outline: clients/{cslug}/onboarding.md\n"
            f"- {len(c['items'])} deliverable(s) with due dates, {c['weeks']} week(s) from {c['start']}\n\nNothing was sent. Send the welcome message, the agreement and the invoice yourself.\n")


def show(target: str, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    f, c = load_client(target)
    sym = c["sym"]
    L = [f"# {c['client']}: {status(c)}", "", f"{c['offer']}. {money(c['price'], sym)}; {c['deposit_pct']}% deposit; starts {c['start']}, {c['weeks']} week(s).", "", "## Onboarding"]
    L += [f"- [{'x' if t['done_on'] else ' '}] {t['task']} (by {t['by']})" + (" LATE" if not t["done_on"] and t["by"] < today.isoformat() else "") for t in c["onboarding"]]
    L += ["", "## Delivery"] + [f"- [{'x' if i['done_on'] else ' '}] {i['name']} (due {i['due']})" + (f", done {i['done_on']}" if i["done_on"] else " LATE" if i["due"] < today.isoformat() else "") for i in c["items"]]
    L += ["", "## Invoices"]
    for i in c["invoices"]:
        o = outstanding(i)
        L.append(f"- {i['id']} {i['kind']}: {money(i['amount'], sym)}, due {i['due']}, " + ("PAID" if o <= TOL else f"{money(o, sym)} outstanding" + (" OVERDUE" if i["due"] < today.isoformat() else "")))
    if not c["invoices"]:
        L.append("- none yet")
    left = round(c["price"] - invoiced(c), 2)
    if left > TOL:
        L.append(f"- Not yet invoiced: {money(left, sym)} of the price.")
    return "\n".join(L) + "\n"


def listing(slug: str, today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    cl = all_clients(slug)
    if not cl:
        return "No clients yet. When a proposal is accepted: python dse.py client won " + slug + " --proposal <name>\n"
    L = [f"{'Client':<28}{'Status':<12}{'Price':>10}{'Paid':>10}{'Owed now':>10}  Next"]
    for f, c in cl:
        paid = round(sum(paid_total(i) for i in c["invoices"]), 2)
        owed = round(sum(outstanding(i) for i in c["invoices"] if i["due"] <= today.isoformat()), 2)
        nxt = next((f"{i['name']} (due {i['due']})" for i in c["items"] if not i["done_on"]), "all delivered")
        L.append(f"{c['client'][:27]:<28}{status(c):<12}{money(c['price'], c['sym']):>10}{money(paid, c['sym']):>10}{money(owed, c['sym']):>10}  {nxt}")
    return "\n".join(L) + "\n"


def done(target: str, item: str, date: str = "", today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    f, c = load_client(target)
    when = parse_date(date, today).isoformat()
    needle = (item or "").strip().lower()
    if len(needle) < 3:
        raise ValueError("Say which deliverable or task (a few words of its name).")
    pool = [("deliverable", i) for i in c["items"]] + [("onboarding task", t) for t in c["onboarding"]]
    hits = [(k, x) for k, x in pool if needle in (x.get("name") or x.get("task", "")).lower()]
    if not hits:
        raise ValueError("No deliverable or task matches '" + item + "'. See them with: python dse.py client show " + target)
    if len(hits) > 1:
        raise ValueError("That matches more than one: " + "; ".join(x.get("name") or x.get("task") for _k, x in hits) + ". Use more of the name.")
    kind, x = hits[0]
    before = status(c)
    x["done_on"] = when
    save(f, c)
    out = f"Ticked off the {kind}: {x.get('name') or x.get('task')} ({when}). Status: {status(c)}."
    if kind == "deliverable" and all(i["done_on"] for i in c["items"]) and before != "delivered":
        left = round(c["price"] - invoiced(c), 2)
        out += f"\nEverything is delivered. " + (f"Issue the final invoice for {money(left, c['sym'])}: python dse.py client invoice {target} --kind final" if left > TOL else "The price is already fully invoiced.")
    return out + "\n"


def invoice(target: str, kind: str = "final", amount: float = 0, note: str = "", terms: int = 7, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    f, c = load_client(target)
    slug = c["engine"]
    if kind not in ("final", "extra"):
        raise ValueError("Kind is final (the balance) or extra (something added).")
    if not 0 <= terms <= 90:
        raise ValueError("Payment terms are 0 to 90 days.")
    if kind == "final":
        amt = round(c["price"] - invoiced(c), 2)
        if amt <= TOL:
            raise ValueError("The whole price is already invoiced: there is no balance to invoice.")
        if not all(i["done_on"] for i in c["items"]):
            late = [i["name"] for i in c["items"] if not i["done_on"]]
            raise ValueError("The final invoice follows delivery, and these are not ticked off yet: " + "; ".join(late) + ". Tick them with client done, or use --kind extra for something else.")
        text = note or f"Balance: {c['offer']}"
    else:
        if not 1 <= amount <= 10_000_000 or len(note.strip()) < 3:
            raise ValueError("An extra invoice needs --amount (more than 0) and --note saying what it is for.")
        amt, text = round(amount, 2), note.strip()[:120]
    inv = {"id": next_invoice_id(slug, today), "kind": kind, "amount": amt, "issued": today.isoformat(), "due": (today + dt.timedelta(days=terms)).isoformat(), "note": text, "payments": []}
    c["invoices"].append(inv)
    inv_dir = f.parent / "invoices"
    inv_dir.mkdir(exist_ok=True)
    (inv_dir / f"{inv['id']}.html").write_text(invoice_html(slug, c, inv), encoding="utf-8")
    save(f, c)
    return f"Invoice {inv['id']} for {money(amt, c['sym'])}, due {inv['due']}: clients/{c['slug']}/invoices/{inv['id']}.html (open it, Print > Save as PDF, send it yourself).\n"


def paid(target: str, invoice_id: str, amount: float = 0, date: str = "", today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    f, c = load_client(target)
    inv = next((i for i in c["invoices"] if i["id"] == invoice_id), None)
    if not inv:
        raise ValueError(f"No invoice {invoice_id} for this client. Invoices: {', '.join(i['id'] for i in c['invoices']) or 'none'}.")
    left = outstanding(inv)
    if left <= TOL:
        raise ValueError(f"{invoice_id} is already paid in full.")
    amt = round(amount or left, 2)
    if amt <= 0 or amt > left + TOL:
        raise ValueError(f"The amount must be more than 0 and at most what is outstanding on {invoice_id} ({money(left, c['sym'])}).")
    when = parse_date(date, today).isoformat()
    cashdesk.log_cash(c["engine"], amt, "project", f"{invoice_id} {c['client']}", when)       # the Cash Desk learns of it at once
    inv["payments"].append({"date": when, "amount": amt})
    save(f, c)
    msg = f"Recorded {money(amt, c['sym'])} on {invoice_id} ({when}) and added it to the Cash Desk. Status: {status(c)}.\n"
    if c["currency"] != "USD":
        msg += f"Note: the Cash Desk adds amounts as they are; it does not convert {c['currency']}.\n"
    return msg + ("That invoice is now paid in full.\n" if outstanding(inv) <= TOL else f"{money(outstanding(inv), c['sym'])} is still outstanding on it.\n")


# ------------------------------------------------------------------ for the Weekly Review

def attention(slug: str, today: dt.date) -> dict:
    """What needs you today: overdue invoices (with the amount) and late deliverables, across the engine's open clients."""
    inv, late = [], []
    for _f, c in all_clients(slug):
        if status(c) == "closed":
            continue
        for i in c["invoices"]:
            if outstanding(i) > TOL and i["due"] < today.isoformat():
                inv.append({"client": c["client"], "id": i["id"], "owed": outstanding(i), "sym": c["sym"], "due": i["due"]})
        for it in c["items"]:
            if not it["done_on"] and it["due"] < today.isoformat():
                late.append({"client": c["client"], "item": it["name"], "due": it["due"]})
    return {"overdue_invoices": inv, "late_items": late}
