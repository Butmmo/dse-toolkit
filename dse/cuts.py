"""The Cut Desk: the percentage cut your students owe you, from agreement to money received.

    python dse.py cut add <engine> --name "Ada Obi" --percent 10 [--basis gross|net] [--currency USD] [--method grey|payoneer|other] [--email a@b.com] [--start 2026-11-01]
    python dse.py cut report <engine>/<student> --month 2026-11 --earned 3200 [--fees 320] [--proof "screenshot of November statement"] [--replace]
    python dse.py cut paid <engine>/<student> --invoice CUT-2026-001 [--amount 300] [--date 2026-12-03] [--writeoff]
    python dse.py cut list <engine>            who owes what, who has not reported
    python dse.py cut show <engine>/<student>  every month, invoice and payment
    python dse.py cut status <engine>/<student> --to paused|ended|active

How it works (a plan you can change in the agreement, not a legal structure):
  * each student has an agreement: your percent, the basis (their GROSS earnings, or NET of the platform's own fees), the currency, the way they pay you (Grey, Payoneer ...)
  * every month the student reports what they earned (0 is a valid report) and where the proof is. You enter it; the cut is worked out as percent x basis
  * a cut above zero becomes an invoice in the company name (a print-ready page you send yourself), due 7 days later; the student bears the transfer fee
  * `paid` records what actually arrived, adds it to the Cash Desk, and says plainly if it came in short (usually a transfer fee). Use --writeoff to accept a small shortfall
  * a student who has not reported by the 7th of the next month, or whose earnings drop by half against their own recent average, shows up in the Weekly Review: a prompt to ask
    a friendly question, never an accusation
Files: engines/<engine>/cuts/<student>/student.json, agreement.md, invoices/CUT-<year>-<n>.html. Payment details are read from engines/<engine>/payment-details-<method>.txt
(or payment-details.txt) on this PC; they never sync to Citadel or Git. The Cash Desk adds amounts as they are and does not convert currencies.
The agreement text is a starting point, not legal advice: have it checked, and check the platforms your students earn on allow sharing earnings.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import cashdesk
from . import clients as cl
from .common import ROOT
from .engines import engine_dir, load

TOL = 0.005
REPORT_BY_DAY = 7
SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
METHODS = ("grey", "payoneer", "other")
DROP_RATIO = 0.5
# The D'Famocious Year (DFY) terms as Citadel's DFY Tracker defines them (src/lib/dfy.ts): 20% of NET income, qualified months are 2,000 or more,
# the remittance is capped at 18,000 in total, and it ends at 12 qualified months or the cap, whichever comes first.
DFY = {"percent": 20.0, "cap": 18000.0, "threshold": 2000.0, "months_target": 12}
DFY_DISCLOSURE = ("DFY is a revenue-share obligation: 20% of your earnings while it's active, capped at $18,000 total, ending at 12 qualified months or the cap, "
                  "whichever comes first. This is a real, binding financial commitment; plan for it the way you'd plan for any other significant obligation.")


def cuts_dir(slug: str) -> Path:
    return engine_dir(slug) / "cuts"


def money(x: float, sym: str = "$") -> str:
    return f"{sym}{x:,.0f}" if abs(x - round(x)) < TOL else f"{sym}{x:,.2f}"


def resolve(target: str) -> Path:
    t = (target or "").replace("\\", "/").strip()
    p = Path(t) if Path(t).is_absolute() else ROOT / t
    if p.name == "student.json" and p.is_file():
        if ROOT.resolve() not in p.resolve().parents:
            raise ValueError("That file is outside this toolkit.")
        return p
    m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_-]{0,59})/([a-z0-9-]{1,40})", t)
    if m:
        f = cuts_dir(m.group(1)) / m.group(2) / "student.json"
        if f.is_file():
            return f
        have = ", ".join(sorted(x.name for x in cuts_dir(m.group(1)).iterdir() if x.is_dir())) if cuts_dir(m.group(1)).is_dir() else "none yet"
        raise ValueError(f"No student '{m.group(2)}' in engine {m.group(1)}. Students: {have}.")
    raise ValueError("Name the student as engine/student-name (for example my-engine/ada-obi).")


def load_student(target: str) -> tuple[Path, dict]:
    f = resolve(target)
    return f, json.loads(f.read_text(encoding="utf-8"))


def save(f: Path, s: dict) -> None:
    f.write_text(json.dumps(s, indent=1), encoding="utf-8")


def all_students(slug: str) -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(cuts_dir(slug).glob("*/student.json")) if cuts_dir(slug).is_dir() else []:
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    return out


def month_key(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def prev_month(d: dt.date) -> str:
    y, m = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return f"{y:04d}-{m:02d}"


def paid_total(inv: dict) -> float:
    return round(sum(p["amount"] for p in inv.get("payments", [])) + inv.get("writeoff", 0), 2)


def owed(inv: dict) -> float:
    return round(inv["amount"] - paid_total(inv), 2)


def next_id(slug: str, today: dt.date) -> str:
    n = 0
    for _f, s in all_students(slug):
        for i in s["invoices"]:
            m = re.fullmatch(rf"CUT-{today.year}-(\d+)", i["id"])
            if m:
                n = max(n, int(m.group(1)))
    return f"CUT-{today.year}-{n + 1:03d}"


# ------------------------------------------------------------------ actions

def add(slug: str, name: str, percent: float, basis: str = "gross", currency: str = "USD", method: str = "grey", email: str = "", due_days: int = 7, start: str = "",
        today: dt.date | None = None, program: str = "custom") -> str:
    cfg = load(slug)
    today = today or dt.date.today()
    if program not in ("custom", "dfy"):
        raise ValueError("Program is custom or dfy (the D'Famocious Year terms).")
    if program == "dfy":
        percent, basis, currency = DFY["percent"], "net", "USD"
    name = re.sub(r"\s+", " ", name or "").strip()[:60]
    if len(name) < 2:
        raise ValueError("Give the student's name.")
    if not 1 <= percent <= 60:
        raise ValueError("The percent is between 1 and 60.")
    if basis not in ("gross", "net"):
        raise ValueError("Basis is gross (what they earn) or net (after the platform's own fees).")
    if currency not in SYMBOLS:
        raise ValueError("Currency is USD, GBP or EUR.")
    if method not in METHODS:
        raise ValueError("Method is grey, payoneer or other.")
    if not 0 <= due_days <= 60:
        raise ValueError("Days to pay are 0 to 60.")
    if email and not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        raise ValueError("That email address does not look right.")
    st = dt.date.fromisoformat(start) if start else today.replace(day=1)
    sslug = cl.slugify(name)
    folder = cuts_dir(slug) / sslug
    if (folder / "student.json").exists():
        raise ValueError(f"{name} is already set up. See: python dse.py cut show {slug}/{sslug}")
    s = {"slug": sslug, "name": name, "engine": slug, "email": email, "percent": float(percent), "basis": basis, "currency": currency, "sym": SYMBOLS[currency], "method": method,
         "due_days": due_days, "start": st.isoformat(), "created": today.isoformat(), "status": "active", "statements": [], "invoices": [], "program": program,
         "cap": DFY["cap"] if program == "dfy" else None, "threshold": DFY["threshold"] if program == "dfy" else None, "months_target": DFY["months_target"] if program == "dfy" else None}
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / "student.json", s)
    (folder / "agreement.md").write_text(agreement(slug, s, cfg), encoding="utf-8")
    notes = []
    if not cl.payment_details(slug, method):
        notes.append(f"No payment details for {method} yet: put them in engines/{slug}/payment-details-{method}.txt on this PC (they stay off Citadel and Git).")
    if currency != "USD":
        notes.append(f"The Cash Desk adds amounts as they are and does not convert {currency}.")
    terms = ("- D'Famocious Year terms: 20% of net income, capped at $18,000 in total, ending at 12 qualified months (net income of $2,000 or more) or the cap, whichever comes first.\n" if program == "dfy" else "")
    return (f"# Cut Desk: {name} added\n\n{terms}- {percent:g}% of their {basis} earnings, reported monthly by the {REPORT_BY_DAY}th, paid within {due_days} days of the invoice, through {method}.\n"
            f"- Agreement starter: cuts/{sslug}/agreement.md (a starting point, not legal advice: have it checked before they sign).\n" + "".join(f"- {n}\n" for n in notes)
            + "\nNothing was sent. Share the agreement with the student yourself.\n")


def agreement(slug: str, s: dict, cfg: dict) -> str:
    co = cfg.get("brand_name") or cfg.get("name") or "[your company]"
    sender = cfg.get("sender_name") or "[your name]"
    basis = ("the gross amount you are paid" if s["basis"] == "gross" else "the amount you are paid after the platform's own fees")
    if s.get("program") == "dfy":
        return "\n".join([
            f"# D'Famocious Year (DFY) remittance: {s['name']}", "", "A starting point, not legal advice. Have a lawyer check it.", "", DFY_DISCLOSURE, "",
            f"1. Parties: D'Famocious Ltd (RC 8867648) trading as {cfg.get('brand_name') or cfg.get('name') or '[your company]'}, and {s['name']}.",
            "2. The remittance: 20% of the net income you file in Citadel for each month you earn.",
            "3. A qualified month is one with net income of $2,000 or more. The DFY ends at 12 qualified months or when your total remittances reach $18,000, whichever comes first.",
            f"4. Reporting: you file each month's net income in Citadel (DFY tracker) by the {REPORT_BY_DAY}th of the next month. File 0 if you earned nothing.",
            f"5. Payment: each month's remittance is due within {s['due_days']} days of filing, in USD, to the account shown in Citadel (Payments). You cover the transfer fees so the full remittance arrives.",
            "6. Records: keep your statements for 12 months and show them if asked, in a reasonable way.",
            "7. If a month looks very different from your usual, we may ask about it. That is a question, not an accusation.",
            "8. Late payment: [your late-payment terms].", "9. Governing law and disputes: [the law that applies; get advice].", "", f"Signed: {cfg.get('sender_name') or '[your name]'} for D'Famocious Ltd:  ____________    {s['name']}:  ____________    Date: ____________", ""])
    return "\n".join([
        f"# Revenue share agreement: {s['name']}", "", "A starting point, not legal advice. Have a lawyer check it, and check that the platforms you earn on allow you to share earnings.", "",
        f"1. Parties: D'Famocious Ltd (RC 8867648) trading as {co}, and {s['name']}.",
        f"2. The cut: {s['percent']:g}% of {basis} from work won or delivered through the program, from {s['start']}.",
        f"3. Reporting: by the {REPORT_BY_DAY}th of each month you report what you earned last month, in {s['currency']}, with proof (a statement or screenshot). Report 0 if you earned nothing.",
        f"4. Payment: the cut is invoiced after your report and paid within {s['due_days']} days, by {s['method']}. You cover the transfer fees so the full cut arrives.",
        "5. Records: keep your statements for 12 months and show them if asked, in a reasonable way.",
        "6. If a month's earnings look very different from your usual, we may ask about it. That is a question, not an accusation.",
        "7. Ending: either side can end this with 14 days' written notice. Cuts for work already done stay payable.",
        "8. Late payment: [your late-payment terms].", "9. Governing law and disputes: [the law that applies; get advice].", "10. Privacy: each side keeps the other's business information private.", "",
        f"Signed: {sender} for D'Famocious Ltd:  ____________    {s['name']}:  ____________    Date: ____________", ""])


def dfy_totals(s: dict, exclude_month: str = "") -> tuple[float, int]:
    """(remittance already invoiced, qualified months so far) for a DFY student, leaving out one month (for a correction)."""
    rows = [x for x in s["statements"] if x["month"] != exclude_month]
    return round(sum(x["cut"] for x in rows), 2), sum(1 for x in rows if x.get("qualified"))


def report(target: str, month: str, earned: float, fees: float = 0, proof: str = "", replace: bool = False, today: dt.date | None = None,
           source: str = "manual", citadel_id: str = "") -> str:
    today = today or dt.date.today()
    f, s = load_student(target)
    slug = s["engine"]
    dfy = s.get("program") == "dfy"
    if dfy and fees:
        raise ValueError("DFY works on the net income the student files, so there are no platform fees to enter.")
    if s["status"] == "completed":
        raise ValueError("This DFY is complete (the cap or 12 qualified months was reached): nothing more is owed.")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month or ""):
        raise ValueError("Month as YYYY-MM, for example 2026-11.")
    if month > month_key(today):
        raise ValueError("That month has not happened yet.")
    if month < s["start"][:7]:
        raise ValueError(f"The agreement starts in {s['start'][:7]}: there is nothing to report before that.")
    if s["status"] == "ended":
        raise ValueError("This agreement has ended. Set it back to active first if that is wrong: python dse.py cut status ... --to active")
    if not 0 <= earned <= 10_000_000:
        raise ValueError("Earned is the month's earnings (0 is fine).")
    if not 0 <= fees <= earned:
        raise ValueError("Platform fees cannot be negative or more than what was earned.")
    proof = re.sub(r"\s+", " ", proof or "").strip()[:200]
    old = next((x for x in s["statements"] if x["month"] == month), None)
    reuse_id = ""
    if old:
        inv = next((i for i in s["invoices"] if i["id"] == old.get("invoice")), None)
        if not replace:
            raise ValueError(f"{month} is already reported. To correct it, add --replace (only possible while nothing has been paid on it).")
        if inv and paid_total(inv) > 0:
            raise ValueError("A payment is already recorded on that month's invoice, so it cannot be replaced. Issue an extra adjustment with your own note instead.")
        s["statements"].remove(old)
        if inv:
            reuse_id = inv["id"]                      # a corrected month keeps its invoice number: no gaps
            s["invoices"].remove(inv)
            (f.parent / "invoices" / f"{inv['id']}.html").unlink(missing_ok=True)
    base = earned if s["basis"] == "gross" else earned - fees
    cut = round(base * s["percent"] / 100, 2)
    qualified = bool(dfy and earned >= s["threshold"])
    dfy_notes: list[str] = []
    if dfy:
        so_far, q_so_far = dfy_totals(s, month)
        room = round(s["cap"] - so_far, 2)
        if cut > room + TOL:
            dfy_notes.append(f"The $18,000 cap leaves only {money(max(room, 0), s['sym'])} of this month's {money(cut, s['sym'])}, so that is what is invoiced. Citadel still shows the full amount for the month.")
            cut = max(room, 0)
    prior = [x["earned"] for x in sorted(s["statements"], key=lambda x: x["month"]) if x["month"] < month][-3:]
    notes = []
    if len(prior) >= 2 and sum(prior) / len(prior) > 0 and earned < DROP_RATIO * sum(prior) / len(prior):
        notes.append(f"Earnings of {money(earned, s['sym'])} are less than half of their recent average ({money(sum(prior) / len(prior), s['sym'])}). Worth a friendly question about how the month went.")
    if not proof:
        notes.append("No proof noted. Ask for a statement or screenshot and note where you keep it (re-run with --replace --proof ...).")
    st = {"month": month, "earned": earned, "fees": fees, "cut": cut, "proof": proof, "reported_on": today.isoformat(), "invoice": "", "qualified": qualified, "source": source, "citadel_id": citadel_id}
    inv = None
    if cut > TOL:
        label = "DFY remittance" if dfy else "Revenue share"
        inv = {"id": reuse_id or next_id(slug, today), "month": month, "amount": cut, "issued": today.isoformat(), "due": (today + dt.timedelta(days=s["due_days"])).isoformat(),
               "note": f"{label} {s['percent']:g}% of {s['basis']} {'net income' if dfy else 'earnings'} for {month}", "payments": [], "writeoff": 0}
        st["invoice"] = inv["id"]
        s["invoices"].append(inv)
        (f.parent / "invoices").mkdir(exist_ok=True)
        pseudo = {"client": s["name"], "contact": "", "email": s.get("email", ""), "address": "", "sym": s["sym"]}
        (f.parent / "invoices" / f"{inv['id']}.html").write_text(cl.invoice_html(slug, pseudo, inv, s["method"]), encoding="utf-8")
    s["statements"].append(st)
    s["statements"].sort(key=lambda x: x["month"])
    if dfy:
        total, qn = dfy_totals(s)
        if total + TOL >= s["cap"] or qn >= s["months_target"]:
            s["status"] = "completed"
            dfy_notes.append(("The $18,000 cap is reached" if total + TOL >= s["cap"] else f"{qn} qualified months reached") + ": this DFY is complete and nothing more is owed.")
        else:
            dfy_notes.append(f"DFY progress: {qn} of {s['months_target']} qualified months, {money(total, s['sym'])} of {money(s['cap'], s['sym'])} remitted so far.")
    save(f, s)
    notes = dfy_notes + notes
    lines = [f"# Cut Desk: {s['name']}, {month}", "", f"Reported earnings {money(earned, s['sym'])}" + (f", platform fees {money(fees, s['sym'])}" if s["basis"] == "net" or fees else "") + f"; basis {s['basis']}.",
             f"Cut: {s['percent']:g}% of {money(base, s['sym'])} = {money(cut, s['sym'])}."]
    if inv:
        lines.append(f"Invoice {inv['id']} for {money(cut, s['sym'])}, due {inv['due']}: cuts/{s['slug']}/invoices/{inv['id']}.html (open it, Print > Save as PDF, send it yourself).")
        if not cl.payment_details(slug, s["method"]):
            lines.append(f"Note: no payment details yet. Put them in engines/{slug}/payment-details-{s['method']}.txt on this PC.")
    else:
        lines.append("Nothing earned, so no invoice this month.")
    lines += [f"Note: {n}" for n in notes]
    return "\n".join(lines) + "\nNothing was sent.\n"


def push_received(s: dict, st: dict, api=None, note: str = "") -> str:
    """Tell Citadel this DFY month's money has arrived (what the council's Mark paid does). Never raises: on failure the month is queued for the next sync."""
    if st.get("citadel_paid") or not st.get("citadel_id"):
        return ""
    if api is None:
        try:
            from . import dfysync
            api = dfysync.get_api()
        except Exception:
            api = None
    if api is None:
        st["push_pending"] = True
        return "Could not reach Citadel from here: it will be marked received there at the next sync (the runner does this)."
    try:
        res = api.rpc("hq_dfy_mark_received", {"p_month_id": st["citadel_id"], "p_note": note or f"Received via {s['method']} (HQ Cut Desk)"})
        st["citadel_paid"], st["push_pending"] = True, False
        return "Citadel already showed this month as paid." if isinstance(res, dict) and res.get("already") else "Marked received in Citadel too: the student's DFY page now shows it paid."
    except Exception as e:
        st["push_pending"] = True
        return f"Could not mark it in Citadel yet ({type(e).__name__}): it will retry at the next sync."


def paid(target: str, invoice_id: str, amount: float = 0, date: str = "", writeoff: bool = False, today: dt.date | None = None, api=None) -> str:
    today = today or dt.date.today()
    f, s = load_student(target)
    inv = next((i for i in s["invoices"] if i["id"] == invoice_id), None)
    if not inv:
        raise ValueError(f"No invoice {invoice_id} for this student. Invoices: {', '.join(i['id'] for i in s['invoices']) or 'none'}.")
    left = owed(inv)
    if left <= TOL:
        raise ValueError(f"{invoice_id} is already settled.")
    amt = round(amount or left, 2)
    if amt <= 0 or amt > left + TOL:
        raise ValueError(f"The amount must be more than 0 and at most what is still owed on {invoice_id} ({money(left, s['sym'])}).")
    when = cl.parse_date(date, today).isoformat()
    cashdesk.log_cash(s["engine"], amt, "commission", f"{invoice_id} {s['name']} {inv['month']}", when)
    inv["payments"].append({"date": when, "amount": amt})
    short = owed(inv)
    msg = f"Recorded {money(amt, s['sym'])} on {invoice_id} ({when}) and added it to the Cash Desk."
    if writeoff and short > TOL:
        inv["writeoff"] = round(inv.get("writeoff", 0) + short, 2)
        msg += f" The shortfall of {money(short, s['sym'])} is written off (your choice, kept on the record)."
        short = 0
    push_msg = ""
    if short <= TOL:
        st = next((x for x in s["statements"] if x.get("invoice") == invoice_id), None)
        if st:
            push_msg = push_received(s, st, api)
    save(f, s)
    if short > TOL:
        msg += f"\nIt came in {money(short, s['sym'])} short: usually a transfer fee. Ask the student to cover it (the agreement says they bear the fees), or run again with --writeoff to accept it."
    else:
        msg += "\nThat invoice is settled." + (f"\n{push_msg}" if push_msg else "")
    if s["currency"] != "USD":
        msg += f"\nNote: the Cash Desk adds amounts as they are; it does not convert {s['currency']}."
    return msg + "\n"


def set_status(target: str, to: str) -> str:
    f, s = load_student(target)
    if to not in ("active", "paused", "ended"):
        raise ValueError("Status is active, paused or ended.")
    s["status"] = to
    save(f, s)
    return f"{s['name']} is now {to}." + (" Unpaid invoices stay payable." if to == "ended" and any(owed(i) > TOL for i in s["invoices"]) else "") + "\n"


def show(target: str, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    f, s = load_student(target)
    sym = s["sym"]
    L = [f"# {s['name']}: {s['status']}", "", f"{s['percent']:g}% of {s['basis']} earnings, {s['currency']}, through {s['method']}, from {s['start']}."]
    if s.get("program") == "dfy":
        total, qn = dfy_totals(s)
        L.append(f"D'Famocious Year: {qn} of {s['months_target']} qualified months, {money(total, sym)} of {money(s['cap'], sym)} remitted so far.")
    L += ["", "## Months"]
    for st in s["statements"]:
        inv = next((i for i in s["invoices"] if i["id"] == st["invoice"]), None)
        pay = "no invoice (nothing earned)" if not inv else (f"{inv['id']} settled" if owed(inv) <= TOL else f"{inv['id']}: {money(owed(inv), sym)} owed" + (" OVERDUE" if inv["due"] < today.isoformat() else f", due {inv['due']}"))
        L.append(f"- {st['month']}: earned {money(st['earned'], sym)}, cut {money(st['cut'], sym)}; {pay}" + ("" if st["proof"] else "; no proof noted"))
    if not s["statements"]:
        L.append("- nothing reported yet")
    tot_cut = sum(x["cut"] for x in s["statements"])
    got = sum(sum(p["amount"] for p in i["payments"]) for i in s["invoices"])
    L += ["", f"Total cut invoiced {money(tot_cut, sym)}; received {money(got, sym)}; still owed {money(sum(owed(i) for i in s['invoices']), sym)}."]
    return "\n".join(L) + "\n"


def missing_months(s: dict, today: dt.date) -> list[str]:
    """Complete months since the agreement began that should have been reported by now (the 7th of the next month has passed) but were not."""
    if s["status"] != "active":
        return []
    out = []
    y, m = int(s["start"][:4]), int(s["start"][5:7])
    have = {x["month"] for x in s["statements"]}
    while (y, m) < (today.year, today.month):
        k = f"{y:04d}-{m:02d}"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        deadline = dt.date(ny, nm, REPORT_BY_DAY)
        if k not in have and today > deadline:
            out.append(k)
        y, m = ny, nm
    return out


def listing(slug: str, today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    st = all_students(slug)
    if not st:
        return f"No students set up. Add one: python dse.py cut add {slug} --name \"Ada Obi\" --percent 10\n"
    L = [f"{'Student':<24}{'Status':<9}{'%':>4}  {'Invoiced':>10}{'Received':>10}{'Owed':>10}  Needs"]
    tot_i = tot_r = tot_o = 0.0
    for _f, s in st:
        inv = round(sum(x["cut"] for x in s["statements"]), 2)
        rec = round(sum(sum(p["amount"] for p in i["payments"]) for i in s["invoices"]), 2)
        ow = round(sum(owed(i) for i in s["invoices"]), 2)
        tot_i += inv
        tot_r += rec
        tot_o += ow
        miss = missing_months(s, today)
        late = [i for i in s["invoices"] if owed(i) > TOL and i["due"] < today.isoformat()]
        needs = ("report for " + ", ".join(miss[:2]) if miss else "") + ("; " if miss and late else "") + (f"{len(late)} overdue" if late else "")
        L.append(f"{s['name'][:23]:<24}{s['status']:<9}{s['percent']:>4g}  {money(inv, s['sym']):>10}{money(rec, s['sym']):>10}{money(ow, s['sym']):>10}  {needs or '-'}")
    L += ["", f"{len(st)} student(s). Totals (amounts added as they are, not converted): invoiced {money(tot_i)}, received {money(tot_r)}, owed {money(tot_o)}."]
    return "\n".join(L) + "\n"


def attention(slug: str, today: dt.date) -> dict:
    """For the Weekly Review: overdue cut invoices, and students who have not reported when they should have."""
    inv, quiet = [], []
    for _f, s in all_students(slug):
        for i in s["invoices"]:
            if owed(i) > TOL and i["due"] < today.isoformat():
                inv.append({"student": s["name"], "id": i["id"], "owed": owed(i), "sym": s["sym"], "due": i["due"]})
        miss = missing_months(s, today)
        if miss:
            quiet.append({"student": s["name"], "months": miss})
    return {"overdue": inv, "quiet": quiet}
