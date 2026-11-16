"""Claude cost control for DBI-AI: which Claude model answers, how many tokens were used, and a daily token limit you set yourself.

Standard library only; used by chat.py and by `python dse.py claude usage|limit`. Everything lives on this PC (data/claude-usage.json): nothing here is sent anywhere.

  * Three tiers, so a small budget is not spent on the most expensive model by default: haiku (cheapest, fastest), sonnet (balanced, the DEFAULT), opus (strongest, costs the most).
    Choose per question in DBI-AI's "Answering with" menu (claude:haiku, claude:sonnet, claude:opus), or set the PC's default with the HQ_CHAT_CLAUDE_MODEL setting (a tier name or a model id).
  * Every answer's tokens (in and out) are added to today's tally, by model. The answer's footer shows them. Money is not computed here: prices change, so the page links to Anthropic's own usage and billing.
  * A daily token limit (0 = none): once today's tally reaches it, Claude is skipped for the rest of the day and the local model answers instead, with a plain line saying why.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

TIERS = {
    "haiku": ("claude-haiku-5-5", "Haiku 5.5", "the cheapest and fastest"),
    "sonnet": ("claude-sonnet-5-5", "Sonnet 5.5", "balanced: good answers at a moderate cost"),
    "opus": ("claude-opus-5-5", "Opus 5.5", "the strongest, and the one that costs the most"),
}
DEFAULT_TIER = "sonnet"
KEEP_DAYS = 60
MAX_LIMIT = 100_000_000


def usage_file() -> Path:
    return Path(os.environ.get("HQ_CLAUDE_USAGE_FILE") or (Path(__file__).resolve().parent.parent / "data" / "claude-usage.json"))


def _load(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or usage_file()).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict, path: Path | None = None) -> None:
    p = path or usage_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def resolve(mode: str, setting: str = "") -> tuple[str, str]:
    """(tier, model id) for a model choice: 'claude' (the PC's default), 'claude:haiku|sonnet|opus', or a setting that is a tier name or a full model id."""
    mode = (mode or "claude").strip().lower()
    if mode.startswith("claude:") and mode[7:] in TIERS:
        t = mode[7:]
        return t, TIERS[t][0]
    s = (setting or "").strip()
    if s.lower() in TIERS:
        return s.lower(), TIERS[s.lower()][0]
    for t, (mid, _l, _w) in TIERS.items():
        if s == mid:
            return t, mid
    if s and all(c.isalnum() or c in "-._" for c in s) and s.startswith("claude-"):
        return "custom", s                                   # your own choice of model id, passed through as you set it
    return DEFAULT_TIER, TIERS[DEFAULT_TIER][0]


def valid_mode(mode: str) -> bool:
    return mode == "claude" or (mode.startswith("claude:") and mode[7:] in TIERS)


def today_str(today: dt.date | None = None) -> str:
    return (today or dt.date.today()).isoformat()


def record(model: str, tokens_in: int, tokens_out: int, today: dt.date | None = None, path: Path | None = None) -> None:
    d = _load(path)
    days = d.setdefault("days", {})
    day = days.setdefault(today_str(today), {})
    m = day.setdefault(str(model)[:60], {"in": 0, "out": 0, "calls": 0})
    m["in"] += max(0, int(tokens_in or 0))
    m["out"] += max(0, int(tokens_out or 0))
    m["calls"] += 1
    for old in sorted(days)[:-KEEP_DAYS]:
        days.pop(old, None)
    _save(d, path)


def used_today(today: dt.date | None = None, path: Path | None = None) -> int:
    day = _load(path).get("days", {}).get(today_str(today), {})
    return sum(int(m.get("in", 0)) + int(m.get("out", 0)) for m in day.values() if isinstance(m, dict))


def limit(path: Path | None = None) -> int:
    try:
        return max(0, int(_load(path).get("limit", 0)))
    except (TypeError, ValueError):
        return 0


def set_limit(n: int, path: Path | None = None) -> int:
    n = max(0, min(MAX_LIMIT, int(n)))
    d = _load(path)
    d["limit"] = n
    _save(d, path)
    return n


def over_limit(today: dt.date | None = None, path: Path | None = None) -> bool:
    lim = limit(path)
    return lim > 0 and used_today(today, path) >= lim


def report(days: int = 7, today: dt.date | None = None, path: Path | None = None) -> str:
    d = _load(path)
    t = today or dt.date.today()
    rows, total = [], 0
    for k in range(days):
        day = (t - dt.timedelta(days=k)).isoformat()
        for model, m in sorted((d.get("days", {}).get(day, {}) or {}).items()):
            tin, tout = int(m.get("in", 0)), int(m.get("out", 0))
            total += tin + tout
            rows.append(f"{day}  {model:20} {m.get('calls', 0):4} answer(s)  {tin + tout:>10,} tokens (in {tin:,}, out {tout:,})")
    lim = limit(path)
    head = [f"# Claude usage, last {days} days", "", f"Today: {used_today(today, path):,} tokens" + (f" of your daily limit of {lim:,}" if lim else " (no daily limit set)"), ""]
    body = rows or ["No Claude answers in this period."]
    foot = ["", f"Total in this period: {total:,} tokens.", "Money is not worked out here (prices change): see what you spent, and set a monthly limit, at console.anthropic.com."]
    return "\n".join(head + body + foot) + "\n"
