"""CareBridge mystery-shop tracker: how fast does each agency answer a family's enquiry?

  python dse.py mystery new my-lists/2026-11-14-home-care-tampa-fl-checked.csv
        makes a tracker CSV with one row per agency: you send each enquiry yourself (web form, call or email),
        then fill sent_at and first_reply_at (YYYY-MM-DD HH:MM, your local time). Leave first_reply_at empty if
        no reply came.
  python dse.py mystery score my-lists/...-mystery.csv
        works out the reply time and scores each agency. A slow reply is a hot lead for CareBridge:
          Hot  = no reply after 48 hours, or a reply after more than 24 hours
          Warm = a reply after 1 to 24 hours
          Cold = a reply within the hour (they already answer fast; skip them)
Nothing here sends anything. Enquire honestly: you are a member of the public asking about care, and you
never invent a medical situation or a person.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

from .common import log, out_path, read_csv, write_csv

FMT = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")


def _t(s: str) -> dt.datetime | None:
    s = (s or "").strip()
    for f in FMT:
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def new(src: str, out: str = "") -> str:
    rows = read_csv(src)
    tr = [{"business": r.get("business") or r.get("company") or r.get("name", ""), "city": r.get("city", ""),
           "website": r.get("website", ""), "phone": r.get("phone", ""), "email": r.get("email", ""),
           "gap_used": r.get("gap_used", ""), "channel_used": "", "sent_at": "", "first_reply_at": "",
           "reply_hours": "", "score": "", "notes": ""} for r in rows]
    dst = out or str(out_path(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", Path(src).stem), "mystery"))
    write_csv(dst, tr)
    print(f"Tracker with {len(tr)} agencies -> {dst}\nSend each enquiry yourself, fill sent_at / first_reply_at, then run: python dse.py mystery score {dst}")
    return dst


def score(src: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    rows = read_csv(src)
    counts = {"Hot": 0, "Warm": 0, "Cold": 0, "waiting": 0, "not sent": 0}
    for r in rows:
        sent, reply = _t(r.get("sent_at", "")), _t(r.get("first_reply_at", ""))
        if not sent:
            r["reply_hours"], r["score"] = "", "not sent"
        elif reply:
            h = round((reply - sent).total_seconds() / 3600, 1)
            r["reply_hours"] = h
            r["score"] = "Cold" if h <= 1 else "Warm" if h <= 24 else "Hot"
        else:
            waited = (now - sent).total_seconds() / 3600
            r["reply_hours"] = f"none after {round(waited)}h"
            r["score"] = "Hot" if waited >= 48 else "waiting"
        counts[r["score"]] += 1
    order = {"Hot": 0, "Warm": 1, "waiting": 2, "Cold": 3, "not sent": 4}
    rows.sort(key=lambda r: order[r["score"]])
    write_csv(src, rows)
    print(f"{counts['Hot']} Hot, {counts['Warm']} Warm, {counts['Cold']} Cold, {counts['waiting']} still waiting, "
          f"{counts['not sent']} not sent yet -> {src}\nReach out to Hot and Warm only (CareBridge rule).")
    return src
