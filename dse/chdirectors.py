"""Directors from Companies House: the owner's first and last name for a UK business, from the official register.

    python dse.py directors <list.csv> [--company-column NAME] [--city-column NAME] [--max N]     adds the director columns to a list
    python dse.py grid people <grid> --companies-house                                              the same, for a Ledger grid (Name source column says where a name came from)

Why: small UK trades rarely name their owner on their website (5 of 36 tree surgeons did), but every UK company has a public register entry that lists its directors. For each business
we search the register by name (and town, when we have it), accept only a match we are confident of (active company, same name apart from Ltd/Limited, and not two different companies
that fit equally well), and take the longest-serving active human director: "SMITH, John Michael" becomes first name John, last name Smith. A sole trader or partnership is not on the
register, and a company whose name differs from its trading name is not matched: those rows stay empty rather than guessed.

Needs your own free Companies House API key (https://developer.company-information.service.gov.uk/ : register, make an application, add a REST key). Set it once, on this PC only:
    setx COMPANIES_HOUSE_API_KEY "your-key"     (then open a new terminal; the HQ runner sees it after a restart)
The key is read from that environment variable (or your Windows user environment) and is only ever sent to Companies House. It is never printed, saved in a list or sent to Citadel.
Companies House allows 600 requests per 5 minutes; this module keeps to about one request every 0.6 seconds and waits if it is told to slow down. Two requests per business at most.
Director names are public register data (Open Government Licence); using them for B2B outreach is your responsibility under UK GDPR (legitimate interest, a clear opt-out, honour objections).
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time

BASE = "https://api.company-information.service.gov.uk"
ENV = "COMPANIES_HOUSE_API_KEY"
PACE = 0.6
LEGAL = {"ltd", "limited", "llp", "plc", "the", "and", "company", "co", "uk", "inc", "lp", "cic", "cio"}
HUMAN_ROLES = {"director", "llp-member", "llp-designated-member"}
HONORIFICS = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "dame", "rev", "lord", "lady"}
COLUMNS = ["director_first", "director_last", "director_role", "ch_company", "ch_number", "ch_match"]
HELP = ("Companies House needs your own free API key. Register at https://developer.company-information.service.gov.uk/ , make an application, add a REST key, "
        f"then run:  setx {ENV} \"your-key\"  and open a new terminal.")


def api_key() -> str:
    k = os.environ.get(ENV, "").strip()
    if not k and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                k = str(winreg.QueryValueEx(reg, ENV)[0]).strip()
        except (OSError, ImportError):
            k = ""
    return k


class Client:
    """The register's REST API: one request at a time, paced, one retry when it says slow down. http(path, params) -> (status, json) can be replaced in tests."""

    def __init__(self, key: str = "", http=None, sleep=time.sleep):
        self.key, self.http, self.sleep = key, http, sleep
        self._last = 0.0
        self._lock = threading.Lock()
        self.calls = 0

    def get(self, path: str, params: dict | None = None):
        with self._lock:
            wait = PACE - (time.time() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.time()
        for attempt in (0, 1):
            self.calls += 1
            status, data, retry = self._fetch(path, params or {})
            if status == 429 and attempt == 0:
                self.sleep(min(retry, 60))
                continue
            return status, data
        return 429, {}

    def _fetch(self, path: str, params: dict):
        if self.http:
            r = self.http(path, params)
            return (r[0], r[1], 5)
        import requests
        resp = requests.get(BASE + path, params=params, auth=(self.key, ""), timeout=20)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        return resp.status_code, data, int(resp.headers.get("Retry-After", "5") or 5)


# ------------------------------------------------------------------ pure matching

def norm_tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower().replace("&", " and ")) if t not in LEGAL]


def name_score(a: str, b: str) -> float:
    ta, tb = set(norm_tokens(a)), set(norm_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def choose_company(items: list[dict], name: str, city: str = "") -> tuple[dict | None, str]:
    """(the matching company, 'exact' or 'close') or (None, why). Only active companies; the name must match (apart from Ltd and Limited); when two different companies fit equally well,
    the town decides, and if it cannot, nothing is returned: a wrong owner is worse than no owner."""
    ok = []
    for it in items or []:
        if str(it.get("company_status", "")).lower() != "active":
            continue
        s = name_score(name, it.get("title", ""))
        sub = set(norm_tokens(name)) <= set(norm_tokens(it.get("title", ""))) and len(norm_tokens(name)) >= 2
        if s >= 0.75 or (sub and s >= 0.6):
            ok.append((s, it))
    if not ok:
        return None, "no company of that name"
    top = max(s for s, _ in ok)
    best = [it for s, it in ok if s >= top - 0.01]
    if len(best) > 1 and city:
        c = city.lower().strip()
        local = [it for it in best if c in (str(it.get("address_snippet", "")) + " " + str((it.get("address") or {}).get("locality", ""))).lower()]
        if len(local) >= 1:
            best = local[:1] if len(local) == 1 else local
    if len(best) > 1:
        return None, "more than one company fits"
    it = best[0]
    return it, "exact" if top >= 0.99 else "close"


def ch_name(raw: str) -> tuple[str, str]:
    """'SMITH, John Michael' -> ('John', 'Smith'); 'MC DONALD, Ann' -> ('Ann', 'Mc Donald'); an honorific in the forenames is dropped."""
    raw = (raw or "").strip()
    if "," in raw:
        sur, fore = raw.split(",", 1)
    else:
        parts = raw.split()
        sur, fore = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (raw, "")
    toks = [t for t in re.split(r"\s+", fore.strip()) if t and t.lower().strip(".") not in HONORIFICS]
    first = toks[0].title() if toks else ""
    last = " ".join(w.title() for w in sur.split())
    return first, last


def pick_director(officers: list[dict]) -> dict | None:
    """The longest-serving active human director (the founder, usually). A resigned officer, a company, a secretary or a nominee is never picked."""
    live = [o for o in officers or [] if not o.get("resigned_on") and str(o.get("officer_role", "")).lower() in HUMAN_ROLES]
    if not live:
        return None
    live.sort(key=lambda o: (o.get("appointed_on") or "9999", o.get("name", "")))
    o = live[0]
    first, last = ch_name(o.get("name", ""))
    if not first or not last:
        return None
    return {"first": first, "last": last, "role": str(o.get("officer_role", "")).replace("-", " "), "name": o.get("name", "")}


# ------------------------------------------------------------------ lookups

def director_for(client: Client, business: str, city: str = "") -> dict:
    """{'first','last','role','company','number','match'} or {'why': ...} for one business."""
    business = re.sub(r"\s+", " ", business or "").strip()
    if len(norm_tokens(business)) < 1:
        return {"why": "no business name"}
    status, data = client.get("/search/companies", {"q": business, "items_per_page": 8})
    if status == 401:
        raise RuntimeError("Companies House refused the key (401). " + HELP)
    if status != 200:
        return {"why": f"search failed (HTTP {status})"}
    company, how = choose_company(data.get("items") or [], business, city)
    if not company:
        return {"why": how}
    number = company.get("company_number", "")
    status, off = client.get(f"/company/{number}/officers", {"items_per_page": 35})
    if status != 200:
        return {"why": f"officers lookup failed (HTTP {status})"}
    d = pick_director(off.get("items") or [])
    if not d:
        return {"why": "no active human director listed"}
    return {"first": d["first"], "last": d["last"], "role": d["role"], "company": company.get("title", ""), "number": number, "match": how}


def need_key() -> str:
    k = api_key()
    if not k:
        raise ValueError(HELP)
    return k


# ------------------------------------------------------------------ a CSV list

def file(src: str, company_col: str = "", city_col: str = "", max_rows: int = 200, out: str = "", client: Client | None = None) -> str:
    from .common import out_path, read_csv, write_csv
    from pathlib import Path
    rows = read_csv(src)
    if not rows:
        raise ValueError("That list is empty.")
    heads = list(rows[0])
    low = {h.lower().strip(): h for h in heads}
    comp = company_col or next((low[k] for k in ("company", "business", "business name", "company name", "name") if k in low), "")
    if not comp or comp not in heads:
        raise ValueError("I could not find the business name column. Name it with --company-column. Columns: " + ", ".join(heads[:12]) + ".")
    city = city_col or next((low[k] for k in ("city", "town", "search_city") if k in low), "")
    client = client or Client(need_key())
    found = 0
    done = 0
    for r in rows:
        for c in COLUMNS:
            r.setdefault(c, "")
        if done >= max_rows:
            r["ch_match"] = "not looked up (over the limit)"
            continue
        if not (r.get(comp) or "").strip():
            continue
        done += 1
        d = director_for(client, r[comp], r.get(city, "") if city else "")
        if d.get("first"):
            found += 1
            r.update(director_first=d["first"], director_last=d["last"], director_role=d["role"], ch_company=d["company"], ch_number=d["number"], ch_match=d["match"])
        else:
            r["ch_match"] = d.get("why", "")
        if done % 10 == 0:
            print(f"  {done} looked up, {found} directors found", file=sys.stderr, flush=True)
    dst = out or str(out_path("directors", Path(src).stem))
    write_csv(dst, rows)
    print(f"{done} businesses looked up in the register, {found} with a director ({round(100 * found / done) if done else 0}%), {client.calls} requests -> {dst}")
    return dst
