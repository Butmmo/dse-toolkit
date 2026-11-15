"""CRM sync: the leads, replies and calls in your engines, kept in your BPS CRM without copying.

    python dse.py crm status <engine|all>          which engines sync, and what the CRM would get
    python dse.py crm preview <engine>             every lead as the CRM would receive it (nothing is sent)
    python dse.py crm on <engine>  /  off <engine> turn it on or off for an engine (it is OFF until you turn it on)
    python dse.py crm sync [<engine>]              send now (the runner also does it by itself every 5 minutes for engines that are on)

What goes across (your own engine files only, nothing is guessed):
  * one CRM lead per business (a business that is on several lists, or got a follow-up, is still one lead): name, city, website, email, phone, what the check found
    (the gap), your opener, where you reached out, and the engine it came from ("Source: My PC: <engine>")
  * its stage, from the Send Desk log: Sent = Contacted; a reply = Replied Positively (interested, a price question, a question, a referral) or Replied Negatively
    (not interested, already have someone, not now, unsubscribe); Call booked; Won = Closed; Lost = Replied Negatively; a saved proposal = Proposal Sent.
    An out-of-office auto-reply or an unclear reply is NOT a stage: it stays Contacted and the reply is written into the notes for you to read.
  * the other way too: a stage you change BY HAND in the CRM is recorded in the engine's log (Contacted = Sent, Replied = a reply tap with no invented text, Call Booked,
    Closed = Won), so the Daily Brief and the follow-ups stop asking about what you already handled. It never undoes anything and never writes a reply you did not get.
  * a block in the notes that the PC keeps up to date (what was sent when, the reply in their words, the call, the result). Your own notes are never touched.
The CRM is yours first: a stage only moves FORWARD (what you set by hand is never pulled back), an empty field is filled but a field you wrote is never overwritten,
and a lead you added yourself is matched by its website (else name and city) and adopted, not duplicated. Nothing is sent to anyone but your own Citadel account.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from . import desklog as dl
from . import replies
from .common import DATA
from .engines import all_slugs, engine_dir, load

STATE = DATA / "crm-sync.json"
BEGIN = "--- From your PC (kept up to date, edit above this line) ---"
POSITIVE = {"interested", "price", "question", "referral"}
NEGATIVE = {"not_interested", "already_have", "not_now", "unsubscribe"}
PATHS = {"smb", "ascent", "revenue", "broadcast", "authority", "gtm", "voiceai", "automation", "ministry", "carebridge"}
MAX_ROWS = 2000


def enabled(slug: str) -> bool:
    try:
        return bool(json.loads((engine_dir(slug) / "engine.json").read_text(encoding="utf-8")).get("crm_sync"))
    except (OSError, ValueError):
        return False


def set_enabled(slug: str, on: bool) -> str:
    load(slug)
    p = engine_dir(slug) / "engine.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["crm_sync"] = bool(on)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return (f"CRM sync is ON for {slug}: its leads, replies and calls now appear in your BPS CRM (the runner sends them every 5 minutes). Preview first: python dse.py crm preview {slug}\n"
            if on else f"CRM sync is OFF for {slug}. Leads already in your CRM stay there; nothing more is sent.\n")


def _category_stage(cat: str) -> str | None:
    c = (cat or "").replace(" ", "_").lower()
    if c in POSITIVE:
        return "replied_positively"
    if c in NEGATIVE:
        return "replied_negatively"
    return None                   # out of office, wrong person, unclear: not a stage


def _classify(e: dict) -> str:
    cat = (e.get("category") or "").strip()
    if cat:
        return cat.replace(" ", "_").lower()
    return replies.classify(e.get("reply", "")).get("category", "unclear")


def _email(row: dict) -> str:
    for k in ("email", "contact_email", "where"):
        v = (row.get(k) or "").strip()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            return v[:200]
    return ""


def _proposal_names(slug: str) -> set[str]:
    out = set()
    d = engine_dir(slug) / "proposals"
    for p in d.glob("*.json") if d.is_dir() else []:
        try:
            out.add(dl.norm(json.loads(p.read_text(encoding="utf-8")).get("client", "")))
        except (OSError, ValueError):
            pass
    return out - {""}


def leads_for(slug: str, today: dt.date | None = None) -> list[dict]:
    """One CRM lead per business in the engine, with its stage and the notes block, from the lists and the tap log."""
    cfg = load(slug)
    hist = dl.history(slug)
    props = _proposal_names(slug)
    path = cfg.get("path") if cfg.get("path") in PATHS else None
    name_of_engine = cfg.get("name") or slug
    out = []
    for tkey, t in dl.threads(slug).items():
        rows = t["rows"]
        first = t["first"] or rows[0]
        events = []
        for r in rows:
            for e in hist.get((r["_source"], r["_row_id"]), []):
                events.append((e.get("logged_at", ""), r, e))
        events.sort(key=lambda x: x[0])
        stage, terminal, last_date = "not_contacted", False, ""
        notes, sent_touches = [], set()
        for when, r, e in events:
            st, day = e.get("status", ""), when[:10]
            if st == "sent":
                sent_touches.add(r["touch"])
                if stage == "not_contacted":
                    stage = "contacted"
                last_date = max(last_date, day)
                notes.append(f"{day}: sent (touch {r['touch']}, {r.get('channel') or 'message'})")
            elif st == "replied":
                cat = _classify(e)
                s = _category_stage(cat)
                if s:
                    stage, terminal = s, False
                elif stage == "not_contacted":
                    stage = "contacted"
                last_date = max(last_date, day)
                text = re.sub(r"\s+", " ", e.get("reply", "")).strip()[:300]
                notes.append(f"{day}: replied ({cat.replace('_', ' ')})" + (f": \"{text}\"" if text else ""))
            elif st == "booked":
                stage, terminal = "call_booked", False
                last_date = max(last_date, day)
                notes.append(f"{day}: call booked")
            elif st == "won":
                stage, terminal = "closed", False
                last_date = max(last_date, day)
                notes.append(f"{day}: won" + (f" ({e['value']})" if e.get("value") else ""))
            elif st == "lost":
                stage, terminal = "replied_negatively", True
                last_date = max(last_date, day)
                notes.append(f"{day}: lost" + (f" ({e['value']})" if e.get("value") else ""))
        name = (first.get("business") or first.get("name") or "").strip()
        if not name:
            continue
        if stage in ("not_contacted", "contacted", "replied_positively", "call_booked") and dl.norm(name) in props:
            stage = "proposal_sent"
            notes.append("a proposal is saved for this business")
        row = {
            "hq_key": f"{slug}|{tkey}"[:200], "hq_engine": slug, "name": name[:200], "city": (first.get("city") or "")[:100],
            "website_url": (first.get("website") or "")[:300], "contact_email": _email(first), "contact_phone": (first.get("phone") or "")[:60],
            "niche": (first.get("category") or "")[:100], "path_key": path, "lead_source": f"My PC: {name_of_engine}"[:100],
            "the_gap": (first.get("gap_used") or "")[:500], "gaps_found": (first.get("gaps_found") or "")[:800], "opener": (first.get("opener") or "")[:1500],
            "outreach_channel": (first.get("channel") or "")[:40], "outreach_where": (first.get("where") or "")[:300],
            "stage": stage, "terminal": terminal, "last_contacted_at": last_date or None,
            "email_1_sent": 1 in sent_touches, "email_2_sent": 2 in sent_touches, "email_3_sent": 3 in sent_touches,
            "notes_hq": "\n".join(notes)[:4000],
        }
        if str(first.get("lead_score", "")).isdigit() and 0 <= int(first["lead_score"]) <= 10:
            row["lead_score"] = int(first["lead_score"])
        out.append(row)
    return out


def _digest(row: dict) -> str:
    return hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sent": {}}


def pending(slugs: list[str]) -> tuple[list[dict], dict]:
    """The leads whose content changed since they were last sent: (rows to send, the new digests)."""
    st = load_state()["sent"]
    rows, digs = [], {}
    for s in slugs:
        for r in leads_for(s):
            d = _digest(r)
            digs[r["hq_key"]] = d
            if st.get(r["hq_key"]) != d:
                rows.append(r)
    return rows[:MAX_ROWS], digs


def preview(slug: str, limit: int = 25) -> str:
    rows = leads_for(slug)
    by: dict[str, int] = {}
    for r in rows:
        by[r["stage"]] = by.get(r["stage"], 0) + 1
    out = [f"# CRM sync preview: {slug}", "", f"{len(rows)} lead(s) would be in your BPS CRM ({'ON' if enabled(slug) else 'OFF: turn it on with: python dse.py crm on ' + slug}).", ""]
    if by:
        out.append("By stage: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])) + ".")
        out.append("")
    for r in rows[:limit]:
        out.append(f"- {r['name']} ({r['city'] or 'no city'}): {r['stage'].replace('_', ' ')}" + (f", last contact {r['last_contacted_at']}" if r["last_contacted_at"] else ""))
        for n in r["notes_hq"].splitlines()[-2:]:
            out.append(f"    {n}")
    if len(rows) > limit:
        out.append(f"... and {len(rows) - limit} more.")
    out += ["", "A stage only moves forward in the CRM and what you wrote there is never overwritten. Nothing was sent by this preview."]
    return "\n".join(out) + "\n"


def status(slug: str) -> str:
    slugs = all_slugs() if slug == "all" else [slug]
    if slug != "all":
        load(slug)
    out = ["# CRM sync", ""]
    st = load_state()["sent"]
    for s in slugs:
        rows = leads_for(s)
        synced = sum(1 for r in rows if st.get(r["hq_key"]) == _digest(r))
        out.append(f"- {s}: {'ON' if enabled(s) else 'off'}; {len(rows)} lead(s), {synced} already in your CRM" + ("" if enabled(s) else f" (turn on: python dse.py crm on {s})"))
    return "\n".join(out) + "\n"


def connect():
    """The runner's connection to your Citadel account (the same one the other helpers use), or None when this PC is not connected."""
    import importlib.util
    r = Path(__file__).resolve().parents[1] / "bridge" / "runner.py"
    try:
        spec = importlib.util.spec_from_file_location("dse_runner", r)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.Api(mod.load_env())
    except (SystemExit, Exception):
        return None


RANK = {"not_contacted": 0, "contacted": 1, "replied_negatively": 2, "replied_positively": 2, "call_booked": 3, "proposal_sent": 4, "closed": 5, "retainer": 6}


def events_for(current: str, target: str) -> list[tuple[str, str]]:
    """What the PC's log must record so it agrees with a stage the member set by hand in the CRM: [(status, category)] in order.
    Never undoes anything (a lead moved back is ignored) and invents no reply text. A proposal needs no tap (the Send Desk has no such status)."""
    cr, tr = RANK.get(current, 0), RANK.get(target, 0)
    pre = [("sent", "")] if cr == 0 and tr >= 1 and target != "not_contacted" else []
    if target == "contacted":
        return pre
    if target == "replied_positively":
        return pre + [("replied", "interested")] if cr < 2 or current == "replied_negatively" else []
    if target == "replied_negatively":
        return pre + [("replied", "not interested")] if cr < 2 or current == "replied_positively" else []
    if target == "call_booked":
        return pre + [("booked", "")] if cr < 3 else []
    if target in ("closed", "retainer"):
        return pre + [("won", "")] if cr < 5 else []
    return []


def pull(api, slugs: list[str], say=lambda *_: None) -> str:
    """The stages you changed by hand in the CRM, recorded in the engines' logs (so the Brief and the follow-ups stop asking about what you already handled). '' when nothing changed."""
    slugs = [s for s in slugs if enabled(s)]
    if not slugs or api is None:
        return ""
    changes = api.rpc("hq_crm_pull", {"p_engines": slugs}, tries=2) or []
    if not changes:
        return ""
    cache, acks, done = {}, [], []
    for ch in changes:
        key, target = str(ch.get("hq_key", "")), str(ch.get("stage", ""))
        slug, _, tkey = key.partition("|")
        if slug not in slugs or not tkey or target not in RANK:
            continue
        if slug not in cache:
            cache[slug] = ({r["hq_key"]: r for r in leads_for(slug)}, dl.threads(slug))
        leads, threads = cache[slug]
        lead, thread = leads.get(key), threads.get(tkey)
        if not lead or not thread or not thread["rows"]:
            continue                                  # not one of this PC's leads (or its list is gone): leave it, never guess
        row = thread["rows"][-1]                      # the latest message to that business
        now = dt.datetime.now()
        evs = events_for(lead["stage"], target)
        for i, (status, cat) in enumerate(evs):
            dl.append_events(slug, [{"logged_at": (now + dt.timedelta(seconds=i)).isoformat(timespec="seconds"), "list_date": row["_date"], "source": row["_source"], "row_id": row["_row_id"],
                                     "name": lead["name"], "channel": row.get("channel", ""), "touch": row["touch"], "status": status, "category": cat,
                                     "reply": "Marked in your BPS CRM (no reply text)" if status == "replied" else "", "next_step": "from the CRM"}])
        if evs:
            done.append(f"{lead['name']}: {target.replace('_', ' ')}")
        acks.append({"hq_key": key, "stage": target})
    if acks:
        api.rpc("hq_crm_ack", {"p_acks": acks[:200]}, tries=2)
    if done:
        say(f"{len(done)} change(s) from your CRM recorded")
    return (f"From your CRM: {len(done)} change(s) recorded in your logs ({', '.join(done[:5])}{'...' if len(done) > 5 else ''})." + chr(10)) if done else ""


def sync(slug: str = "", api=None, say=lambda *_: None) -> str:
    """First read what you changed by hand in the CRM, then send what changed in your engines. `api`: the runner's Api (rpc), or None to only count."""
    slugs = [slug] if slug else [s for s in all_slugs() if enabled(s)]
    if slug:
        load(slug)
        if not enabled(slug):
            return f"CRM sync is off for {slug}. Turn it on first: python dse.py crm on {slug} (preview: python dse.py crm preview {slug}).\n"
    if not slugs:
        return "No engine has CRM sync turned on. Preview and turn it on per engine: python dse.py crm on <engine>.\n"
    api = api or connect()
    got = pull(api, slugs, say)
    rows, digs = pending(slugs)
    if not rows:
        return got or "Your CRM is up to date.\n"
    if api is None:
        return got + f"{len(rows)} lead(s) would be sent (no connection to Citadel here).\n"
    tot = {"inserted": 0, "updated": 0, "unchanged": 0}
    st = load_state()
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        res = api.rpc("hq_crm_push", {"p_rows": chunk}, tries=2) or {}
        for k in tot:
            tot[k] += int(res.get(k, 0))
        for r in chunk:
            st["sent"][r["hq_key"]] = digs[r["hq_key"]]
        DATA.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(st), encoding="utf-8")
        say(f"sent {min(i + 100, len(rows))} of {len(rows)}")
    return got + f"CRM: {tot['inserted']} new lead(s), {tot['updated']} updated, {tot['unchanged']} already up to date.\n"
