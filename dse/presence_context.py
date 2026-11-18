"""Presence: find the social media plan you already have inside an engine's folder, understand it, and ask you how to use it, so Presence builds on your earlier work instead of replacing it.

    python dse.py presence context <engine>

A Function in Presence can be linked to an engine, and then it inherits that engine's folders: the folders attached to the engine (python dse.py context <engine> --add <folder>) and the engine's own
folder. This reads them read-only, with the SAME safety rules as the engine context folders (never _private-keys, the encrypted vault, .ssh, .aws, .env files, key, token or password files,
archives or encrypted files; anything that looks like a key or password is hidden; nothing is changed, moved or deleted). It looks for files that read like social media work: a content plan or calendar, a
posting schedule, brand voice notes, hashtag lists, post drafts or ideas, notes from an AI chat about growing on social media. From them it keeps, in plain counts and short quotes:
  * which platforms the plan is about and how much,   * account handles,   * the posting rhythm it wanted,   * content themes or pillars,   * the voice or tone it asked for,
  * hashtags,   * goals and the audience,   * post ideas and drafts (with the file each came from).
Then it writes my-lists/<engine>-presence-context.json for Presence > Earlier plan, with QUESTIONS for you: how to bring each finding into Presence (keep, change or leave out). It decides nothing for you.
The result stays on this PC until you press Add in Citadel, and then only these short findings go up (never a whole file). Standard library only: the engine context reader opens .docx and .pdf itself.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from . import context_folder as cf
from .common import LISTS
from .engines import engine_dir, load

MAX_FILES = 300
MAX_SOURCES = 25
MAX_TEXT = 80_000
PLATFORM_WORDS = {
    "instagram": r"\b(instagram|insta|ig|reels?)\b", "tiktok": r"\btik ?tok\b", "linkedin": r"\blinked ?in\b", "facebook": r"\bfacebook\b|\bfb\b", "x": r"\b(twitter|tweets?|x\.com)\b",
    "youtube": r"\byoutube\b|\byt shorts\b", "reddit": r"\breddit\b|\bsubreddit\b", "pinterest": r"\bpinterest\b|\bpins?\b", "discord": r"\bdiscord\b",
}
OTHER_PLATFORMS = {"threads": r"\bthreads\b", "snapchat": r"\bsnap ?chat\b", "telegram": r"\btelegram\b", "whatsapp": r"\bwhats ?app\b"}
SOCIAL_WORDS = re.compile(r"\b(social media|content (calendar|plan|pillars?|strategy|ideas|mix)|posting (schedule|plan|rhythm)|post(s|ing)? (daily|weekly|\d+ ?x)|captions?|hashtags?|carousels?|reels?|stories|engagement rate|followers|brand voice|tone of voice|content pillars?|editorial calendar|publish(ing)? schedule)\b", re.I)
NAME_HINT = re.compile(r"(social|content|calendar|caption|hashtag|instagram|linkedin|tiktok|facebook|youtube|posts?|reels?|brand[-_ ]?voice|editorial|ideas)", re.I)
SKIP_PATH = re.compile(r"(^|/)(context/digest|digest\.(md|json)$|engine\.json$|drafts/|sends/|replies/|outcomes/)", re.I)
HANDLE = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{3,30})\b")
PROFILE_URL = re.compile(r"https?://(?:www\.)?(instagram|tiktok|facebook|linkedin\.com/(?:in|company)|youtube|reddit\.com/user|pinterest|x|twitter)\.?(?:com)?/@?([A-Za-z0-9_.-]{3,50})", re.I)
HASHTAG = re.compile(r"(?<![\w&])#([A-Za-z][A-Za-z0-9_]{2,30})\b")
CADENCE = re.compile(r"\b(?:post(?:s|ing)?|publish(?:es|ing)?|share|upload)\b[^.\n]{0,40}?\b(?:(\d{1,2}) ?(?:x|times)(?: a| per|/)? ?(day|week|month)|(daily|every day|weekly|once a week|twice a week|every other day|three times a week))", re.I)
CADENCE2 = re.compile(r"\b(\d{1,2}) ?(?:x|times) ?(?:a|per|/) ?(day|week|month)\b", re.I)
THEME_HEAD = re.compile(r"^\s{0,3}(?:#{1,4}\s*|\*\*)?(content )?(pillars?|themes?|topics?|categories|content (types|mix|buckets))\b.*$", re.I)
VOICE_LINE = re.compile(r"\b(brand voice|tone of voice|tone|writing style|persona)\b\s*[:\-]\s*(.{8,160})", re.I)     # a bare "Voice:" is usually a spoken line in a script, not the brand voice
GOAL_LINE = re.compile(r"\b(goals?|objectives?|targets?|kpis?)\b\s*[:\-]\s*(.{8,160})", re.I)
AUDIENCE_LINE = re.compile(r"\b(audience|ideal (customer|client)|target (market|customer|audience)|who we (serve|help))\b\s*[:\-]\s*(.{8,160})", re.I)
CAL_DATE = {"date", "day", "when", "publish date", "post date"}
CAL_PLATFORM = {"platform", "channel", "network"}
CAL_TOPIC = {"topic", "idea", "post", "caption", "title", "theme", "hook", "content", "subject"}


def _clean(s: str, n: int = 200) -> str:
    return re.sub(r"\s+", " ", cf.redact(s)).strip(" -*#>|\t\"'“”")[:n]


# ------------------------------------------------------------------ the folders a Function inherits

def inherited_folders(engine: str) -> list[Path]:
    """The engine's attached context folders (kept only if they are safe) and the engine's own folder."""
    out: list[Path] = []
    cfg = load(engine)
    for f in cfg.get("context_folders") or []:
        try:
            p = cf.resolve_folder(str(f.get("path") if isinstance(f, dict) else f))
        except (ValueError, OSError):
            continue
        if cf.unsafe_reason(p) is None and p not in out:
            out.append(p)
    own = engine_dir(engine)
    if own.is_dir() and own not in out:
        out.append(own.resolve())
    return out


def walk_texts(root: Path):
    """(relative path, kind, text) for readable files, read-only, with the engine context reader's safety rules."""
    root = root.resolve()
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in sorted(dirnames) if d.lower() not in cf.FORBIDDEN_DIRS and not d.startswith(".") and not (Path(dirpath) / d).is_symlink()
                       and depth + 1 <= cf.MAX_DEPTH and os.path.realpath(Path(dirpath) / d).startswith(str(root))]
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root)).replace(os.sep, "/")
            kind, _why = cf.classify(p)
            if p.is_symlink() or kind in ("skip", "sheet", "config") or SKIP_PATH.search(rel):
                continue
            total += 1
            if total > MAX_FILES:
                return
            try:
                if kind == "text":
                    txt = cf._read(p, MAX_TEXT)
                elif kind == "doc":
                    txt = cf.read_doc(p)[:MAX_TEXT]
                elif kind == "json":
                    txt = cf._read(p, MAX_TEXT)
                elif kind == "csv":
                    txt = cf._read(p, MAX_TEXT)
                else:
                    continue
            except OSError:
                continue
            if txt.strip():
                yield rel, kind, txt


# ------------------------------------------------------------------ reading one file

def platform_counts(text: str) -> Counter:
    c: Counter = Counter()
    for k, rx in PLATFORM_WORDS.items():
        n = len(re.findall(rx, text, re.I))
        if n:
            c[k] = n
    return c


def social_score(rel: str, text: str) -> int:
    pc = platform_counts(text)
    return len(SOCIAL_WORDS.findall(text)) + sum(min(n, 5) for n in pc.values()) + (4 if NAME_HINT.search(Path(rel).stem) else 0)


def _calendar_rows(text: str) -> list[dict]:
    """Rows of a content calendar CSV: a topic column plus (optionally) a platform and a date. Empty when the file is not shaped like one."""
    try:
        rows = list(csv.reader(text.splitlines(), delimiter="\t" if text.count("\t") > text.count(",") else ","))
    except csv.Error:
        return []
    if len(rows) < 2:
        return []
    head = [h.strip().lower() for h in rows[0]]
    ti = next((i for i, h in enumerate(head) if h in CAL_TOPIC), None)
    if ti is None:
        return []
    pi = next((i for i, h in enumerate(head) if h in CAL_PLATFORM), None)
    di = next((i for i, h in enumerate(head) if h in CAL_DATE), None)
    out = []
    for r in rows[1:200]:
        if len(r) > ti and r[ti].strip():
            out.append({"topic": _clean(r[ti], 160), "platform": _clean(r[pi], 20).lower() if pi is not None and len(r) > pi else "", "date": _clean(r[di], 20) if di is not None and len(r) > di else ""})
    return out


def read_file(rel: str, kind: str, text: str) -> dict:
    """What one file says about social media. Everything is short, redacted text; counts, not copies."""
    red = cf.redact(text)
    f: dict = {"platforms": platform_counts(red), "handles": [], "cadence": [], "themes": [], "voice": [], "goals": [], "audience": [], "hashtags": Counter(), "topics": [], "drafts": 0, "others": []}
    for m in PROFILE_URL.finditer(red):
        host = m.group(1).lower().replace("linkedin.com/in", "linkedin").replace("linkedin.com/company", "linkedin").replace("reddit.com/user", "reddit").replace("twitter", "x")
        f["handles"].append((host, m.group(2)))
    for m in HANDLE.finditer(red):
        window = red[max(0, m.start() - 60): m.end() + 60].lower()
        host = next((k for k, rx in PLATFORM_WORDS.items() if re.search(rx, window, re.I)), "")
        f["handles"].append((host, m.group(1)))
    for m in CADENCE.finditer(red):
        f["cadence"].append(_clean(m.group(0), 90))
    for m in CADENCE2.finditer(red):
        f["cadence"].append(_clean(m.group(0), 60))
    for line in red.splitlines():
        if line.count("|") >= 2:          # a table row is not a sentence about the plan
            continue
        for rx, key in ((VOICE_LINE, "voice"), (GOAL_LINE, "goals"), (AUDIENCE_LINE, "audience")):
            m = rx.search(line)
            if m:
                f[key].append(_clean(m.group(m.lastindex), 160))
    for m in HASHTAG.finditer(red):
        f["hashtags"][m.group(1).lower()] += 1
    for k, rx in OTHER_PLATFORMS.items():
        if re.search(rx, red, re.I):
            f["others"].append(k)
    lines = red.splitlines()
    for i, line in enumerate(lines):
        if THEME_HEAD.match(line):
            for nxt in lines[i + 1: i + 14]:
                b = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.{4,120})$", nxt)
                if b:
                    f["themes"].append(_clean(re.sub(r"\*\*|__", "", b.group(1)), 100))
                elif nxt.strip() and f["themes"] and not nxt.strip().startswith(("-", "*", "•")):
                    break
    if kind == "csv":
        cal = _calendar_rows(text)
        f["drafts"] = len(cal)
        f["topics"] += [(r["topic"], r["platform"]) for r in cal[:12]]
        for r in cal:
            if r["platform"] in PLATFORM_WORDS:
                f["platforms"][r["platform"]] += 1
    elif Path(rel).stem and re.search(r"(idea|post|calendar|caption|content)", Path(rel).stem, re.I):
        for line in lines:
            b = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.{15,160})$", line)
            if b and not THEME_HEAD.match(line) and _clean(re.sub(r"\*\*|__", "", b.group(1)), 100) not in f["themes"]:     # a theme is a theme, not also a post idea
                f["topics"].append((_clean(re.sub(r"\*\*|__", "", b.group(1)), 160), ""))
                if len(f["topics"]) >= 12:
                    break
    return f


# ------------------------------------------------------------------ putting the findings together (pure)

def combine(per_file: list[tuple[str, int, dict]]) -> dict:
    """The findings across files: ranked platforms, handles by platform, cadence lines, themes, voice, hashtags, goals, audience, topics with their file."""
    plats: Counter = Counter()
    handles: dict[tuple[str, str], int] = {}
    cadence: list[str] = []; themes: list[str] = []; voice: list[str] = []; goals: list[str] = []; audience: list[str] = []; others: set[str] = set()
    tags: Counter = Counter(); topics: list[dict] = []; drafts = 0
    for rel, _score, f in per_file:
        plats.update(f["platforms"]); tags.update(f["hashtags"]); others.update(f["others"]); drafts += f["drafts"]
        for h in f["handles"]:
            handles[h] = handles.get(h, 0) + 1
        for key, dst in (("cadence", cadence), ("themes", themes), ("voice", voice), ("goals", goals), ("audience", audience)):
            for x in f[key]:
                if x and x.lower() not in (y.lower() for y in dst):
                    dst.append(x)
        for t, pf in f["topics"]:
            if len(t) >= 12 and len(t.split()) >= 2 and not any(t.lower() == y["text"].lower() for y in topics):
                topics.append({"text": t, "platform": pf if pf in PLATFORM_WORDS else "", "file": rel})
    named = {h for (p, h) in handles if p}
    hs = [{"platform": p, "handle": h, "mentions": n} for (p, h), n in sorted(handles.items(), key=lambda kv: -kv[1]) if len(h) >= 3 and not h.lower().endswith((".com", ".org", ".net")) and (p or h not in named)]
    return {"platforms": [{"key": k, "mentions": n} for k, n in plats.most_common(6)], "handles": hs[:12], "cadence": cadence[:6], "themes": themes[:10], "voice": voice[:4], "goals": goals[:4],
            "audience": audience[:4], "hashtags": [h for h, _ in tags.most_common(12)], "topics": topics[:24], "drafts": drafts, "others": sorted(others)}


def questions_for(findings: dict) -> list[dict]:
    """The questions to ask the member, one at a time, about how to use what was found. Each has fixed options; nothing is applied until the member answers in Citadel."""
    q: list[dict] = []
    plats = findings.get("platforms") or []
    if plats:
        top = plats[0]
        q.append({"id": "platforms", "kind": "platforms", "text": f"Your earlier plan is mostly about {top['key'].title()} ({top['mentions']} mentions)" + (f", then {', '.join(p['key'].title() for p in plats[1:3])}" if len(plats) > 1 else "") + ". Should this Function use these platforms, in this order?",
                  "options": [{"value": "use", "label": "Yes, use them"}, {"value": "main_only", "label": "Only the main one, I will pick the second"}, {"value": "skip", "label": "No, I will choose myself"}]})
    by_plat: dict[str, list[str]] = {}
    for h in findings.get("handles") or []:
        if h["platform"]:
            by_plat.setdefault(h["platform"], []).append(h["handle"])
    for pf, hs in list(by_plat.items())[:3]:
        if len(hs) == 1:
            q.append({"id": f"handle:{pf}", "kind": "handle", "platform": pf, "handle": hs[0], "text": f"Is @{hs[0]} your {pf.title()} account for this business?", "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No, a different one"}]})
        else:
            q.append({"id": f"handle:{pf}", "kind": "handle", "platform": pf, "text": f"I found more than one {pf.title()} handle ({', '.join('@' + x for x in hs[:3])}). Which is the account for this business?",
                      "options": [{"value": x, "label": "@" + x} for x in hs[:3]] + [{"value": "none", "label": "None of them"}]})
    if findings.get("cadence"):
        q.append({"id": "cadence", "kind": "cadence", "text": f"Your plan said: \"{findings['cadence'][0]}\". Presence plans one post a day on weekdays by default. Keep your own rhythm in mind when you work through the week?",
                  "options": [{"value": "note", "label": "Yes, note it for this Function"}, {"value": "default", "label": "No, use Presence's rhythm"}]})
    if findings.get("themes"):
        q.append({"id": "themes", "kind": "themes", "text": f"I found these content themes: {'; '.join(findings['themes'][:5])}. Bring them in as ideas to make content from (you can pick the pillar for each in Research)?",
                  "options": [{"value": "import", "label": "Yes, add them as ideas"}, {"value": "skip", "label": "No"}]})
    if findings.get("voice"):
        q.append({"id": "voice", "kind": "voice", "text": f"Your notes describe the voice as: \"{findings['voice'][0]}\". Which tone should the Studio start with?",
                  "options": [{"value": "friendly", "label": "Friendly and warm"}, {"value": "expert", "label": "Calm and expert"}, {"value": "bold", "label": "Direct and bold"}, {"value": "skip", "label": "Keep Presence's default"}]})
    if findings.get("topics"):
        q.append({"id": "topics", "kind": "topics", "text": f"I found {len(findings['topics'])} post ideas or drafts from your earlier work. Add them to your Research shelf, so the plan and the Studio can use them?",
                  "options": [{"value": "import", "label": "Yes, add them"}, {"value": "skip", "label": "No"}]})
    if findings.get("hashtags"):
        q.append({"id": "hashtags", "kind": "hashtags", "text": f"You already use hashtags like {' '.join('#' + h for h in findings['hashtags'][:4])}. Keep them in your notes for this Function?",
                  "options": [{"value": "note", "label": "Yes, keep them"}, {"value": "skip", "label": "No"}]})
    if findings.get("goals") or findings.get("audience"):
        q.append({"id": "goals", "kind": "goals", "text": "Your earlier plan has goals" + (" and an audience" if findings.get("audience") else "") + ": " + " | ".join((findings.get("goals") or [])[:1] + (findings.get("audience") or [])[:1]) + ". Keep this in your Function notes so the drafts stay on target?",
                  "options": [{"value": "note", "label": "Yes, keep it"}, {"value": "skip", "label": "No"}]})
    if findings.get("others"):
        q.append({"id": "others", "kind": "others", "text": f"Your plan also mentions {', '.join(x.title() for x in findings['others'])}. Presence does not plan content for those yet. Keep them as your own channel outside Presence?",
                  "options": [{"value": "note", "label": "Yes, note it"}, {"value": "skip", "label": "No"}]})
    return q


# ------------------------------------------------------------------ the whole thing

def run_context(engine: str, out=print, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    try:
        folders = inherited_folders(engine)
    except SystemExit as e:
        out(str(e))
        return 1
    scored: list[tuple[str, int, dict, str]] = []
    scanned = 0
    for root in folders:
        for rel, kind, text in walk_texts(root):
            scanned += 1
            sc = social_score(rel, text)
            if sc >= 3:
                scored.append((f"{root.name}/{rel}", sc, read_file(rel, kind, text), kind))
    scored.sort(key=lambda x: -x[1])
    keep = scored[:MAX_SOURCES]
    if not keep:
        out(f"I looked through {scanned} files in {len(folders)} folder(s) of engine '{engine}' and found no social media plan or notes. If you have one, attach its folder: python dse.py context {engine} --add <folder>")
        return 0
    findings = combine([(r, s, f) for r, s, f, _ in keep])
    questions = questions_for(findings)
    result = {"v": 1, "kind": "presence-context", "made": today.isoformat(), "engine": engine, "folders": [p.name for p in folders], "scanned": scanned,
              "sources": [{"path": r, "kind": k, "score": s, "platforms": [p for p, _ in f["platforms"].most_common(3)]} for r, s, f, k in keep], "findings": findings, "questions": questions}
    LISTS.mkdir(parents=True, exist_ok=True)
    p = LISTS / f"{engine}-presence-context.json"
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out(f"Looked through {scanned} files in {len(folders)} folder(s) of engine '{engine}'. {len(keep)} read like social media work. {len(questions)} question(s) for you in Presence > Earlier plan. Saved {p.name}.")
    for r, s, _f, _k in keep[:8]:
        out(f"  {s:3}  {r}")
    return 0


def cli(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 2
    return run_context(args[0])


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
