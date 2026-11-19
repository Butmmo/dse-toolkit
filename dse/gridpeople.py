"""Find the first name, last name and work email of the person behind each business in an existing grid.

    python dse.py grid people <grid> [--from <website column>] [--mode empty|all] [--limit N] [--guess] [--dry]

Works on a grid you already have in your Ledgers (the one a list was sent to with `grid push`, or any grid with a website column). For every row it reads the business's own
public website (the same free, polite reader as Lead enrichment: robots.txt respected, a short list of pages, no logged-in scraping) and writes four cells:

  First name, Last name   the most senior person the site names (owner, founder, director ...), split into a first and a last name
  Work email              an address on the business's own domain, the person's own when the site shows one, else the business's general one (info@, office@)
  Email type              personal (matches the person) | role address (info@, office@) | personal mailbox (gmail and the like, common with small trades) | guess

Columns the grid does not have yet are added (First name, Last name, Work email, Email type); columns it already has, under those or similar names, are used. A cell that already holds a
value is never replaced unless you pick mode all. --guess adds a guessed address (first.last@their-domain, only when the domain receives mail and the site showed no personal address), marked
"guess" in Email type: check it before sending. Without --guess nothing is ever guessed. Answers are saved in small batches, so Stop keeps what is done; it writes only into those cells of
YOUR grid, through this PC's own connection. Needs this PC connected to Citadel and the grid database files (20261213090000_hq_grids.sql, 20261224090000_grid_run_column.sql).
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import sys
import time

from . import gridpush
from .gridrun import read_rows, save_cells

BATCH = 10
WORKERS = 4
MAX_ROWS = 5000
HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "mx", "prof", "professor", "sir", "dame", "rev", "reverend", "lord", "lady"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "dds", "dmd", "mba", "cpa", "esq", "mbe", "obe", "cbe", "frics", "mrics", "ceng"}
WEBSITE_NAMES = {"website", "site", "url", "web", "domain", "web site", "website url", "web address", "company website"}
FIRST_NAMES = {"first name", "firstname", "first", "given name", "forename"}
LAST_NAMES = {"last name", "lastname", "last", "surname", "family name"}
EMAIL_NAMES = {"work email", "business email", "work e mail", "company email", "email", "email address", "e mail"}
TYPE_NAMES = {"email type", "email kind", "work email type"}
SOURCE_NAMES = {"name source", "source of name", "name found by"}
COMPANY_NAMES = {"company", "business", "business name", "company name", "name", "organisation", "organization"}
CITY_NAMES = {"city", "town", "search city", "location"}
ADDRESS_NAMES = {"address", "full address", "street address"}
NEW = (("first", "First name", "text", FIRST_NAMES), ("last", "Last name", "text", LAST_NAMES), ("email", "Work email", "email", EMAIL_NAMES), ("type", "Email type", "text", TYPE_NAMES))


def split_name(full: str) -> tuple[str, str]:
    """'Dr. Mary Ann Smith, MBA' -> ('Mary', 'Smith'); 'Owen Hart' -> ('Owen', 'Hart'); a single word is a first name only. A middle initial is dropped."""
    toks = [t for t in re.split(r"[\s,]+", (full or "").strip()) if t]
    toks = [t for t in toks if t.lower().strip(".") not in HONORIFICS and t.lower().strip(".") not in SUFFIXES]
    toks = [t.strip(".,") for i, t in enumerate(toks) if i == 0 or not re.fullmatch(r"[A-Za-z]\.?", t)]      # a middle initial is dropped, a first-name initial is kept
    toks = [t for t in toks if t]
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0], ""
    return toks[0], toks[-1]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def own_domain(email: str, domain: str) -> bool:
    d = email.lower().rpartition("@")[2]
    dom = (domain or "").lower().removeprefix("www.")
    return bool(dom) and (d == dom or d.endswith("." + dom) or dom.endswith("." + d))


def pick_work_email(site: dict, first: str, last: str, guess: bool = False) -> tuple[str, str]:
    """(email, type) for one site: the person's own address first, then any personal address on the domain, then the business's general one, then (only if asked) a guess."""
    domain = (site or {}).get("domain", "")
    emails = [e for e in (site or {}).get("emails") or [] if isinstance(e, dict) and e.get("email")]
    mine = [e for e in emails if own_domain(e["email"], domain)]
    f, l = _slug(first), _slug(last)

    def about_person(e: dict) -> bool:
        loc = _slug(e["email"].partition("@")[0])
        return bool(loc) and e.get("kind") == "personal" and ((len(f) >= 3 and f in loc) or (len(l) >= 3 and l in loc) or (f and l and loc == f[0] + l))

    for e in mine:
        if about_person(e):
            return e["email"], "personal"
    for e in mine:
        if e.get("kind") == "personal":
            return e["email"], "personal"
    for e in mine:
        return e["email"], "role address"
    for e in emails:
        if e.get("kind") == "freemail":
            return e["email"], "personal mailbox"
    if guess and f and l and (site or {}).get("mx") == "yes":
        g = [x for x in (site or {}).get("guesses") or [] if x.lower().startswith(f + "." + l + "@")]
        if g:
            return g[0], "guess"
    return "", ""


def person_of(site: dict) -> tuple[str, str]:
    people = (site or {}).get("people") or []
    return split_name(str(people[0].get("name", ""))) if people and isinstance(people[0], dict) else ("", "")


def ch_guess(first: str, last: str, domain: str, mx=None) -> str:
    """first.last@domain for a name from the register, only when the domain receives mail (the site showed no address of the person's own)."""
    from . import enrich
    f, l = _slug(first), _slug(last)
    if not (f and l and domain):
        return ""
    ok = (mx or enrich.has_mx)(domain)
    return f"{f}.{l}@{domain}" if ok == "yes" else ""


def find_columns(columns: list[dict], from_ref: str = "") -> dict:
    """{'website': column, 'first'|'last'|'email'|'type': column or None}. The website column is the one named, else the first that looks like one."""
    by = {}
    if from_ref:
        by["website"] = next((c for c in columns if c["key"] == from_ref or gridpush.norm(c["label"]) == gridpush.norm(from_ref)), None)
        if by["website"] is None:
            raise ValueError(f"The grid has no column called '{from_ref}'. Its columns: " + ", ".join(c["label"] for c in columns[:12]) + ".")
    else:
        by["website"] = next((c for c in columns if gridpush.norm(c["label"]) in WEBSITE_NAMES), None) or next((c for c in columns if c["type"] == "url"), None)
        if by["website"] is None:
            raise ValueError("I could not find the website column of that grid. Name it with --from. Its columns: " + ", ".join(c["label"] for c in columns[:12]) + ".")
    for k, _label, _type, names in NEW:
        by[k] = next((c for c in columns if gridpush.norm(c["label"]) in names and c["key"] != by["website"]["key"]), None)
    by["source"] = next((c for c in columns if gridpush.norm(c["label"]) in SOURCE_NAMES), None)
    by["company"] = next((c for c in columns if gridpush.norm(c["label"]) in COMPANY_NAMES and c["key"] != by["website"]["key"]), None)
    by["city"] = next((c for c in columns if gridpush.norm(c["label"]) in CITY_NAMES), None)
    by["address"] = next((c for c in columns if gridpush.norm(c["label"]) in ADDRESS_NAMES), None)
    return by


def cell(col: dict | None, data: dict) -> str:
    v = (data or {}).get(col["key"]) if col else None
    return "" if v is None or v is False else str(v).strip()


def read_site(website: str) -> dict:
    from . import enrich
    return enrich.enrich_site(website, render=False)


def run(grid_ref: str, from_ref: str = "", mode: str = "empty", limit: int = 0, guess: bool = False, dry: bool = False, say=print, api=None, site=None,
        companies_house: bool = False, ch=None, mx=None) -> str:
    if mode not in ("empty", "all"):
        raise ValueError("mode must be empty or all.")
    api = api or gridpush.connect()
    if api is None:
        raise ValueError("This PC is not connected to Citadel yet (run the HQ Tools setup first).")
    grid = gridpush.resolve_grid(gridpush._grids(api), grid_ref)
    columns = gridpush.columns_of(grid.get("doc"))
    cols = find_columns(columns, from_ref)
    missing = [(k, label, ctype) for k, label, ctype, _n in NEW if cols[k] is None]
    if companies_house:
        if cols["company"] is None:
            raise ValueError("To use Companies House I need the business name column (called Company, Business or Name). Its columns: " + ", ".join(c["label"] for c in columns[:12]) + ".")
        if cols["source"] is None:
            missing.append(("source", "Name source", "text"))
    head = f"{grid.get('workbook', '')} / {grid['name']}: website column '{cols['website']['label']}'."
    rows = read_rows(api, grid["id"])
    todo = []
    for r in rows:
        d = r.get("data") or {}
        web = cell(cols["website"], d)
        if not web:
            continue
        if mode == "all" or any(cols[k] is None or not cell(cols[k], d) for k, *_ in NEW[:3]):
            todo.append(r)
    skipped = len(rows) - len(todo)
    if limit:
        todo = todo[:limit]
    lines = [head, f"{len(todo)} of {len(rows)} rows to read ({'every row with a website' if mode == 'all' else 'rows with a website and an empty first name, last name or work email'}); {skipped} skipped."]
    if missing:
        lines.append(("Would add columns: " if dry else "Adding columns: ") + ", ".join(label for _k, label, _t in missing) + ".")
    if dry:
        lines.append("Dry run: no website was read and nothing was saved.")
        return "\n".join(lines) + "\n"
    if not todo:
        lines.append("Nothing to do.")
        return "\n".join(lines) + "\n"
    if missing:
        res = api.rpc("hq_grid_add_columns", {"p_grid": grid["id"], "p_cols": [{"label": label, "type": ctype} for _k, label, ctype in missing]}, tries=2) or []
        for (k, label, ctype), r in zip(missing, res):
            cols[k] = {"key": r["key"], "label": r.get("label", label), "type": r.get("type", ctype)}
        if any(cols[k] is None for k, *_ in NEW) or (companies_house and cols["source"] is None):
            raise RuntimeError("The grid did not accept the new columns.")
    for ln in lines:
        say(ln)
    site = site or read_site
    if companies_house and ch is None:
        from . import chdirectors
        ch = chdirectors.Client(chdirectors.need_key())
    ch_found = 0
    cache: dict[str, dict] = {}
    total = len(todo)
    done = names = emails = failed = 0
    kinds: dict[str, int] = {}
    pending: list[dict] = []

    def flush() -> None:
        nonlocal pending, failed
        if not pending:
            return
        try:
            save_cells(api, grid["id"], pending)
        except Exception:
            for u in pending:
                try:
                    save_cells(api, grid["id"], [u])
                except Exception:
                    failed += 1
        pending = []

    def read(r: dict):
        web = cell(cols["website"], r.get("data") or {})
        try:
            return r, (cache[web] if web in cache else cache.setdefault(web, site(web))), ""
        except Exception as e:                    # one unreachable site must not stop the rest
            return r, {}, str(e)[:120]

    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for r, s, err in ex.map(read, todo):
            d = r.get("data") or {}
            first, last = person_of(s)
            source = "website" if first and last else ""
            if companies_house and not (first and last) and not (cell(cols["first"], d) and cell(cols["last"], d)):
                from . import chdirectors
                try:
                    res = chdirectors.director_for(ch, cell(cols["company"], d), cell(cols["city"], d), cell(cols.get("address"), d))
                except RuntimeError:
                    raise
                except Exception as e:                # one failed lookup must not stop the run
                    res = {"why": str(e)[:80]}
                if res.get("first"):
                    first, last, ch_found = res["first"], res["last"], ch_found + 1
                    source = f"Companies House: {res['company']} ({res['number']})"
            email, kind = pick_work_email(s, first or cell(cols["first"], d), last or cell(cols["last"], d), guess)
            if guess and not email and source.startswith("Companies House") and (s or {}).get("domain"):
                g = ch_guess(first, last, s["domain"], mx)
                if g:
                    email, kind = g, "guess"
            out: dict = {}
            for k, v in (("first", first), ("last", last), ("email", email), ("type", kind)):
                if v and (mode == "all" or not cell(cols[k], d)):
                    out[cols[k]["key"]] = v
            if source and cols.get("source") and cols["first"]["key"] in out:          # the source of the name that was just written
                out[cols["source"]["key"]] = source
            if first or last:
                names += 1
            if email:
                emails += 1
                kinds[kind] = kinds.get(kind, 0) + 1
            if err:
                failed += 1
            if out:
                pending.append({"id": r["id"], "cells": out})
            done += 1
            if len(pending) >= BATCH:
                flush()
            if done % 3 == 0 or done == total:
                say(f"PROGRESS {done}/{total} failed {failed} skipped {skipped}")
    flush()
    say(f"PROGRESS {done}/{total} failed {failed} skipped {skipped}")
    detail = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
    return (f"FINISHED {done} rows read: {names} with a first and last name" + (f" ({ch_found} from Companies House)" if companies_house else "") + f", {emails} with a work email" + (f" ({detail})" if detail else "") + f", {failed} failed, {skipped} skipped"
            + ("" if guess else ". No addresses were guessed (add --guess to also get likely addresses, marked guess)") + ".\n")


def cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="dse.py grid people")
    ap.add_argument("grid")
    ap.add_argument("--from", dest="from_ref", default="", help="the website column (found automatically when it is called Website, URL or Domain)")
    ap.add_argument("--mode", default="empty", choices=["empty", "all"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--guess", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--companies-house", action="store_true", dest="companies_house", help="UK: where the website names nobody, look the business up in the Companies House register for its director (needs your free API key)")
    a = ap.parse_args(argv)
    try:
        print(run(a.grid, a.from_ref, a.mode, a.limit, a.guess, a.dry, say=lambda m: print(m, flush=True), companies_house=a.companies_house), end="")
        return 0
    except (ValueError, RuntimeError) as e:
        msg = str(e)
        print("grid people: " + ("the database update 20261224090000_grid_run_column.sql has not been run yet (ask the super admin)" if "hq_grid_" in msg and "function" in msg.lower() else msg[:300]))
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
