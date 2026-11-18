"""Presence: find the social media plan you already have inside an engine's folder, understand it, and ask you how to use it, so Presence builds on your earlier work instead of replacing it.

    python dse.py presence context <engine> [--ai]

A Function in Presence can be linked to an engine, and then it inherits that engine's folders: the folders attached to the engine (python dse.py context <engine> --add <folder>) and the engine's own
folder. This reads them read-only, with the SAME safety rules as the engine context folders (never _private-keys, the encrypted vault, .ssh, .aws, .env files, key, token or password files,
archives or encrypted files; anything that looks like a key or password is hidden; nothing is changed, moved or deleted). It looks for files that read like social media work: a content plan or calendar, a
posting schedule, brand voice notes, hashtag lists, post drafts or ideas, notes from an AI chat about growing on social media. From them it keeps, in plain counts and short quotes:
  * which platforms the plan is about and how much,   * account handles,   * the posting rhythm it wanted,   * content themes or pillars,   * the voice or tone it asked for,
  * hashtags,   * goals and the audience,   * post ideas and drafts (with the file each came from).
With --ai, this PC's own AI (Ollama; the text never leaves the PC) also reads the start of the strongest files and adds a short summary and up to three open questions of its own, because rules cannot understand every kind of plan. Then it writes my-lists/<engine>-presence-context.json for Presence > Earlier plan, with QUESTIONS for you: how to bring each finding into Presence (keep, change or leave out). It decides nothing for you.
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
MAX_JSON = 600_000                     # an idea bank or a schedule can be big: it is read whole so it can be understood, then only short findings are kept
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
NOT_HANDLES = {"p", "reel", "reels", "explore", "watch", "intent", "share", "sharer", "tags", "hashtag", "video", "videos", "channel", "c", "user", "users", "in", "company", "groups", "pages", "profile", "stories", "story", "tv", "results", "search", "home", "feed", "login", "signup", "about", "help", "privacy", "terms", "pin", "pins"}
NOT_AT_WORDS = {"media", "keyframes", "import", "font", "charset", "page", "supports", "container", "layer", "property", "apply", "screen", "tailwind", "namespace", "everyone", "channel", "here", "all", "mention", "example", "handle", "username", "yourname", "name"}
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


WEBHOOK = re.compile(r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I)
OPAQUE = re.compile(r"\b(?=[A-Za-z0-9_\-.]*\d)(?=[A-Za-z0-9_\-.]*[A-Za-z])[A-Za-z0-9_\-.]{28,}\b")
SECRETY_LINE = re.compile(r"\b(password|passwd|passcode|token|secret|webhook|api[ _-]?key|credentials?|login (details|info))\b", re.I)


def scrub(text: str) -> str:
    """cf.redact plus what Presence itself handles: Discord webhook addresses, long opaque tokens, and any line that talks about a password, token, secret, webhook or key (the whole line is dropped, so nothing around a secret survives)."""
    t = WEBHOOK.sub("[hidden]", cf.redact(text or ""))
    t = OPAQUE.sub("[hidden]", t)
    return "\n".join("[line hidden]" if SECRETY_LINE.search(ln) else ln for ln in t.splitlines())


def _clean(s: str, n: int = 200) -> str:
    return re.sub(r"\s+", " ", scrub(s)).strip(" -*#>|\t\"'“”")[:n]


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
                       and depth + 1 <= cf.MAX_DEPTH and cf.inside(root, Path(dirpath) / d)]
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
                    txt = cf._read(p, MAX_JSON)
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
    # a file named like a calendar or a schedule is the plan itself: it always ranks high, so a long list of other files cannot push it out of the top
    return len(SOCIAL_WORDS.findall(text)) + sum(min(n, 5) for n in pc.values()) + (4 if NAME_HINT.search(Path(rel).stem) else 0) + (40 if re.search(r"calendar|schedule", Path(rel).stem, re.I) else 0)


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


# ------------------------------------------------------------------ calendars, schedules, idea banks, posting times, brand files

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
ISO_RANGE = re.compile(r"(20\d\d-\d\d-\d\d)[-_ ]+(?:to|until|through|-)[-_ ]+(20\d\d-\d\d-\d\d)")
DAY_MONTH = re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(20\d\d))?\b", re.I)
TIMES_LINE = re.compile(r"(?:^|\.\s+)\s*(?:\*\*|[-*]\s*)?(?:post(?:ing)? times?|times?|posting schedule)\s*:\s*([^\n]{8,140})", re.I | re.M)
CLOCK = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s?(?:am|pm)\b", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".pdf", ".ai", ".psd", ".fig", ".ico"}
BRAND_DIR = re.compile(r"^(brand|branding|logos?|brand[-_ ]?kit|brand[-_ ]?assets|identity)$", re.I)


def _date(y: int, m: int, d: int):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def _range_of(rel: str, text: str):
    """The date range a calendar file says it covers: two ISO dates in its name, else two dates in its first lines (like '10 Dec - 08 Jan 2027')."""
    m = ISO_RANGE.search(rel)
    if m:
        a, b = [dt.date.fromisoformat(x) for x in (m.group(1), m.group(2))]
        return (a, b) if a <= b else None
    head = "\n".join(text.splitlines()[:3])
    hits = [(int(g[0]), MONTHS[g[1][:3].lower()], int(g[2]) if g[2] else None) for g in DAY_MONTH.findall(head)]
    if len(hits) >= 2:
        yb = hits[-1][2] or dt.date.today().year
        d2 = _date(yb, hits[-1][1], hits[-1][0])
        if not d2:
            return None
        ya = hits[0][2] or (yb if hits[0][1] <= hits[-1][1] else yb - 1)
        d1 = _date(ya, hits[0][1], hits[0][0])
        return (d1, d2) if d1 and d1 <= d2 else None
    return None


def _cell_date(cell: str, rng):
    """A date in a table's first column: 2026-12-10, '10 Dec 2026' or 'Thu 10 Dec' (the year is taken from the range the file covers)."""
    m = ISO.search(cell)
    if m:
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = DAY_MONTH.search(cell)
    if not m:
        return None
    mon, day = MONTHS[m.group(2)[:3].lower()], int(m.group(1))
    if m.group(3):
        return _date(int(m.group(3)), mon, day)
    if rng:
        for y in sorted({rng[0].year, rng[1].year}):
            d = _date(y, mon, day)
            if d and rng[0] - dt.timedelta(days=3) <= d <= rng[1] + dt.timedelta(days=3):
                return d
    return None


EMPTY_CELL = {"", "-", "\u2013", "\u2014", "n/a", "none", "tbd"}


def schedule_from(rel: str, text: str, kind: str) -> dict | None:
    """Scheduled content in a markdown calendar table (a Date column, one column per kind of post) or a date-keyed JSON file: the first and last day, the number of items, the days and the post ideas with their ids removed."""
    items = 0
    days: set = set()
    topics: list[tuple[str, str]] = []
    cols: Counter = Counter()
    if kind == "json":
        try:
            j = json.loads(text)
        except ValueError:
            return None
        if not isinstance(j, dict):
            return None
        for k, v in j.items():
            m = ISO.fullmatch(str(k))
            d = _date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
            if d and isinstance(v, (dict, list)):
                n = len([x for x in (v.values() if isinstance(v, dict) else v) if x])
                if n:
                    days.add(d); items += n
                    if isinstance(v, dict):
                        cols.update(str(c).lower() for c, x in v.items() if x)
    else:
        rng = _range_of(rel, text)
        head: list[str] | None = None
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                head = None if not line.strip() else head
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if head is None:
                head = [c.lower() for c in cells]
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if not head or not re.search(r"\b(date|day|when)\b", head[0]):
                continue
            d = _cell_date(cells[0], rng)
            if not d:
                continue
            filled = [(head[i] if i < len(head) else "", c) for i, c in enumerate(cells) if i > 0 and c.lower() not in EMPTY_CELL]
            if filled:
                days.add(d); items += len(filled)
                for h, c in filled:
                    cols[h] += 1
                    t = re.sub(r"^[A-Za-z]{1,3}\d{1,4}\s*[:\-]\s*", "", _clean(c, 160))     # "ED60: 25 of 25 studios..." keeps the sentence, not the id
                    if len(t.split()) >= 3:
                        topics.append((t, ""))
    if not days or items == 0:
        return None
    return {"schedule": {"from": min(days).isoformat(), "to": max(days).isoformat(), "days": len(days), "items": items, "columns": [c for c, _ in cols.most_common(5) if c]}, "topics": topics}


def ideas_from_json(text: str) -> list[tuple[str, str]]:
    """Post ideas from a JSON idea bank: a list (or {'ideas': [...]}) of objects with a topic and hooks. The first hook is the idea, without markup."""
    try:
        j = json.loads(text)
    except ValueError:
        return []
    arr = j.get("ideas") if isinstance(j, dict) else j
    if isinstance(arr, dict):
        arr = list(arr.values())
    out: list[tuple[str, str]] = []
    for it in (arr if isinstance(arr, list) else [])[:200]:
        if not isinstance(it, dict):
            continue
        hooks = it.get("hooks") if isinstance(it.get("hooks"), list) else []
        raw = str(hooks[0]) if hooks else str(it.get("topic") or it.get("title") or "")
        t = _clean(re.sub(r"<[^>]+>", "", raw), 160)
        if len(t.split()) >= 3:
            out.append((t, ""))
    return out[:12]


HEX_COLOR = re.compile(r"(?<![0-9A-Za-z&])#([0-9A-Fa-f]{6})(?![0-9A-Za-z])")
STYLE_NAME = re.compile(r"(brand|style|palette|colou?r|design|theme|identity|guideline)", re.I)
FONT_NAMES = ("Playfair Display", "DM Serif Display", "Cormorant", "Merriweather", "Georgia", "Lora", "Times New Roman", "Montserrat", "Poppins", "Inter", "Roboto", "Open Sans", "Lato", "Raleway", "Oswald",
              "DM Sans", "Nunito", "Source Sans", "Segoe UI", "Arial", "Helvetica", "Bebas Neue")


def style_from(items: list) -> dict | None:
    """The colours (hex codes, most used first) and fonts a brand or plan file names: only values that really appear in the text. None when there is no colour. Pure white and pure black are kept only when nothing else is named."""
    cols: Counter = Counter()
    fonts: Counter = Counter()
    for _rel, text in items:
        for m in HEX_COLOR.finditer(text):
            cols["#" + m.group(1).upper()] += 1
        for f in FONT_NAMES:
            n = len(re.findall(r"(?<![A-Za-z])" + re.escape(f) + r"(?![A-Za-z])", text))
            if n:
                fonts[f] += n
    colors = [c for c, _ in cols.most_common(12)]
    real = [c for c in colors if c not in ("#FFFFFF", "#000000")]
    colors = (real or colors)[:6]
    if not colors:
        return None
    return {"colors": colors, "fonts": [f for f, _ in fonts.most_common(2)]}


def brand_files(root: Path) -> list[str]:
    """The names (never the contents) of files in a brand, branding or logo folder: pictures and design files that cannot be read as text but show a brand exists."""
    out: list[str] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in sorted(dirnames) if d.lower() not in cf.FORBIDDEN_DIRS and not d.startswith(".") and not (Path(dirpath) / d).is_symlink() and cf.inside(root, Path(dirpath) / d)
                       and len(Path(dirpath).relative_to(root).parts) < cf.MAX_DEPTH]
        if BRAND_DIR.match(Path(dirpath).name):
            for fn in sorted(filenames):
                if Path(fn).suffix.lower() in IMAGE_EXT and not cf.SECRET_NAME.search(fn):
                    out.append(f"{Path(dirpath).name}/{fn}")
        if len(out) >= 12:
            break
    return out[:12]


def read_file(rel: str, kind: str, text: str) -> dict:
    """What one file says about social media. Everything is short, redacted text; counts, not copies."""
    red = scrub(text)
    f: dict = {"platforms": platform_counts(red), "handles": [], "cadence": [], "themes": [], "voice": [], "goals": [], "audience": [], "hashtags": Counter(), "topics": [], "drafts": 0, "others": [], "schedule": None, "times": []}
    for m in PROFILE_URL.finditer(red):
        host = m.group(1).lower().replace("linkedin.com/in", "linkedin").replace("linkedin.com/company", "linkedin").replace("reddit.com/user", "reddit").replace("twitter", "x")
        if m.group(2).lower() not in NOT_HANDLES and not m.group(2).lower().startswith(("watch", "reel")):
            f["handles"].append((host, m.group(2)))
    for m in HANDLE.finditer(red):
        window = red[max(0, m.start() - 60): m.end() + 60].lower()
        host = next((k for k, rx in PLATFORM_WORDS.items() if re.search(rx, window, re.I)), "")
        if m.group(1).lower() not in NOT_AT_WORDS:
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
    sch = schedule_from(rel, text, kind) if kind in ("text", "json", "doc") else None
    if sch:
        f["schedule"] = sch["schedule"]
        f["topics"] = (sch["topics"][:12] + f["topics"])[:16]
        f["drafts"] += sch["schedule"]["items"]
    if kind == "json" and not sch:
        f["topics"] += ideas_from_json(text)
    for m in TIMES_LINE.finditer(red):
        if CLOCK.search(m.group(1)):                  # only a line that really gives clock times, not any sentence with the word "time"
            f["times"].append(_clean(m.group(1), 120))
    return f


# ------------------------------------------------------------------ putting the findings together (pure)

def combine(per_file: list[tuple[str, int, dict]]) -> dict:
    """The findings across files: ranked platforms, handles by platform, cadence lines, themes, voice, hashtags, goals, audience, topics with their file."""
    plats: Counter = Counter()
    handles: dict[tuple[str, str], int] = {}
    cadence: list[str] = []; themes: list[str] = []; voice: list[str] = []; goals: list[str] = []; audience: list[str] = []; others: set[str] = set()
    tags: Counter = Counter(); topics: list[dict] = []; drafts = 0; times: list[str] = []; sched: dict | None = None
    for rel, _score, f in sorted(per_file, key=lambda x: 0 if x[2].get("schedule") else 1):      # scheduled items come first: they are what the person really planned
        plats.update(f["platforms"]); tags.update(f["hashtags"]); others.update(f["others"]); drafts += f["drafts"]
        for tm in f.get("times", []):
            if tm and tm.lower() not in (y.lower() for y in times):
                times.append(tm)
        sc = f.get("schedule")
        if sc:
            sched = dict(sc) if not sched else {"from": min(sched["from"], sc["from"]), "to": max(sched["to"], sc["to"]), "days": sched["days"] + sc["days"], "items": sched["items"] + sc["items"],
                                                  "columns": list(dict.fromkeys(sched["columns"] + sc["columns"]))[:5]}
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
            "audience": audience[:4], "hashtags": [h for h, _ in tags.most_common(12)], "topics": topics[:24], "drafts": drafts, "others": sorted(others), "schedule": sched, "times": times[:3], "brand": [], "style": None}


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
    sch = findings.get("schedule")
    if sch and sch.get("to", "") >= dt.date.today().isoformat():
        last = dt.date.fromisoformat(sch["to"])
        q.append({"id": "schedule", "kind": "schedule", "text": f"Your earlier plan already has {sch['items']} posts scheduled from {sch['from']} to {sch['to']}. Presence plans a post a day too, so the two would collide until {last.strftime('%d %b %Y')}. What should Presence do about those weeks?",
                  "options": [{"value": "start_after", "label": f"Start Presence's plan the day after, {(last + dt.timedelta(days=1)).isoformat()}"}, {"value": "alongside", "label": "Run beside my schedule, I will keep both in mind"}, {"value": "ignore", "label": "Ignore it"}]})
    elif sch:
        q.append({"id": "schedule", "kind": "schedule", "text": f"Your earlier schedule ran {sch['from']} to {sch['to']} ({sch['items']} posts) and is over. Keep a note of it, so Presence builds on what you already published?",
                  "options": [{"value": "note", "label": "Yes, keep a note"}, {"value": "ignore", "label": "No"}]})
    if findings.get("times"):
        q.append({"id": "times", "kind": "times", "text": f"Your plan says when to post: \"{findings['times'][0]}\". Keep that in your notes so Presence's reminders follow your times?",
                  "options": [{"value": "note", "label": "Yes, keep it"}, {"value": "skip", "label": "No"}]})
    if findings.get("style"):
        st = findings["style"]
        q.append({"id": "style", "kind": "style", "text": f"Your plan names these brand colours: {', '.join(st['colors'][:4])}" + (f" and the font{'s' if len(st['fonts']) > 1 else ''} {' and '.join(st['fonts'])}" if st["fonts"] else "") + ". Use them as your own look for slides, pictures and videos (made readable, so the words never get lost)?",
                  "options": [{"value": "adopt", "label": "Yes, use my brand look"}, {"value": "skip", "label": "No, keep Presence's looks"}]})
    if findings.get("brand"):
        q.append({"id": "brand", "kind": "brand", "text": f"I found brand files ({', '.join(findings['brand'][:3])}). Pictures cannot be read as text, but your logo can go on every slide: put it in the toolkit's my-pictures folder. Note that for this Function?",
                  "options": [{"value": "note", "label": "Yes, note it"}, {"value": "skip", "label": "No"}]})
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


# ------------------------------------------------------------------ the optional local AI reading

OLLAMA = "http://localhost:11434/api/chat"
AI_BUDGET = 3200            # characters of the plan shown to the model, in all
AI_PROMPT = ("You read a person's earlier social media plan and help them combine it with a new planning tool. Reply with JSON only, no other words: "
             '{"summary": "two or three plain sentences saying what the plan is trying to do, who it is for and how it works", '
             '"questions": ["up to three short questions that would help use this plan well, each about something the plan leaves unclear or in conflict"]}. '
             "Use only what is in the text. Never invent facts. If something is unclear, ask about it instead of guessing.")


def ai_digest(sources: list[tuple[str, str]], budget: int = AI_BUDGET) -> str:
    """A short, redacted piece of the strongest files for the local model: the start of each file, in order of strength, up to the budget."""
    parts, left = [], budget
    for rel, text in sources:
        if left < 200:
            break
        take = scrub(re.sub(r"\n{3,}", "\n\n", text.strip()))[: min(left, 1100)]
        parts.append(f"--- {rel}\n{take}")
        left -= len(take) + len(rel) + 6
    return "\n".join(parts)


def _ollama_chat(model: str, system: str, user: str, timeout: int = 150) -> str:
    import urllib.request
    body = json.dumps({"model": model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "options": {"temperature": 0.2}}).encode("utf-8")
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # always this PC's own Ollama: the plan never leaves this PC
        return str(json.loads(r.read()).get("message", {}).get("content", ""))


def parse_ai(raw: str) -> dict | None:
    """The model's reply, made safe: a short plain summary and up to three plain questions that end in '?'. Anything else gives None."""
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(j, dict):
        return None
    def plain(x, n):
        return re.sub(r"[\x00-\x1f<>]+", " ", re.sub(r"\s+", " ", str(x or ""))).strip()[:n]
    summary = plain(j.get("summary"), 500)
    qs = []
    for q in (j.get("questions") if isinstance(j.get("questions"), list) else [])[:5]:
        t = plain(q if not isinstance(q, dict) else q.get("text"), 220)
        if len(t) >= 12 and t.endswith("?") and t.lower() not in (x.lower() for x in qs):
            qs.append(t)
    if len(summary) < 20 and not qs:
        return None
    return {"summary": summary, "questions": qs[:3]}


def ai_read(sources: list[tuple[str, str]], model: str = "", chat=None, installed=None) -> dict | None:
    """Optional: this PC's own AI (Ollama) reads the start of the strongest files and says what the plan is for, with a few questions. None when there is no model or the answer is not usable."""
    chat = chat or _ollama_chat
    if not model:
        from chat import ollama_model as om
        have = (installed or om.installed)()
        if not have:
            return None
        model = om.pick(have=have)[0]
    digest = ai_digest(sources)
    if len(digest) < 80:
        return None
    try:
        got = parse_ai(chat(model, AI_PROMPT, digest))
    except Exception:
        return None
    return {**got, "model": model} if got else None


# ------------------------------------------------------------------ the whole thing

def run_context(engine: str, out=print, today: dt.date | None = None, ai: bool = False, chat=None, installed=None) -> int:
    today = today or dt.date.today()
    try:
        folders = inherited_folders(engine)
    except SystemExit as e:
        out(str(e))
        return 1
    scored: list[tuple[str, int, dict, str]] = []
    texts: dict[str, str] = {}
    style_items: list[tuple[str, str]] = []
    scanned = 0
    for root in folders:
        for rel, kind, text in walk_texts(root):
            scanned += 1
            sc = social_score(rel, text)
            if (sc >= 3 or STYLE_NAME.search(rel)) and len(style_items) < 60:
                style_items.append((rel, text))
            if sc >= 3:
                scored.append((f"{root.name}/{rel}", sc, read_file(rel, kind, text), kind))
                texts[f"{root.name}/{rel}"] = text
    scored.sort(key=lambda x: -x[1])
    keep = scored[:MAX_SOURCES]
    if not keep:
        out(f"I looked through {scanned} files in {len(folders)} folder(s) of engine '{engine}' and found no social media plan or notes. If you have one, attach its folder: python dse.py context {engine} --add <folder>")
        return 0
    findings = combine([(r, s, f) for r, s, f, _ in keep])
    findings["brand"] = [b for root in folders for b in brand_files(root)][:8]
    findings["style"] = style_from(style_items)
    questions = questions_for(findings)
    reading = ai_read([(r, texts[r]) for r, _s, _f, _k in keep if r in texts][:6], chat=chat, installed=installed) if ai else None
    if reading:
        questions += [{"id": f"open:{i}", "kind": "open", "text": q, "options": []} for i, q in enumerate(reading["questions"], 1)]
    result = {"v": 1, "kind": "presence-context", "made": today.isoformat(), "engine": engine, "folders": [p.name for p in folders], "scanned": scanned,
              "sources": [{"path": r, "kind": k, "score": s, "platforms": [p for p, _ in f["platforms"].most_common(3)]} for r, s, f, k in keep], "findings": findings, "questions": questions, **({"ai": reading} if reading else {})}
    LISTS.mkdir(parents=True, exist_ok=True)
    p = LISTS / f"{engine}-presence-context.json"
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    out(f"Looked through {scanned} files in {len(folders)} folder(s) of engine '{engine}'. {len(keep)} read like social media work. {len(questions)} question(s) for you in Presence > Earlier plan. Saved {p.name}.")
    if ai:
        out(f"My PC's AI ({reading['model']}) also read it: {reading['summary'][:200]}" if reading else "No local AI answered (Ollama may be off), so this is the reading by rules only.")
    for r, s, _f, _k in keep[:8]:
        out(f"  {s:3}  {r}")
    return 0


def cli(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 2
    return run_context(args[0], ai="--ai" in args[1:])


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
