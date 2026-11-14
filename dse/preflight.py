"""Outreach Preflight: check a send list, and your sending domain, BEFORE a single message goes out.

    python dse.py preflight <engine|path-to-list> [--domain yourdomain.com] [--clean]
    python dse.py preflight --domain yourdomain.com              only the domain checks

List checks (engine send lists; with an engine name it takes the newest list):
  BLOCKERS (fix or drop these rows)   on your do-not-contact list (Reply Desk); an Email row with no valid address; already contacted (the log says Sent, or the same
                                     business is on an earlier list); an unfilled template placeholder like {business} or [their area] left in the message
  WARNINGS (your call)                spam trigger words, ALL CAPS words, too many exclamation marks, more than one link, a long message, a role address (info@) or a free mailbox
                                     as the recipient, an Email message with no easy way to say no, a missing sender name, no postal address in the engine settings
                                     (CAN-SPAM asks for one in commercial email to US recipients), more Email rows than your own engine cap, more than the common daily ceiling for one mailbox
Domain checks (--domain): mail servers (MX), an SPF record, DMARC and its policy, and the common DKIM selectors. A DKIM miss only means the common names were not found: your
sender tells you the real selector.

--clean writes a copy of the list WITHOUT the blocked rows into the engine's send-lists/drafts/ (never touches the original). Thresholds: dse/preflight_rules.json.
This is deliverability and good-manners guidance, not legal advice. In the UK, writing to a named person at a sole trader or partnership needs more care than to a company address (PECR).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from . import desklog as dl
from . import replies
from .common import ROOT, write_csv
from .engines import engine_dir, load

RULES = json.loads(Path(__file__).with_name("preflight_rules.json").read_text(encoding="utf-8"))
OPTOUT = re.compile(RULES["optout_rx"], re.I)
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PLACEHOLDER = re.compile(r"\{[a-z_ ]{2,30}\}|\[[A-Za-z][^\]]{2,40}\]|<<[^>]+>>|\bTODO\b|\bXXX\b")
LINK = re.compile(r"https?://\S+|www\.\S+", re.I)


# ------------------------------------------------------------------ message checks (pure)

def check_message(text: str, channel: str = "Email") -> list[tuple[str, str]]:
    """[(level, issue)] for one message. level is 'block' or 'warn'."""
    t = text or ""
    out: list[tuple[str, str]] = []
    if not t.strip():
        return [("block", "the message is empty")]
    ph = PLACEHOLDER.search(t)
    if ph:
        out.append(("block", f"an unfilled placeholder is still in the message: {ph.group(0)}"))
    low = t.lower()
    hits = sorted({w for w in RULES["spam_words"] if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])" if w[0].isalnum() else re.escape(w), low)})
    if len(hits) > RULES["max_spam_words"]:
        out.append(("warn", "spam trigger words: " + ", ".join(hits[:5])))
    caps = [w for w in re.findall(r"\b[A-Z]{4,}\b", t) if w not in ("ASAP", "FAQ", "CRM", "SEO", "B2B", "B2C", "USA", "HVAC")]
    if len(caps) > RULES["max_caps_words"]:
        out.append(("warn", f"{len(caps)} ALL CAPS words ({', '.join(caps[:3])})"))
    if t.count("!") > RULES["max_exclamations"]:
        out.append(("warn", f"{t.count('!')} exclamation marks"))
    if len(LINK.findall(t)) > RULES["max_links"]:
        out.append(("warn", f"{len(LINK.findall(t))} links (one at most in a first message)"))
    words = len(t.split())
    if words > RULES["max_words"]:
        out.append(("warn", f"{words} words: a first message works best under {RULES['max_words']}"))
    if channel == "Email" and not OPTOUT.search(t):
        out.append(("warn", "no easy way to say no (add: 'If this is not relevant, just reply no and I will not write again.')"))
    return out


def check_address(channel: str, where: str) -> list[tuple[str, str]]:
    w = (where or "").strip()
    if channel != "Email":
        return [("block", f"no {channel} address or handle on the row")] if not w else []
    if not EMAIL.match(w):
        return [("block", f"'{w or 'empty'}' is not a valid email address")]
    local, _, dom = w.lower().partition("@")
    out = []
    if local in RULES["role_locals"]:
        out.append(("warn", f"role address ({local}@): often read by several people or filtered"))
    if dom in RULES["freemail"]:
        out.append(("warn", f"free mailbox ({dom}): fine for a small business, but check it is theirs"))
    return out


# ------------------------------------------------------------------ list checks

def find_list(target: str) -> tuple[str, Path]:
    """(engine slug, list path) from an engine name (newest list) or a path to a list inside engines/<slug>/send-lists/."""
    p = Path(target)
    if not p.is_absolute() and (ROOT / target).exists():
        p = ROOT / target
    if p.is_file():
        m = re.search(r"engines[\\/]([^\\/]+)[\\/]send-lists", str(p))
        if not m:
            raise ValueError("A list to check must be inside engines/<engine>/send-lists/ (that is where the Send Desk lists live).")
        return m.group(1), p
    load(target)
    sl = engine_dir(target) / "send-lists"
    files = sorted(f for f in sl.glob("*.csv") if re.match(r"\d{4}-\d{2}-\d{2}", f.stem)) if sl.is_dir() else []
    if not files:
        files = sorted(f for f in (sl / "drafts").glob("*.csv")) if (sl / "drafts").is_dir() else []
    if not files:
        raise ValueError(f"'{target}' has no send lists yet. Build one first: python dse.py daily {target}")
    return target, files[-1]


def check_list(slug: str, path: Path) -> dict:
    cfg = load(slug)
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    hist = dl.history(slug)
    earlier = {}
    for r in dl.load_lists(slug):
        if r["_source"] != path.stem and r["_date"] <= re.match(r"\d{4}-\d{2}-\d{2}", path.stem).group(0):
            earlier.setdefault(r["_thread"], []).append(r)
    issues: dict[int, list[tuple[str, str]]] = {}
    seen_here: dict[str, int] = {}
    email_rows = 0
    for i, r in enumerate(rows):
        row_issues: list[tuple[str, str]] = []
        ch = (r.get("channel") or "").strip()
        where = (r.get("where") or "").strip()
        email = where if ch == "Email" else (r.get("email") or "").strip()
        row_issues += check_address(ch, where)
        reason = replies.on_dnc(slug, email, r.get("website", ""))
        if reason:
            row_issues.append(("block", f"on your do-not-contact list: {reason}"))
        row_issues += check_message(r.get("opener", ""), ch)
        key = dl.thread_key({**r, "business": r.get("business", "")})
        if key in seen_here:
            row_issues.append(("block", f"the same business appears twice on this list (row {rows[seen_here[key]].get('row', seen_here[key] + 1)})"))
        else:
            seen_here[key] = i
        prior = earlier.get(key, [])
        if any(dl.status_of_row(hist, p) in ("sent", "replied", "booked", "won", "lost") for p in prior):
            row_issues.append(("block", "already contacted: the log says a message to this business was sent on an earlier list"))
        if ch == "Email":
            email_rows += 1
        if row_issues:
            issues[i] = row_issues
    sender = (cfg.get("sender_name") or "").strip()
    list_notes: list[tuple[str, str]] = []
    if email_rows and not sender:
        list_notes.append(("warn", "your engine has no sender_name: messages should be signed with a real name"))
    if email_rows and not (cfg.get("postal_address") or "").strip():
        list_notes.append(("warn", "no postal_address in the engine settings: CAN-SPAM asks for a valid postal address in commercial email to US recipients"))
    cap = int((cfg.get("caps") or {}).get("Email", 999))
    if email_rows > cap:
        list_notes.append(("warn", f"{email_rows} Email rows is over your own Email cap of {cap} a day"))
    if email_rows > RULES["mailbox_daily_warn"]:
        list_notes.append(("warn", f"{email_rows} emails in one day. {RULES['mailbox_daily_note']}"))
    return {"slug": slug, "path": path, "rows": rows, "issues": issues, "list_notes": list_notes, "email_rows": email_rows}


# ------------------------------------------------------------------ domain checks

def dns_txt(name: str) -> list[str]:
    try:
        r = subprocess.run(["nslookup", "-type=TXT", name], capture_output=True, timeout=12, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = r.stdout.decode("utf-8", "replace")
    return [rec for rec in (" ".join(re.findall(r'"([^"]*)"', ln)) for ln in out.splitlines() if '"' in ln) if rec]


def dns_mx(name: str) -> bool | None:
    try:
        r = subprocess.run(["nslookup", "-type=MX", name], capture_output=True, timeout=12, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.decode("utf-8", "replace").lower()
    if "mail exchanger" in out:
        return True
    if "non-existent" in out or "can't find" in out or "no mx" in out or "no answer" in out:
        return False
    return None


def check_domain(domain: str, txt=dns_txt, mx=dns_mx) -> list[tuple[str, str]]:
    """[(level, text)]: level is ok, warn or block."""
    d = (domain or "").strip().lower().removeprefix("www.")
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d):
        raise ValueError("Give a domain like yourdomain.com (the part after the @ in your sending address).")
    out: list[tuple[str, str]] = []
    m = mx(d)
    out.append(("ok", "mail servers (MX) found") if m else ("warn", "no mail servers (MX) found: this domain cannot receive replies") if m is False else ("warn", "could not look up MX (no DNS tool?)"))
    recs = txt(d)
    spf = [r for r in recs if r.lower().startswith("v=spf1")]
    if not spf:
        out.append(("block", "no SPF record: receivers cannot tell your mail is really from you. Add one at your DNS host (your sender's help page gives the exact line)."))
    else:
        s = spf[0].lower()
        lookups = len(re.findall(r"\b(include:|a:|mx:|ptr:|exists:|redirect=)|(?<=\s)(a|mx)(?=\s|$)", s))
        out.append(("ok", f"SPF found ({'strict -all' if s.rstrip().endswith('-all') else 'soft ~all' if '~all' in s else 'ends with ' + s.split()[-1]})"))
        if len(spf) > 1:
            out.append(("block", "more than one SPF record: only one is allowed, and having two makes SPF fail"))
        if lookups > RULES["spf_lookup_limit"]:
            out.append(("warn", f"SPF may use about {lookups} DNS lookups; the limit is {RULES['spf_lookup_limit']}, and over it SPF fails"))
    dm = [r for r in txt("_dmarc." + d) if r.lower().startswith("v=dmarc1")]
    if not dm:
        out.append(("warn", "no DMARC record at _dmarc." + d + ". " + RULES["sender_guidelines"]))
    else:
        pol = (re.search(r"\bp=(\w+)", dm[0].lower()) or [None, "?"])[1]
        out.append(("ok", f"DMARC found, policy p={pol}" + (" (monitoring only: fine to start)" if pol == "none" else "")))
    found = [s for s in RULES["dkim_selectors"] if any(r.lower().startswith("v=dkim1") or "p=" in r.lower() for r in txt(f"{s}._domainkey.{d}"))]
    out.append(("ok", "DKIM found for selector " + ", ".join(found)) if found else
               ("warn", "no DKIM record under the common selector names. This does not prove it is missing: your email provider shows the real selector in its setup page."))
    return out


# ------------------------------------------------------------------ report

def report(target: str = "", domain: str = "", clean: bool = False, today: dt.date | None = None, txt=dns_txt, mx=dns_mx) -> str:
    today = today or dt.date.today()
    if not target and not domain:
        raise ValueError("Give an engine or a list to check, or --domain yourdomain.com.")
    out = ["# Outreach Preflight", ""]
    verdict_block = False
    if target:
        slug, path = find_list(target)
        res = check_list(slug, path)
        blocked = {i for i, iss in res["issues"].items() if any(l == "block" for l, _ in iss)}
        warned = {i for i, iss in res["issues"].items() if i not in blocked}
        n = len(res["rows"])
        verdict_block = bool(blocked)
        out += [f"List: {path.relative_to(ROOT).as_posix() if ROOT in path.parents else path.name}  ({n} rows, engine {slug})", "",
                (f"FIX FIRST: {len(blocked)} of {n} rows have a blocker." if blocked else f"READY: no blockers in {n} rows.") + (f" {len(warned)} more have warnings." if warned else ""), ""]
        for lvl, text in res["list_notes"]:
            out.append(f"- {'Warning' if lvl == 'warn' else 'Fix'}: {text}")
        if res["list_notes"]:
            out.append("")
        counts: dict[str, int] = {}
        for iss in res["issues"].values():
            for _l, t in iss:
                k = re.sub(r"[:'(].*$", "", t).strip()[:60]
                counts[k] = counts.get(k, 0) + 1
        if counts:
            out.append("## Most common problems")
            out += [f"- {v} x {k}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]
            out.append("")
        if res["issues"]:
            out.append("## Row by row")
            for i in sorted(res["issues"]):
                r = res["rows"][i]
                out.append(f"- row {r.get('row', i + 1)} {r.get('business', '')}:")
                for lvl, t in res["issues"][i]:
                    out.append(f"    {'BLOCK' if lvl == 'block' else 'warn '} {t}")
            out.append("")
        if clean:
            keep = [r for i, r in enumerate(res["rows"]) if i not in blocked]
            for j, r in enumerate(keep, 1):
                r["row"] = j
            dest = engine_dir(slug) / "send-lists" / "drafts" / f"{path.stem}-preflight-ready.csv"
            write_csv(dest, keep, first=list(res["rows"][0]) if res["rows"] else None)
            out += [f"Clean copy without the {len(blocked)} blocked row(s): {dest.relative_to(ROOT).as_posix()} (drafts/ is not shown on the Send Desk; look it over, then move it up into send-lists/ if you want to use it instead). The original is untouched.", ""]
    if domain:
        out += [f"## Sending domain: {domain}"]
        for lvl, text in check_domain(domain, txt, mx):
            out.append(f"- {'OK   ' if lvl == 'ok' else 'Fix  ' if lvl == 'block' else 'Check'} {text}")
            verdict_block = verdict_block or lvl == "block"
        out.append("")
    out.append("This is deliverability and good-manners guidance, not legal advice. Nothing was sent or changed" + (" except the clean copy." if clean and target else "."))
    text = "\n".join(out) + "\n"
    if target:
        (engine_dir(slug) / f"preflight-{today.isoformat()}.md").write_text(text, encoding="utf-8")
    return text
