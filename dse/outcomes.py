"""Outcomes: what your engine is really producing, from the taps you made. No guessing, no vanity numbers.

    python dse.py outcomes <engine>          print the report and save engines/<engine>/outcomes.md

Funnel: lists built, messages sent, replies, calls booked, clients won, lost, plus the money won (monthly USD you typed in
when you tapped Won). Then the same funnel by channel, by what the website was missing (the gap you led with), by
wording (variant) and by touch, so you can see what works.

Honesty rules:
  * Sent counts only what you marked Sent. A reply, call or win on a row also proves it was sent.
  * A difference is called only when BOTH groups have 30 or more sends, and gaps and wordings are compared inside the
    same channel (an email and a Facebook message are not the same test). Below that it says "too early to call".
  * One business replying to touch 2 counts once, on the touch it answered.
"""
from __future__ import annotations

import datetime as dt
import re

from . import desklog as dl
from .engines import engine_dir, load

MIN_N = 30
SENT_STATES = {"sent", "replied", "booked", "won", "lost"}


def _flags(events: list[dict]) -> dict:
    # an out-of-office auto-reply proves the message arrived but is not an answer
    s = {("sent" if dl.is_out_of_office(e) else e["status"]) for e in events}
    sent = bool(s & SENT_STATES)
    replied = bool(s & {"replied", "booked", "won"}) or ("lost" in s and "replied" in s)
    booked = bool(s & {"booked", "won"})
    won = "won" in s
    lost = "lost" in s and not won
    value = 0.0
    for e in events:
        if e["status"] == "won" and re.fullmatch(r"\d+(\.\d+)?", str(e.get("value", "") or "")):
            value = max(value, float(e["value"]))
    return {"sent": sent, "replied": replied, "booked": booked, "won": won, "lost": lost, "skipped": "skipped" in s and not sent, "value": value}


def rows_with_flags(slug: str) -> list[dict]:
    hist = dl.history(slug)
    out = []
    for r in dl.load_lists(slug):
        f = _flags(hist.get((r["_source"], r["_row_id"]), []))
        out.append({**r, **f})
    return out


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "-"


def group(rows: list[dict], key) -> dict[str, dict]:
    g: dict[str, dict] = {}
    for r in rows:
        if not r["sent"]:
            continue
        k = key(r)
        d = g.setdefault(k, {"sent": 0, "replied": 0, "booked": 0, "won": 0})
        d["sent"] += 1
        d["replied"] += r["replied"]
        d["booked"] += r["booked"]
        d["won"] += r["won"]
    return g


def verdicts(rows: list[dict]) -> list[str]:
    """Plain statements the numbers support, and plain 'too early' notes where they do not."""
    out = []
    firsts = [r for r in rows if r["touch"] == 1]
    ch = group(firsts, lambda r: r.get("channel", "") or "?")
    big = {k: v for k, v in ch.items() if v["sent"] >= MIN_N}
    small = {k: v for k, v in ch.items() if v["sent"] < MIN_N}
    if len(big) >= 2:
        ranked = sorted(big.items(), key=lambda kv: kv[1]["replied"] / kv[1]["sent"], reverse=True)
        (bk, bv), (wk, wv) = ranked[0], ranked[-1]
        if bv["replied"] / bv["sent"] > wv["replied"] / wv["sent"]:
            out.append(f"Channel: {bk} gets replies {pct(bv['replied'], bv['sent'])} of the time ({bv['sent']} sent) against {wk} "
                       f"{pct(wv['replied'], wv['sent'])} ({wv['sent']} sent). Send more by {bk}, and look at why {wk} is weaker.")
    elif small:
        out.append("Channel: too early to call. Each channel needs " + str(MIN_N) + " sends to compare. So far: "
                   + ", ".join(f"{k} {v['sent']}" for k, v in sorted(small.items())) + ".")
    for field, label in (("variant", "Wording"), ("gap_used", "Gap you led with")):
        per_channel: dict[str, dict] = {}
        for r in firsts:
            per_channel.setdefault(r.get("channel", "") or "?", {}).setdefault(r.get(field, "") or "?", []).append(r)
        said = False
        for c, groups in per_channel.items():
            stats = {k: group(v, lambda x: "a")["a"] for k, v in groups.items() if sum(1 for x in v if x["sent"]) >= MIN_N and group(v, lambda x: "a")}
            if len(stats) >= 2:
                ranked = sorted(stats.items(), key=lambda kv: kv[1]["replied"] / kv[1]["sent"], reverse=True)
                (bk, bv), (wk, wv) = ranked[0], ranked[-1]
                if bv["replied"] / bv["sent"] > wv["replied"] / wv["sent"]:
                    out.append(f"{label} (by {c}): \"{bk[:70]}\" {pct(bv['replied'], bv['sent'])} replies ({bv['sent']} sent) beats "
                               f"\"{wk[:70]}\" {pct(wv['replied'], wv['sent'])} ({wv['sent']} sent).")
                    said = True
        if not said:
            out.append(f"{label}: too early to call (each version needs {MIN_N} sends in the same channel).")
    t = group(rows, lambda r: r["touch"])
    if 2 in t and 1 in t:
        out.append(f"Follow-ups: touch 1 got {t[1]['replied']} repl{'y' if t[1]['replied'] == 1 else 'ies'} from {t[1]['sent']} sent; "
                   f"touch 2 and later got {sum(v['replied'] for k, v in t.items() if k >= 2)} from {sum(v['sent'] for k, v in t.items() if k >= 2)} sent.")
    return out


def table(g: dict[str, dict], title: str, order=None) -> list[str]:
    if not g:
        return []
    L = [f"### {title}", "", "| | Sent | Replies | Reply rate | Calls | Won |", "|---|---|---|---|---|---|"]
    for k in (order or sorted(g, key=lambda x: -g[x]["sent"])):
        v = g[k]
        flag = "" if v["sent"] >= MIN_N else " (too few to judge)"
        L.append(f"| {str(k)[:80]}{flag} | {v['sent']} | {v['replied']} | {pct(v['replied'], v['sent'])} | {v['booked']} | {v['won']} |")
    return L + [""]


def summary(slug: str) -> dict:
    """Small numbers for the Citadel card (also used by the report)."""
    rows = rows_with_flags(slug)
    sent = [r for r in rows if r["sent"]]
    firsts = [r for r in rows if r["touch"] == 1]
    today = dt.date.today().isoformat()
    unmarked = sum(1 for r in firsts if r["_date"] < today and not r["sent"] and not r["skipped"])
    s = {"rows": len(rows), "sent": len(sent), "replied": sum(r["replied"] for r in sent), "booked": sum(r["booked"] for r in sent),
         "won": sum(r["won"] for r in sent), "lost": sum(r["lost"] for r in sent),
         "value": round(sum(r["value"] for r in sent), 2), "unmarked": unmarked}
    s["reply_rate"] = round(100 * s["replied"] / s["sent"]) if s["sent"] else None
    ch = group(firsts, lambda r: r.get("channel", "") or "?")
    ready = {k: v for k, v in ch.items() if v["sent"] >= MIN_N}
    if len(ready) >= 2:
        k = max(ready, key=lambda x: ready[x]["replied"] / ready[x]["sent"])
        s["best_channel"] = k
    return s


def report(slug: str, write: bool = True) -> str:
    cfg = load(slug)
    rows = rows_with_flags(slug)
    s = summary(slug)
    firsts = [r for r in rows if r["touch"] == 1]
    L = [f"# Results: {cfg.get('name', slug)}", "", f"_Made {dt.date.today():%d %b %Y} from your taps. Only rows you marked Sent count as sent._", ""]
    if not s["sent"]:
        L += ["Nothing marked Sent yet, so there are no results to show. Send from the Send Desk and tap Sent on each message; "
              "the numbers appear here and on your engine card in Citadel.", ""]
    else:
        L += ["## The funnel", "", "| Lists rows | Sent | Replies | Calls booked | Won | Lost |", "|---|---|---|---|---|---|",
              f"| {s['rows']} | {s['sent']} | {s['replied']} ({pct(s['replied'], s['sent'])}) | {s['booked']} | {s['won']} | {s['lost']} |", ""]
        if s["won"]:
            L += [f"**Won:** {s['won']} client(s), **${s['value']:,.0f} a month** in total (what you typed when you tapped Won).", ""]
        L += ["## What the numbers say", ""] + [f"- {v}" for v in verdicts(rows)] + [""]
        L += ["## By channel (first messages)", ""] + table(group(firsts, lambda r: r.get("channel", "") or "?"), "Channel")[2:]
        L += table(group(firsts, lambda r: r.get("gap_used", "") or "?"), "By the gap you led with")
        L += table(group(firsts, lambda r: r.get("variant", "") or "?"), "By wording (variant)")
        L += table(group(rows, lambda r: f"touch {r['touch']}"), "By touch")
    if s["unmarked"]:
        L += [f"> **{s['unmarked']} first message(s)** on past lists were never marked Sent or Skipped. They are not counted and are not followed up. "
              "Open the Send Desk and mark them so these numbers are true.", ""]
    text = "\n".join(L) + "\n"
    if write:
        (engine_dir(slug) / "outcomes.md").write_text(text, encoding="utf-8", newline="\n")
    return text
