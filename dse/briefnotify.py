"""Brief notifications: a quiet phone push when something that needs you has changed in your Daily Brief.

The PC decides (it knows your local time and what it already told you); Citadel only delivers (your own account, the notification bell and your phone) and honours
the switch in your profile. The rules are fixed and visible:

  * Only things that need you: a reply waiting, a booked call to prepare for, an overdue invoice or student cut, a late deliverable, a student who needs a check-in.
    Routine things (follow-ups due, messages to send, nothing going out, offers, goals) never buzz your phone: they are in the brief when you look.
  * Only what is NEW since you were last told: a thing already announced stays quiet until it grows (2 replies waiting becomes 3). When it is handled and comes back, it is new again.
  * The first brief ever is a baseline: what is already waiting is not announced, so turning this on never floods you.
  * One push at a time, at most one every 45 minutes, several new things in the same push.
  * Quiet hours (default 21:00 to 07:00, this PC's time): nothing is sent, and what arrived overnight is announced once, after they end, if it is still waiting.
  * Settings (optional) in data/brief-notify.json: {"enabled": true, "quiet_start": 21, "quiet_end": 7, "min_minutes": 45}.
Nothing is sent to anyone but your own account.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from .common import DATA

SETTINGS = DATA / "brief-notify.json"
STATE = DATA / "brief-notify-state.json"
NOTABLE = (1, 2, 2.5, 2.6, 3.5, 3.7)
DEFAULTS = {"enabled": True, "quiet_start": 21, "quiet_end": 7, "min_minutes": 45}


def settings() -> dict:
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    out = {**DEFAULTS, **{k: s[k] for k in DEFAULTS if k in s}}
    for k in ("quiet_start", "quiet_end", "min_minutes"):
        try:
            out[k] = int(out[k])
        except (TypeError, ValueError):
            out[k] = DEFAULTS[k]
    out["quiet_start"] %= 24
    out["quiet_end"] %= 24
    out["min_minutes"] = max(5, min(out["min_minutes"], 24 * 60))
    out["enabled"] = bool(out["enabled"])
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(st: dict) -> None:
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st), encoding="utf-8")


def notable(brief: dict) -> dict[str, dict]:
    """The things in the brief that need you: {key: {n, text, engine}}. n is the number in the sentence (2 replies waiting), 1 when there is none."""
    out = {}
    for m in brief.get("moves", []):
        try:
            rank = float(m.get("rank"))
        except (TypeError, ValueError):
            continue
        if rank not in NOTABLE:
            continue
        mm = re.search(r"\d+", m.get("do", ""))
        out[f"{m.get('engine', '')}|{rank:g}"] = {"n": int(mm.group(0)) if mm else 1, "text": m.get("do", ""), "engine": m.get("engine_name") or m.get("engine", "")}
    return out


def is_quiet(now: dt.datetime, cfg: dict) -> bool:
    a, b, h = cfg["quiet_start"], cfg["quiet_end"], now.hour
    if a == b:
        return False
    return (h >= a or h < b) if a > b else (a <= h < b)


def decide(brief: dict, state: dict, now: dt.datetime, cfg: dict | None = None) -> tuple[dict | None, dict]:
    """(the push to send or None, the new state). The state is only to be saved once the push is delivered (or not wanted)."""
    cfg = cfg or settings()
    cur = notable(brief)
    ann = dict(state.get("announced", {}))
    if "announced" not in state:                          # the first brief is a baseline: what is already waiting is not announced
        return None, {"announced": {k: v["n"] for k, v in cur.items()}, "notified_at": state.get("notified_at", "")}
    fresh = {k: v for k, v in cur.items() if k not in ann or v["n"] > int(ann[k])}
    # what is no longer waiting is forgotten (so it can be announced again if it comes back); a thing that shrank is lowered (so growing again counts as new)
    keep = {k: min(int(ann[k]), cur[k]["n"]) for k in ann if k in cur}
    quiet = is_quiet(now, cfg)
    last = state.get("notified_at", "")
    too_soon = False
    if last:
        try:
            too_soon = (now - dt.datetime.fromisoformat(last)).total_seconds() < cfg["min_minutes"] * 60
        except ValueError:
            too_soon = False
    if not fresh or not cfg["enabled"] or quiet or too_soon:
        return None, {"announced": keep, "notified_at": last}
    items = list(fresh.values())[:3]
    body = " | ".join(f"[{i['engine']}] {i['text']}" for i in items)[:280]
    more = len(fresh) - len(items)
    title = "Your brief: " + (f"{len(fresh)} new things" if len(fresh) > 1 else "something new")
    push = {"title": title, "body": body + (f" (+{more} more)" if more > 0 else "")}
    new_ann = {**keep, **{k: v["n"] for k, v in fresh.items()}}
    return push, {"announced": new_ann, "notified_at": now.isoformat(timespec="seconds")}
