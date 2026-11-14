"""The Books Desk: a monthly pack for your accountant, from the records the other tools already keep.

    python dse.py books <engine> [--month 2026-11] [--base USD]
    python dse.py fx add <engine> --from GBP --to USD --rate 1.27 --date 2026-11-14      (the exchange rates YOU enter, see dse/fx.py)

It writes engines/<engine>/books/<month>/ with:
  summary.md       the one-page summary: received (cash basis), invoiced (accrual basis), still owed with ageing, written off, exchange rates used, year to date, and a list of things to check
  receipts.csv     every payment received in the month: date, amount and currency, amount in your base currency, the rate used, the source (client invoice, DFY remittance ...), who, the invoice
  invoices.csv     every invoice issued in the month with its status at month end
  receivables.csv  every invoice still owed at month end, with how many days past due
  writeoffs.csv    shortfalls you chose to write off (usually a transfer fee)

What it is not: it does not work out tax, and it does not decide cash or accrual, which exchange rate to use, how fees are treated, or whether anything is VAT, sales tax or
withholding. Those are for your accountant, and the summary lists the questions. It prepares clean records: every figure traces to a line in your own files, every currency stays
in its own currency, and money in a currency with no rate from you is listed as NOT converted, never guessed. Money received before currencies were recorded counts as dollars and is flagged.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from . import cashdesk, clients as cl, cuts, fx
from .common import ROOT, write_csv
from .engines import engine_dir, load

TOL = 0.005
REF = re.compile(r"\b((?:INV|CUT)-\d{4}-\d{3,4})\b")
BUCKETS = [("current (not yet due)", None, 0), ("1 to 30 days past due", 1, 30), ("31 to 60 days past due", 31, 60), ("over 60 days past due", 61, 10**6)]


def money(x: float, cur: str = "") -> str:
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(cur, "")
    body = f"{abs(x):,.0f}" if abs(x - round(x)) < TOL else f"{abs(x):,.2f}"
    return f"{'-' if x < 0 else ''}{sym}{body}" + ("" if sym else (f" {cur}" if cur else ""))


def last_complete(today: dt.date) -> str:
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{y:04d}-{m:02d}"


def invoice_index(slug: str) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for _f, c in cl.all_clients(slug):
        for i in c["invoices"]:
            idx[i["id"]] = {"id": i["id"], "source": "Client invoice", "who": c["client"], "cur": c["currency"], "issued": i["issued"], "due": i["due"], "amount": i["amount"],
                            "payments": i.get("payments", []), "writeoff": 0.0, "note": i.get("note", "")}
    for _f, s in cuts.all_students(slug):
        src = "DFY remittance" if s.get("program") == "dfy" else "Student revenue share"
        for i in s["invoices"]:
            idx[i["id"]] = {"id": i["id"], "source": src, "who": s["name"], "cur": s["currency"], "issued": i["issued"], "due": i["due"], "amount": i["amount"],
                            "payments": i.get("payments", []), "writeoff": float(i.get("writeoff", 0)), "note": i.get("note", "")}
    return idx


def paid_by(inv: dict, end: dt.date) -> float:
    """Payments counted by month end. Payments the Citadel sync recorded as history have no real date: they count as paid already."""
    return round(sum(p["amount"] for p in inv["payments"] if p.get("from_citadel") or p["date"] <= end.isoformat()), 2)


def owed_at(inv: dict, end: dt.date) -> float:
    return round(inv["amount"] - paid_by(inv, end) - inv["writeoff"], 2)


def month_label(ym: str) -> str:
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%B %Y")


def build(slug: str, month: str | None = None, base: str = "USD", today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    base = (base or "USD").upper()
    if not re.fullmatch(r"[A-Z]{3}", base):
        raise ValueError("The base currency is a 3-letter code such as USD.")
    month = month or last_complete(today)
    a, b = cashdesk.month_bounds(month, today)
    if a > today:
        raise ValueError("That month has not started yet.")
    rates = fx.read_rates(slug)
    idx = invoice_index(slug)

    # ---- receipts (cash basis)
    receipts: list[dict] = []
    for r in cashdesk.read_cash(slug):
        if not cashdesk.in_month(r["date"], a, b):
            continue
        amt = float(r["amount"])
        day = dt.date.fromisoformat(r["date"])
        ref = (REF.search(r.get("note", "")) or [None, ""])[1] if REF.search(r.get("note", "")) else ""
        inv = idx.get(ref)
        got = fx.convert(slug, amt, day, r["currency"], base, rates)
        receipts.append({"date": r["date"], "amount": amt, "currency": r["currency"], "currency_assumed": "yes" if r.get("currency_assumed") else "",
                         "base_amount": got[0] if got else "", "rate_used": (round(got[1]["rate"], 6) if got and r["currency"] != base else (1 if got else "")),
                         "rate_date": got[1]["date"] if got and r["currency"] != base else "", "rate_old": "yes" if got and got[1].get("old") else "",
                         "source": inv["source"] if inv else ("Refund" if r["kind"] == "refund" else "Other income (no invoice)"), "who": inv["who"] if inv else "",
                         "reference": ref, "kind": r["kind"], "note": r.get("note", ""), "_inv": inv, "_missing_ref": bool(ref and not inv)})
    receipts.sort(key=lambda x: x["date"])

    # ---- invoices issued in the month (accrual basis)
    issued, receivables, writeoffs = [], [], []
    for inv in sorted(idx.values(), key=lambda i: (i["issued"], i["id"])):
        issued_d = dt.date.fromisoformat(inv["issued"])
        if issued_d > b:
            continue
        left = owed_at(inv, b)
        due_d = dt.date.fromisoformat(inv["due"])
        days_over = max(0, (b - due_d).days) if left > TOL else 0
        status = "paid" if left <= TOL else ("part paid" if paid_by(inv, b) > TOL else "open") + (", overdue" if days_over > 0 else "")
        row = {"invoice": inv["id"], "source": inv["source"], "who": inv["who"], "issued": inv["issued"], "due": inv["due"], "amount": inv["amount"], "currency": inv["cur"],
               "paid_by_month_end": paid_by(inv, b), "written_off": inv["writeoff"], "owed_at_month_end": max(left, 0), "status": status, "note": inv["note"]}
        if a <= issued_d <= b:
            issued.append(row)
        if left > TOL:
            receivables.append({**row, "days_past_due": days_over})
        if inv["writeoff"] > TOL:
            last_pay = max((p["date"] for p in inv["payments"] if not p.get("from_citadel")), default="")
            if last_pay and a.isoformat() <= last_pay <= b.isoformat():
                writeoffs.append({"invoice": inv["id"], "who": inv["who"], "invoice_amount": inv["amount"], "currency": inv["cur"], "written_off": inv["writeoff"], "last_payment": last_pay,
                                  "note": "a shortfall you chose to accept (usually a transfer fee)"})

    # ---- year to date (receipts only)
    ytd = {}
    for r in cashdesk.read_cash(slug):
        d = dt.date.fromisoformat(r["date"])
        if d.year == a.year and d <= b:
            got = fx.convert(slug, float(r["amount"]), d, r["currency"], base, rates)
            ytd.setdefault(r["date"][:7], {"base": 0.0, "unconverted": 0})
            if got:
                ytd[r["date"][:7]]["base"] += got[0]
            else:
                ytd[r["date"][:7]]["unconverted"] += 1

    # ---- history paid in Citadel before this ledger
    history = [(i["who"], i["id"], i["amount"], i["cur"]) for i in idx.values() if any(p.get("from_citadel") for p in i["payments"]) and a <= dt.date.fromisoformat(i["issued"]) <= b]

    # ---- the files
    out_dir = engine_dir(slug) / "books" / month
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = lambda rows: [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]  # noqa: E731
    write_csv(out_dir / "receipts.csv", clean(receipts), first=["date", "amount", "currency", "base_amount", "rate_used", "rate_date", "source", "who", "reference"])
    write_csv(out_dir / "invoices.csv", issued or [{"invoice": ""}], first=["invoice", "source", "who", "issued", "due", "amount", "currency"])
    write_csv(out_dir / "receivables.csv", receivables or [{"invoice": ""}], first=["invoice", "source", "who", "due", "owed_at_month_end", "currency", "days_past_due"])
    write_csv(out_dir / "writeoffs.csv", writeoffs or [{"invoice": ""}], first=["invoice", "who", "written_off", "currency"])

    # ---- the summary
    L = [f"# Books Desk: {slug}, {month_label(month)}", "", f"Base currency {base}. Prepared from your own records on {today.isoformat()}. This is a record, not tax advice: your accountant decides how it is treated.", ""]
    cur_tot: dict[str, float] = {}
    for r in receipts:
        cur_tot[r["currency"]] = round(cur_tot.get(r["currency"], 0.0) + r["amount"], 2)
    conv_total = round(sum(r["base_amount"] for r in receipts if r["base_amount"] != ""), 2)
    unconv = [r for r in receipts if r["base_amount"] == ""]
    L += ["## Received in the month (cash basis)", f"- {len(receipts)} payment(s): " + (", ".join(money(v, c) for c, v in sorted(cur_tot.items())) if cur_tot else "none")
          + (f"; in {base}: {money(conv_total, base)}" + (" (excluding money with no exchange rate, below)" if unconv else "") if receipts else "")]
    by_src: dict[str, list] = {}
    for r in receipts:
        by_src.setdefault(r["source"], []).append(r)
    for src, rows in sorted(by_src.items()):
        tot = {}
        for r in rows:
            tot[r["currency"]] = round(tot.get(r["currency"], 0.0) + r["amount"], 2)
        L.append(f"  - {src}: {len(rows)} payment(s), " + ", ".join(money(v, c) for c, v in sorted(tot.items())))
    L += ["", "## Invoiced in the month (accrual basis)"]
    if issued:
        it: dict[str, float] = {}
        for r in issued:
            it[r["currency"]] = round(it.get(r["currency"], 0.0) + r["amount"], 2)
        L.append(f"- {len(issued)} invoice(s): " + ", ".join(money(v, c) for c, v in sorted(it.items())))
        isrc: dict[str, int] = {}
        for r in issued:
            isrc[r["source"]] = isrc.get(r["source"], 0) + 1
        L += [f"  - {k}: {v}" for k, v in sorted(isrc.items())]
    else:
        L.append("- none issued")
    L += ["", f"## Still owed at the end of {month_label(month)}"]
    if receivables:
        ot: dict[str, float] = {}
        for r in receivables:
            ot[r["currency"]] = round(ot.get(r["currency"], 0.0) + r["owed_at_month_end"], 2)
        L.append(f"- {len(receivables)} invoice(s): " + ", ".join(money(v, c) for c, v in sorted(ot.items())))
        for name, lo, hi in BUCKETS:
            rows = [r for r in receivables if (r["days_past_due"] == 0 if lo is None else lo <= r["days_past_due"] <= hi)]
            if rows:
                bt: dict[str, float] = {}
                for r in rows:
                    bt[r["currency"]] = round(bt.get(r["currency"], 0.0) + r["owed_at_month_end"], 2)
                L.append(f"  - {name}: {len(rows)}, " + ", ".join(money(v, c) for c, v in sorted(bt.items())))
        for r in sorted(receivables, key=lambda x: -x["days_past_due"])[:5]:
            if r["days_past_due"] > 0:
                L.append(f"  - oldest: {r['invoice']} {r['who']}, {money(r['owed_at_month_end'], r['currency'])}, {r['days_past_due']} days past due")
    else:
        L.append("- nothing owed")
    L += ["", "## Written off in the month"]
    L += ([f"- {w['invoice']} {w['who']}: {money(w['written_off'], w['currency'])} ({w['note']})" for w in writeoffs] if writeoffs else ["- none"])
    L += ["", "## Exchange rates"]
    used = {}
    for r in receipts:
        if r["rate_date"]:
            used[(r["currency"], r["rate_date"], r["rate_used"])] = r["rate_old"]
    if used:
        L += [f"- 1 {c} = {rt} {base}, the rate you entered for {d}" + (" (OLD: more than 45 days before the payment)" if old else "") for (c, d, rt), old in sorted(used.items())]
    elif not unconv:
        L.append(f"- all receipts were in {base}: no rates needed")
    for r in unconv:
        L.append(f"- NOT converted: {money(r['amount'], r['currency'])} on {r['date']} ({r['note'][:40]}): {fx.fix_hint(slug, r['currency'], base, dt.date.fromisoformat(r['date']))}")
    L += ["", f"## {a.year} to date (money received, in {base})"]
    run = 0.0
    for ym in sorted(ytd):
        run += ytd[ym]["base"]
        L.append(f"- {month_label(ym)}: {money(ytd[ym]['base'], base)}" + (f" ({ytd[ym]['unconverted']} payment(s) without a rate)" if ytd[ym]["unconverted"] else ""))
    L.append(f"- Total so far: {money(run, base)}")
    if history:
        L += ["", "## Paid in Citadel before this ledger started", f"- {len(history)} invoice(s) issued this month already show as paid in Citadel with no recorded receipt date, so they are not in the receipts above: "
              + ", ".join(f"{w} {i} ({money(a_, c)})" for w, i, a_, c in history[:6]) + (" ..." if len(history) > 6 else "")]
    flags = []
    noref = [r for r in receipts if not r["reference"] and r["kind"] != "refund"]
    if noref:
        flags.append(f"{len(noref)} payment(s) ({', '.join(money(r['amount'], r['currency']) for r in noref[:4])}{'...' if len(noref) > 4 else ''}) have no invoice number: keep the source document for each.")
    if any(r["_missing_ref"] for r in receipts):
        flags.append("A payment names an invoice that is not in your records: " + ", ".join(r["reference"] for r in receipts if r["_missing_ref"]))
    if any(r["currency_assumed"] for r in receipts):
        flags.append(f"{sum(1 for r in receipts if r['currency_assumed'])} payment(s) were logged before currencies were recorded and are counted as {cashdesk.BASE}: check them.")
    if unconv:
        flags.append(f"{len(unconv)} payment(s) have no exchange rate and are not converted.")
    if any(v for v in used.values()):
        flags.append("An exchange rate older than 45 days was used: check it.")
    if any(r["amount"] < 0 for r in receipts):
        flags.append("There are refunds in the month: they are negative lines in receipts.csv.")
    early = [r for r in receipts if r["_inv"] and r["date"] < r["_inv"]["issued"]]
    if early:
        flags.append("Payment dated before its invoice was issued: " + ", ".join(r["reference"] for r in early))
    if any(r["days_past_due"] > 60 for r in receivables):
        flags.append(f"{sum(1 for r in receivables if r['days_past_due'] > 60)} invoice(s) are over 60 days past due.")
    L += ["", "## Check before you send this to your accountant"] + ([f"- {f}" for f in flags] if flags else ["- nothing flagged"])
    L += ["", "## Questions for your accountant (this tool does not decide them)",
          "- Cash or accrual basis for this business, and which of the two views above to use.",
          "- Which exchange rate to use for each receipt and invoice, and how to treat the difference between the invoice date and the date the money landed.",
          "- How transfer fees and platform fees (Grey, Payoneer, bank) are recorded: they are not in these records.",
          "- How DFY remittances and student revenue shares are classified, and how written-off shortfalls are treated.",
          "- VAT, sales tax or withholding tax, if any apply to these clients and students.",
          "- Any money received into a personal account that should be in the company's books.",
          "- Whether any outstanding invoices need a provision at year end.", "",
          f"Files: engines/{slug}/books/{month}/ (summary.md, receipts.csv, invoices.csv, receivables.csv, writeoffs.csv). Nothing was sent."]
    text = "\n".join(L) + "\n"
    (out_dir / "summary.md").write_text(text, encoding="utf-8")
    return text
