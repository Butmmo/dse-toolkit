"""An engine's lists, its tap log and its threads: the data layer under follow-ups, outcomes and the Send Desk sync.

    engines/<slug>/send-lists/<date>.csv              the lists `dse.py daily` builds (first messages)
    engines/<slug>/send-lists/<date>-followups.csv    follow-ups `dse.py followups` plans (touch 2 and 3)
    engines/<slug>/data/log.csv                       one line per tap: Sent, Skipped, Got a reply, Call booked, Won, Lost

The log is the only source of truth about what happened. A row counts as sent ONLY when you (or the phone) marked it
Sent: no guessing from dates, so every number in your results is real. A "thread" is one business in one engine,
whatever number of lists it appears on.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from .common import ROOT, read_csv

ENGINES = ROOT / "engines"
STATUSES = ("to do", "sent", "skipped", "replied", "booked", "won", "lost")
LOG_COLS = ["logged_at", "list_date", "source", "row_id", "name", "channel", "touch", "status", "category", "reply", "next_step", "value"]
ENDS_THREAD = {"replied", "booked", "won", "lost", "skipped"}      # a thread with any of these needs no more follow-ups
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def domain(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (url or "").lower().strip())
    return u.split("/")[0]


def ig_handle(s: str) -> str:
    m = re.search(r"instagram\.com/([\w.]+)", s or "", re.I) or re.match(r"^@([\w.]+)$", (s or "").strip())
    return m.group(1).lower() if m else ""


def thread_key(row: dict) -> str:
    """One business = one thread: by website domain, else Instagram handle, else name (a trailing (label) is ignored)."""
    d = domain(row.get("website", ""))
    if d:
        return "d:" + d
    h = ig_handle(row.get("instagram", "")) or ig_handle(row.get("where", ""))
    if h:
        return "i:" + h
    return "n:" + norm(re.sub(r"\s*\([^)]*\)\s*$", "", row.get("business") or row.get("name") or ""))


def engine_dir(slug: str) -> Path:
    return ENGINES / slug


def log_path(slug: str) -> Path:
    return engine_dir(slug) / "data" / "log.csv"


def read_log(slug: str) -> list[dict]:
    p = log_path(slug)
    if not p.exists():
        return []
    try:
        return read_csv(p)
    except Exception:
        return []


def append_events(slug: str, events: list[dict]) -> int:
    """Add taps to the engine's log (header written once). Duplicate lines (same time, row and status) are skipped."""
    if not events:
        return 0
    p = log_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    have = {(r["logged_at"], r["source"], r["row_id"], r["status"]) for r in read_log(slug)}
    new = [e for e in events if (e.get("logged_at", ""), e.get("source", ""), str(e.get("row_id", "")), e.get("status", "")) not in have]
    if not new:
        return 0
    fresh = not p.exists() or p.stat().st_size == 0
    with p.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore")
        if fresh:
            w.writeheader()
        for e in new:
            w.writerow({**{c: "" for c in LOG_COLS}, **{k: ("" if v is None else v) for k, v in e.items()}, "row_id": str(e.get("row_id", ""))})
    return len(new)


def local_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load_lists(slug: str) -> list[dict]:
    """Every row on the engine's lists (not drafts), with _source (file stem), _date, _followup and touch filled in."""
    rows = []
    d = engine_dir(slug) / "send-lists"
    if not d.exists():
        return rows
    for p in sorted(d.glob("*.csv")):
        m = DATE.match(p.stem)
        if not m:
            continue
        try:
            file_rows = read_csv(p)
        except Exception:
            continue
        for r in file_rows:
            r = dict(r)
            r["_source"], r["_date"] = p.stem, m.group(1)
            r["_followup"] = p.stem.endswith("-followups")
            try:
                r["touch"] = int(r.get("touch") or (2 if r["_followup"] else 1))
            except ValueError:
                r["touch"] = 2 if r["_followup"] else 1
            r["_row_id"] = str(r.get("row", "") or "")
            r["_thread"] = r.get("thread") or thread_key(r)
            rows.append(r)
    return rows


def history(slug: str) -> dict[tuple[str, str], list[dict]]:
    """(source, row_id) -> that row's taps, oldest first."""
    out: dict[tuple[str, str], list[dict]] = {}
    for i, e in enumerate(read_log(slug)):
        e["_i"] = i
        out.setdefault((e.get("source", ""), str(e.get("row_id", ""))), []).append(e)
    for v in out.values():
        v.sort(key=lambda e: (e.get("logged_at", ""), e["_i"]))
    return out


def latest(events: list[dict] | None) -> dict | None:
    return events[-1] if events else None


def is_out_of_office(e: dict | None) -> bool:
    return bool(e) and e.get("status") == "replied" and (e.get("category") or "") == "out of office"


def status_of_row(hist: dict, row: dict) -> str:
    """The row's current status. An out-of-office auto-reply is not an answer: the row stays 'sent'."""
    e = latest(hist.get((row["_source"], row["_row_id"])))
    if not e:
        return "to do"
    return "sent" if is_out_of_office(e) else e["status"]


def sent_on(hist: dict, row: dict) -> str:
    """The date this row was first marked Sent ('' if never): taken from the tap, in this PC's local time."""
    for e in hist.get((row["_source"], row["_row_id"]), []):
        if e["status"] in ("sent", "replied", "booked", "won", "lost") and e.get("logged_at"):
            return e["logged_at"][:10]
    return ""


def threads(slug: str) -> dict[str, dict]:
    """thread key -> {rows, first (the touch-1 row), name}. Rows are in list-date order."""
    out: dict[str, dict] = {}
    for r in load_lists(slug):
        t = out.setdefault(r["_thread"], {"rows": [], "first": None})
        t["rows"].append(r)
    for t in out.values():
        t["rows"].sort(key=lambda r: (r["_date"], r["touch"], r["_source"]))
        firsts = [r for r in t["rows"] if r["touch"] == 1 and not r["_followup"]]
        t["first"] = firsts[0] if firsts else None
        t["name"] = (t["first"] or t["rows"][0]).get("business") or (t["first"] or t["rows"][0]).get("name") or ""
    return out
