"""Outreach Pack: a 14-day touch plan and a mail-merge file for your own sending tool. It sends nothing.

    python dse.py outreach <engine|path-to-list> [--door review|inquiry] [--start 2026-12-01] [--name "Your Name"] [--address "Your postal address"]

It takes an engine's newest send list (or one list you name) and writes two files into engines/<engine>/outreach/:
  * <start>-<door>-mailmerge.csv      one row per business you can email: the address, the name, and the whole email sequence
                                      (subject_1, body_1, send_on_1 ... ) with the send dates already worked out. Load it into a
                                      Gmail mail-merge or your sending tool. YOU press start, and you press every send.
  * <start>-<door>-touch-calendar.csv one row per touch per business over 14 days: the warm comment the day before, the emails,
                                      the likes and replies, the call. The same plan as the Warm Desk tab in Citadel.

Rules it keeps:
  * rows on your do-not-contact list, already contacted, or listed twice are left out (and listed in the summary)
  * rows with no valid email address get the social and call touches but no email
  * a row is marked ready=no when anything is still missing (your sender name, your postal address, the gap line, or, for the Inquiry door,
    the date and result of your Reply Test): fill the gap in the list, or pass --name and --address
  * every email ends with your name, your postal address and an easy way to say no
  * Sundays are skipped; the warm comment goes the day before the first email
  * nothing is ever sent for you. The wording is in dse/outreach_templates.json (copy it to engines/<engine>/outreach-templates.json to change it)

Run 'python dse.py preflight <engine> --domain yourdomain.com' before you load the file: it checks the list and your sending domain.
This is deliverability and good-manners guidance, not legal advice.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from . import preflight as pf
from .common import write_csv
from .engines import engine_dir, load
from .followups import greeting

HERE = Path(__file__).resolve().parent
DOORS = ("review", "inquiry")
BLOCK_WORDS = ("do-not-contact", "already contacted", "appears twice", "consent was withdrawn")


class _Missing(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def templates(slug: str) -> dict:
    mine = engine_dir(slug) / "outreach-templates.json"
    p = mine if mine.exists() else HERE / "outreach_templates.json"
    return json.loads(p.read_text(encoding="utf-8"))


def fill(text: str, vals: dict) -> str:
    """Fill {fields}; a field with no value keeps its braces so the row is marked not ready (never guessed)."""
    try:
        return text.format_map(_Missing(vals)).strip()
    except (ValueError, IndexError):
        return text


def first_day(start: str | None) -> dt.date:
    d = dt.date.fromisoformat(start) if start else dt.date.today() + dt.timedelta(days=1)
    return d + dt.timedelta(days=1) if d.weekday() == 6 else d


def day_date(day0: dt.date, offset: int) -> dt.date:
    """Sundays are skipped: a day before the start moves back to Saturday, a later day forward to Monday."""
    d = day0 + dt.timedelta(days=offset)
    if d.weekday() == 6:
        d += dt.timedelta(days=-1 if offset < 0 else 1)
    return d


def clean_business(row: dict) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", row.get("business") or row.get("name") or "").strip() or "your business"


def recipient(row: dict) -> str:
    ch = (row.get("channel") or "").strip()
    return ((row.get("where") if ch == "Email" else row.get("email")) or "").strip()


def reach_for(row: dict) -> str:
    """Where the social touches happen: the Instagram or Facebook page on the list, else the business's own website."""
    return (row.get("instagram") or row.get("facebook") or row.get("website") or "").strip()


def touch_id(date: str, business: str, channel: str, day: int) -> str:
    """A short id that stays the same when the pack is rebuilt, so a tap on the phone still finds its row."""
    return hashlib.sha1(f"{date}|{business}|{channel}|{day}".encode("utf-8")).hexdigest()[:10]


def build(target: str, door: str = "", start: str | None = None, sender: str = "", address: str = "", write: bool = True) -> dict:
    slug, path = pf.find_list(target)
    cfg = load(slug)
    door = (door or cfg.get("door") or "review").strip().lower()
    if door not in DOORS:
        raise ValueError(f"The door is 'review' or 'inquiry', not '{door}'.")
    tpl = templates(slug)
    chk = pf.check_list(slug, path)
    rows, issues = chk["rows"], chk["issues"]
    sender = (sender or cfg.get("sender_name") or "").strip()
    postal = (address or cfg.get("postal_address") or "").strip()
    day0 = first_day(start)
    emails, plan = tpl["emails"][door], tpl["plan"][door]
    defaults = tpl.get("defaults", {})
    footer_t = tpl["footer"]

    out = {"slug": slug, "list": path, "door": door, "start": day0, "left_out": [], "no_email": [], "not_ready": [], "merge": [], "calendar": [], "files": []}
    for i, r in enumerate(rows):
        biz = clean_business(r)
        reasons = [t for lvl, t in issues.get(i, []) if lvl == "block" and any(w in t for w in BLOCK_WORDS)]
        if reasons:
            out["left_out"].append((biz, reasons[0]))
            continue
        email = recipient(r)
        has_email = bool(pf.EMAIL.match(email))
        if not has_email:
            out["no_email"].append(biz)
        vals = {
            "hi": greeting(r), "business": biz, "city": r.get("city", ""),
            "gap_line": (r.get("gap_used") or r.get("gap_line") or "").strip().rstrip(".") or "{gap_line}",
            "competitor": (r.get("competitor") or defaults.get("competitor", "")).strip(),
            "service": (r.get("service") or defaults.get("service", "")).strip(),
            "sender": sender or "{sender}", "postal": postal or "{postal}",
            "tested_on": (r.get("tested_on") or "").strip() or "{tested_on}",
            "reply_note": (r.get("reply_note") or "").strip() or "{reply_note}",
        }
        footer = fill(footer_t, vals)
        merged = {"ready": "yes", "email": email if has_email else "", "first_name": (r.get("host") or "").split(" ")[0], "business": biz, "city": vals["city"]}
        missing: set[str] = set()
        for n, e in enumerate(emails, 1):
            sub, body = fill(e["subject"], vals), fill(e["body"], vals) + "\n\n" + footer
            missing |= set(re.findall(r"\{([a-z_]+)\}", sub + " " + body))
            merged[f"subject_{n}"], merged[f"body_{n}"] = sub, body
            merged[f"send_on_{n}"] = day_date(day0, next(p["day"] for p in plan if p.get("email") == n)).isoformat()
        if missing:
            merged["ready"] = "no"
            out["not_ready"].append((biz, sorted(missing)))
        if has_email:
            merged["variants"] = ",".join(e["variant"] for e in emails)
            out["merge"].append(merged)
        for p in plan:
            if p["channel"] == "email" and not has_email:
                continue
            n = p.get("email")
            # an email touch carries the real email (subject and body) so it can be copied on the phone; the others carry the instruction
            text = (f"Subject: {merged.get(f'subject_{n}', '')}\n\n{merged.get(f'body_{n}', '')}" if n else p["action"])
            date = day_date(day0, p["day"]).isoformat()
            out["calendar"].append({"date": date, "day": p["day"], "business": biz, "city": vals["city"], "channel": p["channel"],
                                    "where": email if p["channel"] == "email" else reach_for(r), "action": p["action"], "draft": text, "done": "",
                                    "door": door, "row_id": touch_id(date, biz, p["channel"], p["day"])})
    out["calendar"].sort(key=lambda c: (c["date"], c["business"]))
    if write:
        d = engine_dir(slug) / "outreach"
        stem = f"{day0.isoformat()}-{door}"
        cols = ["ready", "email", "first_name", "business", "city"] + [f"{k}_{n}" for n in range(1, len(emails) + 1) for k in ("subject", "body", "send_on")]
        if out["merge"]:
            write_csv(d / f"{stem}-mailmerge.csv", out["merge"], first=cols)
            out["files"].append(d / f"{stem}-mailmerge.csv")
        if out["calendar"]:
            write_csv(d / f"{stem}-touch-calendar.csv", out["calendar"], first=["date", "day", "business", "city", "channel", "where", "action", "draft", "done", "door", "row_id"])
            out["files"].append(d / f"{stem}-touch-calendar.csv")
    return out


def report(target: str, door: str = "", start: str | None = None, sender: str = "", address: str = "") -> str:
    res = build(target, door, start, sender, address)
    L = [f"Outreach Pack for '{res['slug']}': the {res['door']} door, first email on {res['start']}, from {res['list'].name}.", ""]
    ready = sum(1 for m in res["merge"] if m["ready"] == "yes")
    L.append(f"Emails: {len(res['merge'])} businesses in the mail-merge file, {ready} ready, {len(res['merge']) - ready} not ready yet.")
    L.append(f"Touches: {len(res['calendar'])} in the 14-day calendar.")
    if res["left_out"]:
        L.append(f"Left out ({len(res['left_out'])}): " + "; ".join(f"{b} ({why})" for b, why in res["left_out"][:8]) + (" ..." if len(res["left_out"]) > 8 else ""))
    if res["no_email"]:
        L.append(f"No email address ({len(res['no_email'])}): they keep the social and call touches only: " + ", ".join(res["no_email"][:8]) + (" ..." if len(res["no_email"]) > 8 else ""))
    if res["not_ready"]:
        gaps: dict[str, int] = {}
        for _b, ms in res["not_ready"]:
            for m in ms:
                gaps[m] = gaps.get(m, 0) + 1
        L.append("Not ready, because these are missing: " + ", ".join(f"{k} ({v} rows)" for k, v in sorted(gaps.items())) + ".")
        L.append("  Fill them in on the list (or pass --name and --address) and run this again. Rows marked ready=no must not be sent as they are.")
    for f in res["files"]:
        L.append(f"Saved: engines/{res['slug']}/outreach/{f.name}")
    if not res["files"]:
        L.append("Nothing to save: no row could be used.")
    L += ["", "Next, in this order:",
          "  1. python dse.py preflight " + res["slug"] + " --domain yourdomain.com   (checks the list and your sending domain)",
          "  2. Fix every ready=no row, then load the mail-merge file into your own Gmail merge or sending tool.",
          "  3. Do the warm comments on the calendar the day before each first email.",
          "  4. YOU press start and YOU press every send. Nothing was sent by this tool."]
    return "\n".join(L)


# ------------------------------------------------------------------ the Send Desk view of the touch calendar

CALENDAR_SUFFIX = "-touch-calendar"
CHANNEL_LABEL = {"email": "Email", "social": "Social touch", "call": "Call"}


def desk_items(slug: str, cfg: dict, today: dt.date, back: int = 2, ahead: int = 14, hist: dict | None = None, limit: int = 1200) -> list[dict]:
    """The touch-calendar rows around today, in the Send Desk's row shape, with the status the log says.
    Taps on them come back through the same log as any list (source = the calendar file's name)."""
    from . import desklog as dl
    d = engine_dir(slug) / "outreach"
    if not d.is_dir():
        return []
    hist = hist if hist is not None else dl.history(slug)
    lo, hi = (today - dt.timedelta(days=back)).isoformat(), (today + dt.timedelta(days=ahead)).isoformat()
    items: list[dict] = []
    for p in sorted(d.glob(f"*{CALENDAR_SUFFIX}.csv")):
        try:
            with p.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            continue
        for r in rows:
            date = (r.get("date") or "").strip()
            if not (lo <= date <= hi):
                continue
            rid = (r.get("row_id") or "").strip() or touch_id(date, r.get("business", ""), r.get("channel", ""), int(r.get("day") or 0))
            ev = dl.latest(hist.get((p.stem, rid)))
            ch = r.get("channel", "")
            where = (r.get("where") or "").strip()
            label = CHANNEL_LABEL.get(ch, ch.title())
            if ch == "social" and "instagram" in where.lower():
                label = "Social touch (Instagram)"
            items.append({
                "key": f"{slug}|{p.stem}|{rid}", "list_date": date, "engine": slug, "engine_label": cfg.get("name") or slug, "source": p.stem, "row_id": rid,
                "name": r.get("business", ""), "person": "", "city": r.get("city", ""), "channel": label, "where": where, "website": "",
                "message": r.get("draft", ""), "warmup": "", "gap": "", "audit": "",
                "notes": f"Day {r.get('day', '')} of the 14-day touch plan ({r.get('door') or 'review'} door). {r.get('action', '')}".strip(),
                "touch": None, "status": ev["status"] if ev else "to do", "category": (ev or {}).get("category", ""), "reply": (ev or {}).get("reply", ""),
                "next_step": (ev or {}).get("next_step", ""), "value": (ev or {}).get("value", "")})
    items.sort(key=lambda i: (i["list_date"], i["name"], i["row_id"]))
    return items[:limit]
