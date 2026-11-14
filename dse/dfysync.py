"""The bridge between Citadel's DFY Tracker and the Cut Desk.

    python dse.py cut sync <engine> [--auto on|off]            pull every student's filed DFY months from Citadel into the Cut Desk
    python dse.py cut accounts <engine> [--publish]            show (or publish) the accounts students are told to pay into

Students already file their monthly net income in Citadel (/dfy) and pay on /payments. This does the HQ side, so the money is tracked where your books are:
  * each filed month becomes a statement and an invoice (DFY remittance: 20% of net income, capped at $18,000, ending at 12 qualified months)
  * a month the student's Citadel page already shows as paid is recorded as paid here too (history: it is NOT added to the Cash Desk again)
  * when YOU record that the money arrived (`cut paid`), Citadel is told, exactly as the council's "Mark paid" button does it: the pending bank-transfer
    entry succeeds and the DFY month shows paid. A month whose push failed (no internet) is retried at the next sync
  * a student's filed figure that changes after money was recorded is reported to you, never silently rewritten
  * a month the council disputed is listed, not invoiced
Needs your runner connected (Citadel link) and an ADMIN account: every Citadel function checks both.
--auto on makes the runner do this by itself every ten minutes (bridge/dfy_sync.py); the engine it uses is saved in data/dfy-sync.json.

Payout accounts: put the accounts in engines/<engine>/payout-accounts.json (an example is in dse/payout_accounts.example.json: Grey, Payoneer or a bank).
`cut accounts <engine> --publish` replaces what students see on /payments and sign-up. Placeholders in [brackets] are refused, so an unfinished file never goes live.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

from . import cuts
from . import clients as cl
from .common import DATA, ROOT
from .engines import engine_dir, load

CONFIG = DATA / "dfy-sync.json"
EXAMPLE = Path(__file__).with_name("payout_accounts.example.json")
CURRENCIES = ("USD", "NGN")
METHODS = ("grey", "payoneer", "wise", "bank", "other")


def get_api():
    """The runner's Citadel connection (the same token the other tools use), or None when this PC is not connected."""
    runner = ROOT / "bridge" / "runner.py"
    if not runner.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("dse_runner_dfy", runner)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.Api(mod.load_env())
    except Exception:
        return None


def set_auto(slug: str, on: bool) -> str:
    load(slug)
    DATA.mkdir(exist_ok=True)
    if on:
        CONFIG.write_text(json.dumps({"engine": slug}), encoding="utf-8")
        return f"Automatic DFY sync is on for engine {slug}: the runner pulls new months every ten minutes (restart the runner once)."
    CONFIG.unlink(missing_ok=True)
    return "Automatic DFY sync is off."


def auto_engine() -> str:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("engine", "")
    except (OSError, ValueError):
        return ""


def once(f: Path, s: dict, key: str) -> bool:
    """True the first time a notice is raised, and remembers it, so the background sync never repeats itself every ten minutes."""
    seen = s.setdefault("notified", [])
    if key in seen:
        return False
    seen.append(key)
    cuts.save(f, s)
    return True


def find_student(slug: str, user_id: str, email: str) -> tuple[Path, dict] | None:
    for f, s in cuts.all_students(slug):
        if user_id and s.get("citadel_user_id") == user_id:
            return f, s
    for f, s in cuts.all_students(slug):
        if email and (s.get("email") or "").lower() == email.lower():
            return f, s
    return None


def clean_row(r: dict) -> dict | None:
    try:
        month = str(r["period_month"])[:7]
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            return None
        return {"id": str(r["id"]), "user_id": str(r.get("user_id") or ""), "email": (r.get("email") or "").strip().lower(), "name": (r.get("full_name") or "").strip(),
                "month": month, "net": round(float(r["net_income_usd"]), 2), "status": r.get("status") or "submitted", "paid": bool(r.get("remittance_paid"))}
    except (KeyError, TypeError, ValueError):
        return None


def sync(slug: str, months: list[dict], api=None, today: dt.date | None = None) -> str:
    load(slug)
    today = today or dt.date.today()
    rows = [c for c in (clean_row(r) for r in months) if c]
    created, imported, changed, disputed, after_done, errors, pushed, history = [], [], [], [], [], [], [], []
    by_student: dict[str, list[dict]] = {}
    for r in rows:
        by_student.setdefault(r["user_id"] or r["email"], []).append(r)
    for key, ms in by_student.items():
        ms.sort(key=lambda r: r["month"])
        first = ms[0]
        found = find_student(slug, first["user_id"], first["email"])
        label = first["name"] or first["email"] or key[:8]
        if not found:
            if not label or len(label) < 2:
                errors.append(f"a student with no name or email ({key[:8]})")
                continue
            try:
                cuts.add(slug, label[:60], 20, "net", "USD", "grey", first["email"], 7, first["month"] + "-01", today, program="dfy")
            except ValueError as e:
                errors.append(f"{label}: {e}")
                continue
            sslug = cl.slugify(label[:60])
            f = cuts.cuts_dir(slug) / sslug / "student.json"
            s = json.loads(f.read_text(encoding="utf-8"))
            s["citadel_user_id"] = first["user_id"]
            cuts.save(f, s)
            created.append(label)
        else:
            f, s = found
            if first["user_id"] and not s.get("citadel_user_id"):
                s["citadel_user_id"] = first["user_id"]
                cuts.save(f, s)
        target = f"{slug}/{f.parent.name}"
        for r in ms:
            f, s = cuts.load_student(target)
            st = next((x for x in s["statements"] if x.get("citadel_id") == r["id"]), None)
            if r["status"] == "disputed":
                if once(f, s, "dispute:" + r["id"]):
                    disputed.append(f"{label} {r['month']}")
                continue
            if st is None:
                if any(x["month"] == r["month"] for x in s["statements"]):
                    if once(f, s, "dup:" + r["id"]):
                        changed.append(f"{label} {r['month']}: you already entered this month by hand; Citadel has a filing for it too. Left as it is.")
                    continue
                if r["month"] < s["start"][:7]:
                    s["start"] = r["month"] + "-01"
                    cuts.save(f, s)
                try:
                    cuts.report(target, r["month"], r["net"], 0, "Filed by the student in Citadel (DFY tracker)", False, today, source="citadel", citadel_id=r["id"])
                except ValueError as e:
                    if "complete" in str(e):
                        after_done.append(f"{label} {r['month']}")
                    else:
                        errors.append(f"{label} {r['month']}: {e}")
                    continue
                imported.append(f"{label} {r['month']}: net ${r['net']:,.2f}")
                if r["paid"]:
                    f, s = cuts.load_student(target)
                    st = next(x for x in s["statements"] if x.get("citadel_id") == r["id"])
                    inv = next((i for i in s["invoices"] if i["id"] == st["invoice"]), None)
                    if inv:
                        inv["payments"].append({"date": today.isoformat(), "amount": inv["amount"], "from_citadel": True})
                        st["citadel_paid"] = True
                        cuts.save(f, s)
                        history.append(f"{label} {r['month']}")
            elif abs(st["earned"] - r["net"]) > 0.005:
                inv = next((i for i in s["invoices"] if i["id"] == st.get("invoice")), None)
                if inv and cuts.paid_total(inv) > 0:
                    if once(f, s, f"changed:{r['id']}:{r['net']}"):
                        changed.append(f"{label} {r['month']}: the student now files ${r['net']:,.2f}, but you recorded ${st['earned']:,.2f} and money is already on it. Check with them; nothing was changed.")
                else:
                    try:
                        cuts.report(target, r["month"], r["net"], 0, "Filed by the student in Citadel (DFY tracker)", True, today, source="citadel", citadel_id=r["id"])
                        changed.append(f"{label} {r['month']}: the student changed the figure to ${r['net']:,.2f}; the invoice was updated (same number).")
                    except ValueError as e:
                        errors.append(f"{label} {r['month']}: {e}")
            elif r["paid"] and not st.get("citadel_paid"):
                inv = next((i for i in s["invoices"] if i["id"] == st.get("invoice")), None)
                if inv and cuts.owed(inv) > cuts.TOL:
                    inv["payments"].append({"date": today.isoformat(), "amount": cuts.owed(inv), "from_citadel": True})
                    history.append(f"{label} {r['month']}")
                st["citadel_paid"] = True
                cuts.save(f, s)
    # push the months whose "received" could not be sent before
    if api is not None:
        for f, s in cuts.all_students(slug):
            dirty = False
            for st in s["statements"]:
                if st.get("push_pending") and st.get("citadel_id") and not st.get("citadel_paid"):
                    msg = cuts.push_received(s, st, api)
                    dirty = True
                    if st.get("citadel_paid"):
                        pushed.append(f"{s['name']} {st['month']}")
            if dirty:
                cuts.save(f, s)
    return summary(created, imported, history, changed, disputed, after_done, errors, pushed)


def summary(created, imported, history, changed, disputed, after_done, errors, pushed) -> str:
    L = ["# DFY sync", ""]
    if not any((created, imported, changed, disputed, after_done, errors, pushed)):
        return "# DFY sync\n\nNothing new from Citadel.\n"
    if created:
        L.append("New students (DFY agreement starter saved for each): " + ", ".join(created))
    if imported:
        L += ["", f"New months now in the Cut Desk ({len(imported)}):"] + [f"- {x}" for x in imported]
    if history:
        L += ["", "Already shown as paid in Citadel, recorded as paid here (history, not added to the Cash Desk): " + ", ".join(history)]
    if pushed:
        L += ["", "Marked received in Citadel after an earlier failure: " + ", ".join(pushed)]
    if changed:
        L += ["", "Needs a look:"] + [f"- {x}" for x in changed]
    if disputed:
        L += ["", "Disputed by the council, not invoiced: " + ", ".join(disputed)]
    if after_done:
        L += ["", "After the DFY was complete, nothing owed: " + ", ".join(after_done)]
    if errors:
        L += ["", "Could not import:"] + [f"- {x}" for x in errors]
    return "\n".join(L) + "\n"


def run(slug: str, api=None, today: dt.date | None = None) -> str:
    api = api or get_api()
    if api is None:
        raise ValueError("This PC is not connected to Citadel (the runner's token is missing). Start the runner first: see bridge/README.")
    try:
        months = api.rpc("hq_dfy_pull", {}) or []
    except Exception as e:
        raise ValueError(f"Citadel did not answer ({type(e).__name__}: {str(e)[:120]}). The SQL file 20261118140000_dfy_bridge_payout_accounts.sql must be run in Supabase, and the runner's owner must be an admin.") from None
    return sync(slug, months if isinstance(months, list) else [], api, today)


# ------------------------------------------------------------------ payout accounts

def accounts_path(slug: str) -> Path:
    return engine_dir(slug) / "payout-accounts.json"


def validate_accounts(items) -> list[dict]:
    if not isinstance(items, list) or not 1 <= len(items) <= 8:
        raise ValueError("payout-accounts.json is a list of 1 to 8 accounts.")
    out = []
    for i, a in enumerate(items, 1):
        if not isinstance(a, dict):
            raise ValueError(f"Account {i} is not an object.")
        cur = a.get("currency")
        if cur not in CURRENCIES:
            raise ValueError(f"Account {i}: currency is USD or NGN.")
        method = a.get("method", "bank")
        if method not in METHODS:
            raise ValueError(f"Account {i}: method is one of {', '.join(METHODS)}.")
        rec = {"currency": cur, "method": method}
        for k, lo, hi in (("label", 2, 60), ("bank_name", 1, 80), ("account_name", 1, 120), ("account_number", 1, 60)):
            v = str(a.get(k) or "").strip()
            if not lo <= len(v) <= hi:
                raise ValueError(f"Account {i}: {k} is needed ({lo} to {hi} characters).")
            if "[" in v or "]" in v:
                raise ValueError(f"Account {i}: {k} still has a [placeholder]. Fill it in from your own app before publishing.")
            rec[k] = v
        extra = a.get("extra") or []
        if not isinstance(extra, list) or len(extra) > 8:
            raise ValueError(f"Account {i}: extra is a list of up to 8 label/value pairs.")
        clean_extra = []
        for e in extra:
            lab, val = str((e or {}).get("label", "")).strip()[:40], str((e or {}).get("value", "")).strip()[:120]
            if not lab or not val:
                raise ValueError(f"Account {i}: every extra needs a label and a value.")
            if "[" in val or "]" in val:
                raise ValueError(f"Account {i}: an extra still has a [placeholder].")
            clean_extra.append({"label": lab, "value": val})
        rec["extra"] = clean_extra
        note = str(a.get("note") or "").strip()[:300]
        rec["note"] = note
        rec["active"] = bool(a.get("active", True))
        out.append(rec)
    if not any(a["currency"] == "USD" for a in out):
        raise ValueError("Include at least one USD account (DFY remittances are in USD).")
    return out


def accounts(slug: str, publish: bool = False, add_example: bool = False, api=None) -> str:
    load(slug)
    p = accounts_path(slug)
    if add_example:
        if p.exists():
            return f"{p.relative_to(ROOT).as_posix()} already exists; left as it is.\n"
        p.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        return f"Copied the example to engines/{slug}/payout-accounts.json. Fill in the accounts from your own Grey or Payoneer app (never share a password), then: python dse.py cut accounts {slug} --publish\n"
    if not p.exists():
        return f"No payout-accounts.json for engine {slug} yet. Start from the example: python dse.py cut accounts {slug} --example\n"
    try:
        items = validate_accounts(json.loads(p.read_text(encoding="utf-8")))
    except ValueError as e:
        if publish:
            raise
        return f"Not ready to publish: {e}\n"
    lines = [f"payout-accounts.json is valid: {len(items)} account(s)."] + [f"- {a['currency']} {a['label']} ({a['method']}): {a['bank_name']}, {a['account_name']}" for a in items]
    if not publish:
        pub = ""
        api = api or get_api()
        if api is not None:
            try:
                now = api.rpc("hq_get_payout_accounts", {}) or []
                pub = "\nStudents currently see: " + "; ".join(f"{x['currency']} {x['label']}" for x in now) if now else "\nStudents currently see the accounts built into the app."
            except Exception:
                pub = "\n(Could not read what is published: is the SQL run and the runner an admin's?)"
        return "\n".join(lines) + pub + f"\n\nTo show these to students on the payment page: python dse.py cut accounts {slug} --publish\n"
    api = api or get_api()
    if api is None:
        raise ValueError("This PC is not connected to Citadel (the runner's token is missing).")
    try:
        res = api.rpc("hq_set_payout_accounts", {"p_accounts": items})
    except Exception as e:
        raise ValueError(f"Citadel refused: {str(e)[:200]}") from None
    return "\n".join(lines) + f"\n\nPublished {res.get('published', len(items)) if isinstance(res, dict) else len(items)} account(s): students now see them on /payments and the sign-up page.\n"
