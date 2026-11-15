"""The Daily Brief: the few things to do first today, each with the tool that does it and the form already filled.

    python dse.py brief [--top 3]

It reads what the Weekly Review reads (replies waiting, booked calls, follow-ups due, unsent messages, overdue invoices and cuts, students who need a check-in,
asks and thank-yous due, money against your goal) for ALL your engines, keeps the first few by the review's own fixed rule (closest to money first),
and attaches to each one the tool that does it with the values it already knows (the engine, the list, the row). Nothing is guessed, sent or changed:
every line says where it comes from, and a move with no tool says "open the Send Desk".

The runner builds it by itself in the background and sends it to the Citadel Dashboard (bridge/brief_sync.py), so your day starts with the answer to
"what first?" instead of a list of tools. The same file is on your PC: data/brief.json and data/brief.md.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import review
from .common import DATA
from .engines import all_slugs, engine_dir

BRIEF_JSON = DATA / "brief.json"
BRIEF_MD = DATA / "brief.md"


def _send_list(slug: str, source: str) -> str:
    rel = f"engines/{slug}/send-lists/{source}.csv"
    return rel if (engine_dir(slug) / "send-lists" / f"{source}.csv").is_file() else ""


def action(mv: dict, g: dict) -> tuple[str, dict, str]:
    """(tool key, the values the tool's form can already be given, the button's words) for one move; ("", {}, "") when the Send Desk or your own judgement is the next step."""
    s, r = g["slug"], mv["rank"]
    eng = {"engine": s}
    if r == 1:
        return "dse.reply", dict(eng), "Work out the reply"
    if r == 2:
        c = g["calls"][0] if g["calls"] else None
        return ("dse.call_prep", {**eng, "source": c["source"], "row": str(c["row"])}, "Prepare for the call") if c else ("dse.call_after", dict(eng), "After the call")
    if r == 2.5 or r == 3.5:
        return "dse.client_list", dict(eng), "Open my clients"
    if r == 2.6 or r == 3.6:
        return "dse.cut_list", dict(eng), "Who owes what"
    if r == 3:
        return "dse.followups", dict(eng), "Plan the follow-ups"
    if r == 3.7:
        return "dse.success", {**eng, "view": "drafts"}, "Draft the check-ins"
    if r == 4:
        first = next((_send_list(s, src) for src in sorted(set(g["unsent"]), reverse=True) if _send_list(s, src)), "")
        return ("dse.preflight", {"csv": first}, "Check the list first") if first else ("", {}, "")
    if r == 4.7:
        return "dse.proof_due", dict(eng), "Who to ask or thank"
    if r == 5:
        return "dse.cashin", dict(eng), "Log the money"
    if r == 6:
        return "dse.daily", dict(eng), "Build today's list"
    if r == 7:
        return "dse.offers", dict(eng), "My offers"
    if r == 8:
        return "dse.goal", dict(eng), "Look at the goal"
    return "", {}, ""


def build(today: dt.date | None = None, top: int = 3) -> dict:
    today = today or dt.date.today()
    slugs = all_slugs()
    items, engines = [], []
    for s in slugs:
        g = review.gather(s, today)
        try:
            name = json.loads((engine_dir(s) / "engine.json").read_text(encoding="utf-8")).get("name") or s
        except (OSError, ValueError):
            name = s
        m = g["month"]
        engines.append({"slug": s, "name": name, "received": round(m["received"], 2), "target": g["target"], "sent_week": g["sent_week"],
                        "pace": round(g["pace"]["projected"]) if g["pace"]["state"] == "now" and m["received"] > 0 else None})
        for mv in review.moves(g):
            tool, values, button = action(mv, g)
            items.append({"engine": s, "engine_name": name, "rank": mv["rank"], "do": mv["do"], "how": mv["how"], "source": mv["source"], "tool": tool, "values": values, "button": button})
    items.sort(key=lambda x: x["rank"])
    shown = items[:max(1, min(top, 8))]
    if not slugs:
        head = "You have no engines yet. Create one in HQ Tools, My engines, and your brief starts there."
    elif not items:
        head = "Nothing is waiting. Keep the messages going out."
    else:
        head = f"{len(shown)} thing{'s' if len(shown) != 1 else ''} to do first today" + (f" ({len(items) - len(shown)} more behind them)" if len(items) > len(shown) else "") + "."
    return {"date": today.isoformat(), "made": dt.datetime.now().isoformat(timespec="minutes"), "headline": head, "moves": shown, "more": max(0, len(items) - len(shown)), "engines": engines}


def render(b: dict) -> str:
    out = [f"# Your brief for {b['date']}", "", b["headline"], ""]
    for i, m in enumerate(b["moves"], 1):
        out += [f"{i}. [{m['engine_name']}] {m['do']}", f"   How: {m['how']}", f"   From: {m['source']}" + (f"   Tool: {m['tool']}" if m["tool"] else "")]
    if b["engines"]:
        out += ["", "## Where each engine stands"]
        for e in b["engines"]:
            line = f"- {e['name']}: {e['sent_week']} message(s) sent in the last 7 days"
            if e["target"]:
                line += f"; {e['received']:,.0f} of {e['target']:,.0f} received" + (f", on pace for {e['pace']:,}" if e["pace"] else "")
            out.append(line)
    out += ["", "Made from the same files as the Weekly Review, ranked by its fixed rule. Nothing is sent or changed by this brief."]
    return "\n".join(out) + "\n"


def write(b: dict) -> Path:
    DATA.mkdir(exist_ok=True)
    BRIEF_JSON.write_text(json.dumps(b, indent=1), encoding="utf-8")
    BRIEF_MD.write_text(render(b), encoding="utf-8")
    return BRIEF_MD


def run(top: int = 3, today: dt.date | None = None) -> str:
    b = build(today, top)
    write(b)
    return render(b)
