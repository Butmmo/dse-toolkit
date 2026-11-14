"""The Statement Matcher: match the money that landed in Grey, Payoneer or a bank to your open invoices.

    python dse.py match <engine> <statement.csv> [--apply] [--monthfirst] [--tolerance 5]

Put the CSV you export from Grey, Payoneer or your bank in engines/<engine>/statements/ (a path anywhere also works at your PC). It reads the money coming IN, and
looks at every open invoice in the engine: student cuts (CUT-...) and client invoices (INV-...). For each credit it works out the likeliest invoice from:
  * the invoice number in the reference or description (the strongest sign)
  * the amount: exact, or short by a transfer fee (default tolerance: 2% of the invoice, at least $1 and at most $20, or what you pass with --tolerance)
  * the sender's name against the student's or client's name
  * the date: a credit from before the invoice was issued is marked down

What it will and will not do:
  * SURE   = the invoice number is in the line AND the amount is right (or short by a normal fee) AND nothing else fits as well. With --apply these are recorded through
             the same code as `cut paid` / `client paid`: the payment, the Cash Desk, and Citadel for DFY months. Nothing else is ever applied without you.
  * LIKELY = the name and amount fit, or the number fits but the amount is off. You get the exact command to run if you agree.
  * ASK    = more than one invoice fits equally well. UNMATCHED = no invoice fits (unknown senders, new income that may need an invoice).
  * debits, failed and pending lines are ignored; a line is never applied twice (a fingerprint is kept in engines/<engine>/data/matched-lines.csv); a credit that matches a
    payment you already recorded (same amount within 3 days) is listed as already recorded.
A credit in another currency than the invoice is never matched. Columns are found from the headers (date, amount or credit/debit, description, sender, reference, currency, status).
Dates written 03/04/2026 are read day first unless the file proves otherwise or you pass --monthfirst. It only proposes. Nothing is sent.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
from pathlib import Path

from . import clients as cl
from . import cuts
from .common import ROOT
from .engines import engine_dir, load
from .importer import read_rows, squash

TOL = 0.005
ALIASES = {
    "date": ["date", "transactiondate", "posteddate", "completedat", "datetime", "time", "createdat", "paymentdate", "valuedate", "settledat", "bookingdate", "completedon", "datecompleted"],
    "amount": ["amount", "creditamount", "amountreceived", "received", "value", "netamount", "amountusd", "transactionamount", "sum", "paidin", "credit", "deposit", "amountin"],
    "debit": ["debit", "withdrawal", "amountout", "paidout", "debitamount"],
    "description": ["description", "details", "narration", "memo", "note", "notes", "remarks", "transactiondetails", "purpose", "title", "transactiondescription", "paymentdetails"],
    "sender": ["sender", "from", "payer", "name", "counterparty", "originator", "party", "fromname", "paidby", "sendername", "payername", "beneficiary", "customer"],
    "ref": ["reference", "ref", "transactionid", "id", "referenceid", "paymentreference", "txnid", "transactionreference", "paymentid"],
    "currency": ["currency", "ccy", "currencycode"],
    "type": ["type", "direction", "transactiontype", "drcr", "category"],
    "status": ["status", "state", "transactionstatus"],
}
OK_STATUS = {"", "completed", "complete", "successful", "success", "settled", "posted", "paid", "processed", "done", "available", "received"}
OUT_TYPES = ("debit", "withdraw", "payout", "sent", "transfer out", "fee", "charge", "purchase", "card payment", "dr")
IN_TYPES = ("credit", "deposit", "received", "incoming", "payment received", "transfer in", "cr", "receive")
ID_RX = re.compile(r"\b(CUT|INV)[\s_-]*((?:19|20)\d{2})[\s_-]*(\d{3,4})\b", re.I)


# ------------------------------------------------------------------ reading the statement

def find_columns(headers: list[str]) -> dict[str, str]:
    sq = {squash(h): h for h in headers}
    out: dict[str, str] = {}
    for std, names in ALIASES.items():
        for n in names:
            if n in sq and sq[n] not in out.values():
                out[std] = sq[n]
                break
    return out


def parse_amount(v: str) -> float | None:
    s = (v or "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.endswith("-")
    s = re.sub(r"[^\d.,]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", s) else s.replace(",", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def parse_date(v: str, dayfirst: bool) -> dt.date | None:
    s = (v or "").strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mo = (a, b) if dayfirst else (b, a)
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    for fmt in ("%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y", "%d-%b-%Y"):
        try:
            return dt.datetime.strptime(s[:20].strip(), fmt).date()
        except ValueError:
            continue
    return None


def detect_dayfirst(rows: list[dict], col: str, monthfirst: bool) -> tuple[bool, str]:
    if monthfirst:
        return False, ""
    first_gt12 = second_gt12 = 0
    for r in rows:
        m = re.match(r"\s*(\d{1,2})[/.\-](\d{1,2})[/.\-]\d{4}", r.get(col, "") or "")
        if m:
            first_gt12 += int(m.group(1)) > 12
            second_gt12 += int(m.group(2)) > 12
    if second_gt12 and not first_gt12:
        return False, "Dates read month first (the file proves it)."
    if first_gt12:
        return True, ""
    has_slash = any(re.match(r"\s*\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}", r.get(col, "") or "") for r in rows)
    return True, "Dates like 03/04/2026 are ambiguous here: read day first. Use --monthfirst if that is wrong." if has_slash else ""


def read_statement(path: Path, monthfirst: bool = False) -> dict:
    headers, rows = read_rows(path)
    cols = find_columns(headers)
    if "date" not in cols or ("amount" not in cols and "debit" not in cols):
        raise ValueError("I could not find the date and amount columns. The statement needs a date and an amount (or credit and debit) column. Found: " + ", ".join(headers[:12]))
    dayfirst, note = detect_dayfirst(rows, cols["date"], monthfirst)
    credits, skipped = [], {"debits": 0, "not completed": 0, "no date or amount": 0}
    for i, r in enumerate(rows, 2):
        g = lambda k: (r.get(cols[k], "") or "").strip() if k in cols else ""  # noqa: E731
        status = g("status").lower()
        if status not in OK_STATUS and not any(k in status for k in ("complet", "success", "settled", "posted")):
            skipped["not completed"] += 1
            continue
        d = parse_date(g("date"), dayfirst)
        amt = parse_amount(g("amount"))
        if d is None or amt is None:
            if "debit" in cols and parse_amount(g("debit")):
                skipped["debits"] += 1
            else:
                skipped["no date or amount"] += 1
            continue
        typ = g("type").lower()
        if amt < 0 or any(k in typ for k in OUT_TYPES) and not any(k in typ for k in IN_TYPES):
            skipped["debits"] += 1
            continue
        if amt == 0:
            continue
        sender, desc, ref = g("sender"), g("description"), g("ref")
        credits.append({"line": i, "date": d, "amount": round(amt, 2), "sender": sender, "description": desc, "ref": ref, "currency": g("currency").upper(),
                        "fp": hashlib.sha1(f"{d.isoformat()}|{amt:.2f}|{(ref or desc)[:80].lower()}|{sender.lower()}".encode()).hexdigest()[:16]})
    return {"credits": credits, "skipped": skipped, "note": note, "columns": cols}


# ------------------------------------------------------------------ the open invoices

def invoice_items(slug: str) -> list[dict]:
    items = []
    for f, s in cuts.all_students(slug):
        for i in s["invoices"]:
            items.append({"kind": "cut", "id": i["id"], "who": s["name"], "amount": i["amount"], "owed": cuts.owed(i), "sym": s["sym"], "cur": s["currency"], "issued": i["issued"], "due": i["due"],
                          "target": f"{slug}/{s['slug']}", "payments": [(p["date"], p["amount"]) for p in i.get("payments", [])]})
    for f, c in cl.all_clients(slug):
        for i in c["invoices"]:
            items.append({"kind": "client", "id": i["id"], "who": c["client"], "amount": i["amount"], "owed": cl.outstanding(i), "sym": c["sym"], "cur": c["currency"], "issued": i["issued"], "due": i["due"],
                          "target": f"{slug}/{c['slug']}", "payments": [(p["date"], p["amount"]) for p in i.get("payments", [])]})
    return items


def money(x: float, sym: str = "$") -> str:
    return f"{sym}{x:,.0f}" if abs(x - round(x)) < TOL else f"{sym}{x:,.2f}"


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]{3,}", (s or "").lower()) if t not in ("ltd", "llc", "inc", "the", "and", "limited", "company", "payment", "transfer", "from")]


def name_hit(who: str, text: str) -> bool:
    need = tokens(who)
    if not need:
        return False
    have = set(tokens(text))
    got = sum(1 for t in need if t in have)
    return got >= min(2, len(need))


def fee_tolerance(owed: float, override: float | None) -> float:
    return override if override is not None else min(20.0, max(1.0, 0.02 * owed))


def score(c: dict, it: dict, remaining: float, tol_fee: float) -> dict:
    text = " ".join((c["description"], c["ref"], c["sender"]))
    ids = {f"{m.group(1).upper()}-{m.group(2)}-{m.group(3)}" for m in ID_RX.finditer(text)}
    ref = it["id"] in ids
    s, why = 0, []
    if ref:
        s += 100
        why.append("the invoice number is in the line")
    diff = round(remaining - c["amount"], 2)
    amount_kind = "other"
    if abs(diff) < TOL:
        s += 50
        amount_kind = "exact"
        why.append("the amount is exactly right")
    elif 0 < diff <= tol_fee:
        s += 35
        amount_kind = "short_fee"
        why.append(f"{money(diff, it['sym'])} short, within a normal transfer fee")
    elif diff > 0:
        amount_kind = "partial"
        why.append(f"{money(c['amount'], it['sym'])} is part of the {money(remaining, it['sym'])} owed")
    else:
        amount_kind = "over"
        why.append(f"{money(-diff, it['sym'])} MORE than the {money(remaining, it['sym'])} owed")
    nm = name_hit(it["who"], text)
    if nm:
        s += 40
        why.append("the name fits")
    early = c["date"].isoformat() < it["issued"]
    if early:
        s -= 30
        why.append("it arrived before the invoice was issued")
    return {"item": it, "score": s, "ref": ref, "name": nm, "amount_kind": amount_kind, "diff": diff, "why": why, "early": early}


def already_recorded(c: dict, items: list[dict]) -> str:
    for it in items:
        for d, a in it["payments"]:
            if abs(a - c["amount"]) < TOL and abs((dt.date.fromisoformat(d) - c["date"]).days) <= 3:
                return f"{it['id']} ({it['who']}) already has a payment of {money(a, it['sym'])} on {d}"
    return ""


def classify(c: dict, items: list[dict], remaining: dict[str, float], override: float | None) -> dict:
    cands = []
    for it in items:
        rem = remaining.get(it["id"], it["owed"])
        if rem <= TOL:
            continue
        if c["currency"] and c["currency"] != it["cur"]:
            continue
        sc = score(c, it, rem, fee_tolerance(rem, override))
        if sc["score"] >= 40 or sc["ref"]:
            cands.append(sc)
    cands.sort(key=lambda x: -x["score"])
    if not cands:
        return {"verdict": "unmatched", "cands": []}
    best = cands[0]
    second = cands[1] if len(cands) > 1 else None
    margin = best["score"] - (second["score"] if second else 0)
    good_amount = best["amount_kind"] in ("exact", "short_fee")
    if best["ref"] and good_amount and not best["early"] and margin >= 30 and best["score"] >= 130:
        return {"verdict": "sure", "best": best, "cands": cands}
    if second and margin < 20 and best["score"] >= 60:
        return {"verdict": "ask", "cands": cands}
    if best["ref"] or (best["name"] and best["amount_kind"] in ("exact", "short_fee", "partial")):
        return {"verdict": "likely", "best": best, "cands": cands}
    return {"verdict": "unmatched", "cands": cands}


# ------------------------------------------------------------------ the ledger and the report

def ledger_path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "matched-lines.csv"


def read_ledger(slug: str) -> set[str]:
    p = ledger_path(slug)
    if not p.exists():
        return set()
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {r["fp"] for r in csv.DictReader(f)}


def add_ledger(slug: str, row: dict) -> None:
    p = ledger_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fp", "date", "amount", "invoice", "applied_on"])
        if fresh:
            w.writeheader()
        w.writerow(row)


def resolve_statement(slug: str, statement: str) -> Path:
    p = Path(statement)
    for cand in ([p] if p.is_absolute() else [ROOT / statement, engine_dir(slug) / "statements" / statement, p]):
        if cand.is_file():
            return cand
    have = ", ".join(sorted(x.name for x in (engine_dir(slug) / "statements").glob("*.csv"))) if (engine_dir(slug) / "statements").is_dir() else "none yet"
    raise ValueError(f"I could not find the statement '{statement}'. Put your exported CSV in engines/{slug}/statements/. There: {have}.")


def apply_match(sc: dict, c: dict, slug: str, api=None, today: dt.date | None = None) -> str:
    it = sc["item"]
    when = c["date"].isoformat()
    if it["kind"] == "cut":
        return cuts.paid(it["target"], it["id"], c["amount"], when, False, today, api)
    return cl.paid(it["target"], it["id"], c["amount"], when, today)


def report(slug: str, statement: str, apply: bool = False, monthfirst: bool = False, tolerance: float | None = None, api=None, today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    if tolerance is not None and not 0 <= tolerance <= 100:
        raise ValueError("--tolerance is a fee allowance between 0 and 100.")
    path = resolve_statement(slug, statement)
    st = read_statement(path, monthfirst)
    items = invoice_items(slug)
    if not items:
        raise ValueError(f"Engine {slug} has no invoices yet: the Cut Desk (cut report) and the Client Desk (client won) make them.")
    done = read_ledger(slug)
    remaining = {it["id"]: it["owed"] for it in items}
    buckets = {"applied": [], "sure": [], "likely": [], "ask": [], "unmatched": [], "recorded": [], "seen": [], "errors": []}
    for c in sorted(st["credits"], key=lambda x: (x["date"], x["line"])):
        who = f"{c['date'].isoformat()}  {money(c['amount'], '')} {c['currency'] or ''}  from {c['sender'] or '(no sender)'}  {c['description'][:50]}".rstrip()
        if c["fp"] in done:
            buckets["seen"].append(who)
            continue
        res = classify(c, items, remaining, tolerance)
        v = res["verdict"]
        if v == "unmatched":
            rec = already_recorded(c, items)
            if rec:
                buckets["recorded"].append(f"{who}: {rec}")
                continue
        if v == "sure":
            best = res["best"]
            line = f"{who}\n    -> {best['item']['id']} {best['item']['who']}: " + "; ".join(best["why"])
            if best["amount_kind"] == "short_fee":
                line += f"\n    Short by {money(best['diff'], best['item']['sym'])}: ask {best['item']['who']} to cover it, or accept it with --writeoff on `paid`."
            remaining[best["item"]["id"]] = round(remaining.get(best["item"]["id"], best["item"]["owed"]) - c["amount"], 2)
            if apply:
                try:
                    msg = apply_match(best, c, slug, api, today)
                    add_ledger(slug, {"fp": c["fp"], "date": c["date"].isoformat(), "amount": c["amount"], "invoice": best["item"]["id"], "applied_on": today.isoformat()})
                    buckets["applied"].append(line + "\n    APPLIED: " + msg.strip().splitlines()[0])
                except ValueError as e:
                    buckets["errors"].append(f"{who}: {e}")
            else:
                buckets["sure"].append(line)
        elif v == "likely":
            best = res["best"]
            cmd = (f"python dse.py {'cut' if best['item']['kind'] == 'cut' else 'client'} paid {best['item']['target']} --invoice {best['item']['id']} --amount {c['amount']:g} --date {c['date'].isoformat()}")
            buckets["likely"].append(f"{who}\n    -> {best['item']['id']} {best['item']['who']}: " + "; ".join(best["why"]) + f"\n    If you agree: {cmd}")
        elif v == "ask":
            buckets["ask"].append(f"{who}\n    fits more than one: " + "; ".join(f"{x['item']['id']} {x['item']['who']} (score {x['score']})" for x in res["cands"][:3]))
        else:
            buckets["unmatched"].append(who)
    S = st["skipped"]
    n = len(st["credits"])
    L = [f"# Statement Matcher: {path.name}", "", f"{n} credit(s) read; ignored: {S['debits']} debit(s), {S['not completed']} not completed, {S['no date or amount']} without a date or amount. {len(items)} invoice(s) in engine {slug}."]
    if st["note"]:
        L.append("Note: " + st["note"])
    def sec(title, key, hint=""):
        if buckets[key]:
            L.extend(["", f"## {title} ({len(buckets[key])})" + (f": {hint}" if hint else "")] + [f"- {x}" for x in buckets[key]])
    sec("Applied", "applied")
    sec("Sure matches", "sure", "run again with --apply to record them" if not apply else "")
    sec("Likely: check each", "likely")
    sec("Could be more than one invoice", "ask", "decide which")
    sec("Already recorded", "recorded", "same amount within 3 days of a payment you recorded")
    sec("No invoice fits", "unmatched", "new income that may need an invoice, or a sender to ask about")
    sec("Seen before", "seen", "applied in an earlier run")
    sec("Could not apply", "errors")
    if not any(buckets[k] for k in ("applied", "sure", "likely", "ask", "unmatched", "recorded", "seen", "errors")):
        L.append("\nNothing to match: no credits in this statement.")
    L += ["", "Only 'sure' matches are ever applied by --apply, and each credit only once. Nothing was sent."]
    text = "\n".join(L) + "\n"
    out = engine_dir(slug) / "statements"
    out.mkdir(exist_ok=True)
    (out / f"{path.stem}-match.md").write_text(text, encoding="utf-8")
    return text
