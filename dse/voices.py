"""Voices: the thinkers, teachers and practitioners worth learning from, one library, with the sources they themselves made public.

    python dse.py voices list [--stratum wisdom|empowerment|structure|sales|finance] [--path smb|ascent|...]
    python dse.py voices show <figure>                          who they are, what is known, which sources are checked, what is new
    python dse.py voices verify [<figure>]                      check each source live (nothing is fetched or used until it is verified)
    python dse.py voices fetch <figure>                         download and index the verified public-domain texts and open quotations
    python dse.py voices update [<figure>]                      for living figures: what they have published since last time (their own feeds)
    python dse.py voices ask "how do I stay calm under pressure" [--figure marcus-aurelius] [--stratum wisdom] [--path ascent] [--n 3]
    python dse.py voices today [--stratum wisdom]               one passage for today, with its source
    python dse.py voices note <figure> --text "a line I read" --source "Book, page"      your own notes join the library, marked as yours

What it will and will not use (the rules are in code, not goodwill):
  * PUBLIC-DOMAIN texts from Project Gutenberg (full text, with the book and section as the citation) and quotations from Wikiquote (openly licensed CC BY-SA, shown with that credit,
    sourced quotes only: the misattributed and disputed sections are skipped)
  * a living figure's OWN published feeds only: their blog or newsletter RSS, their YouTube channel's official feed, their podcast feed. These give titles, dates, links and a short
    description, never a copy of the content. You follow the link to read or watch it
  * books still in copyright: the title and year only. Your own notes about them are yours and are kept marked as notes
  * X, LinkedIn, Facebook, Reddit and Instagram are NEVER scraped (their terms forbid it, and our own rule): the profile link is kept and nothing is fetched
  * every answer is a real passage with its source, and says "Voices library, no AI model" so it is never mistaken for the person speaking. Nothing is invented, paraphrased into their voice,
    or attributed to them without a source
The roster (voices/roster.json) is a list YOU can edit: 10 figures for each of 5 strata and 7 for each of the 9 paths. Sources are verified live before use.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as htmllib
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from .common import DATA, ROOT, UA

ROSTER = ROOT / "voices" / "roster.json"
STORE = DATA / "voices"
STRATA = {"wisdom": "Wisdom and philosophy", "empowerment": "Human empowerment and psychology", "structure": "Structure, systems and thinking", "sales": "Sales and persuasion", "finance": "Financial development"}
PATHS = ["smb", "ascent", "revenue", "broadcast", "authority", "gtm", "voiceai", "automation", "ministry"]
SOURCE_TYPES = ("gutenberg", "wikiquote", "feed", "youtube", "books", "links")
LINK_NETWORKS = ("x", "linkedin", "facebook", "reddit", "instagram", "tiktok")
PAUSE = 0.6
CHUNK_WORDS = 110
SHOW_WORDS = 110


# ------------------------------------------------------------------ roster and state

def roster() -> list[dict]:
    return json.loads(ROSTER.read_text(encoding="utf-8"))["figures"]


def figure(fid: str) -> dict:
    f = next((x for x in roster() if x["id"] == (fid or "").lower().strip()), None)
    if not f:
        close = [x["id"] for x in roster() if (fid or "").lower() in x["id"]][:6]
        raise ValueError(f"No figure '{fid}'." + (f" Did you mean: {', '.join(close)}?" if close else " See: python dse.py voices list"))
    return f


def state_path() -> Path:
    return STORE / "state.json"


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verified": {}, "seen": {}}


def save_state(st: dict) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(st, indent=1), encoding="utf-8")


def src_key(f: dict, s: dict) -> str:
    return f"{f['id']}/{s['type']}/{s.get('page') or s.get('search') or s.get('url') or s.get('handle') or s.get('home') or s.get('title') or ''}"[:160]


def is_verified(f: dict, s: dict, st: dict | None = None) -> bool:
    return bool((st or load_state())["verified"].get(src_key(f, s), {}).get("ok"))


# ------------------------------------------------------------------ the network (one place, so tests can replace it)

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36", "Accept-Language": "en", "Cookie": "SOCS=CAI"}


def http_get(url: str, timeout: int = 20, browser: bool = False) -> tuple[int, str]:
    """The one network call (tests replace it). browser=True: asks the way a visitor's browser does (YouTube shows its consent page to anything else)."""
    try:
        h = BROWSER if browser else {**UA, "User-Agent": "Mozilla/5.0 (compatible; DSEToolkit/1.0; Voices library; personal study)"}
        r = requests.get(url, headers=h, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text
    except requests.RequestException:
        return 0, ""


# ------------------------------------------------------------------ public-domain books (Project Gutenberg)

PG_STOP = set("the a an of and on to in for de la le by from with into".split())


def pg_search(query: str) -> list[dict]:
    """Project Gutenberg's own catalogue search: [{id, title}], best first. (Its public API mirror is slow and often times out; this page is not.)"""
    code, body = http_get("https://www.gutenberg.org/ebooks/search/?query=" + requests.utils.quote(query), 30)
    if code != 200:
        return []
    out = []
    for m in re.finditer(r'<li class="booklink">(.*?)</li>', body, re.S):
        i = re.search(r'href="/ebooks/(\d+)"', m.group(1))
        t = re.search(r'<span class="title">(.*?)</span>', m.group(1), re.S)
        if i and t:
            out.append({"id": int(i.group(1)), "title": htmllib.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()})
    return out


def pg_text_url(gid: int) -> str:
    return f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt"


def pg_head(gid: int) -> str:
    code, body = http_get(pg_text_url(gid), 45)
    return body[:6000] if code == 200 else ""


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in PG_STOP}


def gutenberg_resolve(f: dict, s: dict) -> dict | None:
    """The Project Gutenberg book for a roster entry, checked: its own id if the roster has one, else the best search result whose text says the figure wrote it.
    Returns {id, title, text_url} or None. Nothing is accepted on a title match alone: the book's own header must name the author."""
    surname = [w for w in re.findall(r"[a-z]{4,}", f["name"].lower()) if w not in ("saint", "bishop")][-1:] or [""]
    want = _words(s.get("title", "") + " " + s.get("search", "")) - set(surname)
    tried, cands = set(), []
    if s.get("id"):
        cands.append({"id": int(s["id"]), "title": s.get("title", "")})
    for q in dict.fromkeys([s.get("search", ""), s.get("title", ""), (surname[0] + " " + s.get("title", "")).strip(), surname[0]]):
        if not q:
            continue
        found = pg_search(q)
        found = [b for b in found if not re.search(r"index|catalog", b["title"], re.I)]
        found.sort(key=lambda b: -len(want & _words(b["title"])))
        cands += [b for b in found if len(want & _words(b["title"])) >= 1][:4]       # the title must share a word with the one you named: another book by the same author is not accepted
        if len(cands) >= 6:
            break
    for b in cands:
        if b["id"] in tried:
            continue
        tried.add(b["id"])
        head = pg_head(b["id"])
        m = re.search(r"^Author:\s*(.+)$", head, re.M)
        by = (m.group(1) if m else "").lower()
        lang = re.search(r"^Language:\s*(.+)$", head, re.M)
        if head and (not lang or "english" in lang.group(1).lower()) and (surname[0] in by or surname[0] in head[:1500].lower()):
            tm = re.search(r"^Title:\s*(.+)$", head, re.M)
            return {"id": b["id"], "title": (tm.group(1).strip() if tm else b["title"])[:120], "text_url": pg_text_url(b["id"])}
        time.sleep(PAUSE / 2)
    return None


def strip_gutenberg(text: str) -> str:
    m = re.search(r"\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\n", text)
    if m:
        text = text[m.end():]
    m = re.search(r"\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", text)
    return (text[:m.start()] if m else text).strip()


HEADING = re.compile(r"^\s*((?:BOOK|CHAPTER|PART|LETTER|SECTION|CANTO|ARTICLE|QUESTION|DISCOURSE)\s+[IVXLC\d]+\b[^\n]{0,60}|[IVXLC]{1,6}\.\s*[A-Z][^\n]{0,60})\s*$", re.M)


def chunk_text(title: str, text: str) -> list[dict]:
    """Passages of about 110 words, each with a citation locator: the nearest BOOK/CHAPTER/LETTER heading above it."""
    out, section, buf, words = [], "", [], 0
    n = 0

    def flush():
        nonlocal buf, words, n
        if buf:
            n += 1
            body = " ".join(buf).strip()
            out.append({"text": body, "locator": f"{title}, {section}" if section else f"{title}, passage {n}"})
        buf, words = [], 0

    for para in re.split(r"\n\s*\n", text):
        p = re.sub(r"\s+", " ", para).strip()
        if not p:
            continue
        if HEADING.match(p) and len(p.split()) <= 12:
            flush()
            section = " ".join(w if re.fullmatch(r"[IVXLC]+\.?", w) else w.capitalize() for w in p.split()) if p.isupper() else p
            continue
        buf.append(p)
        words += len(p.split())
        if words >= CHUNK_WORDS:
            flush()
    flush()
    return out


# ------------------------------------------------------------------ quotations (Wikiquote, CC BY-SA)

SKIP_SECTIONS = re.compile(r"misattribut|disputed|attributed|quotes about|about\b|see also|external|references|further reading|notes", re.I)


def clean_wiki(s: str) -> str:
    s = re.sub(r"<ref[^>]*?/>|<ref[^>]*?>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return htmllib.unescape(re.sub(r"\s+", " ", s)).strip()


def parse_wikiquote(wikitext: str) -> list[dict]:
    """Sourced top-level quotes only: [{text, source}]. Sections about misattributed, disputed or 'quotes about' are skipped."""
    out, skip, lines = [], False, wikitext.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^=+\s*(.*?)\s*=+\s*$", ln)
        if m:
            skip = bool(SKIP_SECTIONS.search(m.group(1)))
            continue
        if skip or not ln.startswith("*") or ln.startswith("**"):
            continue
        text = clean_wiki(ln.lstrip("* "))
        if not 40 <= len(text) <= 420:
            continue
        src = ""
        for nxt in lines[i + 1:i + 4]:
            if nxt.startswith("**"):
                src = clean_wiki(nxt.lstrip("* "))[:140]
                break
            if nxt.startswith("*"):
                break
        out.append({"text": text, "source": src})
    return out


def wikiquote_get(page: str) -> list[dict]:
    code, body = http_get("https://en.wikiquote.org/w/api.php?action=parse&format=json&prop=wikitext&redirects=1&page=" + requests.utils.quote(page.replace(" ", "_")))
    if code != 200:
        return []
    try:
        return parse_wikiquote(json.loads(body)["parse"]["wikitext"]["*"])
    except (ValueError, KeyError, TypeError):
        return []


# ------------------------------------------------------------------ feeds (their own blog, newsletter, podcast and YouTube channel)

def strip_tags(s: str, n: int = 300) -> str:
    t = htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or ""))).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", t)[:n]


def parse_feed(xml: str) -> list[dict]:
    """RSS 2.0 or Atom (including YouTube's): [{title, link, date, summary}], newest first as the feed gives them."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    items = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        g = lambda name: next((c for c in el if c.tag.split("}")[-1] == name), None)  # noqa: E731
        title = (g("title").text or "").strip() if g("title") is not None else ""
        link_el = g("link")
        link = (link_el.get("href") or (link_el.text or "")).strip() if link_el is not None else ""
        date = ""
        for nm in ("pubDate", "published", "updated", "date"):
            d = g(nm)
            if d is not None and d.text:
                date = d.text.strip()
                break
        summ = ""
        for nm in ("description", "summary", "content", "encoded"):
            d = g(nm)
            if d is not None and (d.text or len(d)):
                summ = strip_tags(d.text or "")
                break
        if not summ:                                   # YouTube puts the description in media:group/media:description
            for sub in el.iter():
                if sub.tag.split("}")[-1] == "description" and sub.text:
                    summ = strip_tags(sub.text)
                    break
        if title and link:
            items.append({"title": strip_tags(title, 160), "link": link, "date": date[:40], "summary": summ})
    return items


COMMON_FEEDS = ("/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml", "/blog/feed", "/blog/feed/", "/blog/rss", "/blog/rss.xml", "/blog/index.xml", "/podcast/feed", "/podcast/feed/", "/feed/podcast", "/?feed=rss2", "/blog?format=rss", "/news/feed", "/articles/feed")


def discover_feed(home: str) -> str:
    """Their own feed: the address the homepage advertises (<link rel="alternate" type="application/rss+xml">), else the usual places a site keeps one. '' if none answers with items."""
    code, body = http_get(home)
    if code == 200:
        for m in re.finditer(r"<link[^>]+>", body, re.I):
            tag = m.group(0)
            if re.search(r"rel=[\"']alternate[\"']", tag, re.I) and re.search(r"type=[\"']application/(rss|atom)\+xml[\"']", tag, re.I):
                h = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
                if h:
                    return requests.compat.urljoin(home, htmllib.unescape(h.group(1)))
    base = re.match(r"https?://[^/]+", home)
    hosts = []
    if base:
        host = base.group(0)
        hosts = [host.replace("http://", "https://")] + ([host.replace("//www.", "//")] if "//www." in host else [host.replace("//", "//www.")])
    for h in dict.fromkeys(hosts):
        for path in COMMON_FEEDS:
            c, b = http_get(h + path)
            if c == 200 and parse_feed(b):
                return h + path
        if code == 200:                              # a link on the homepage that says feed, rss or podcast
            for m in re.finditer(r'href=["\']([^"\']*(?:feed|rss|atom|podcast)[^"\']*)["\']', body, re.I):
                u = requests.compat.urljoin(home, htmllib.unescape(m.group(1)))
                if u.startswith("http") and not re.search(r"\.(css|js|png|jpg|svg)(\?|$)", u):
                    c, b = http_get(u)
                    if c == 200 and parse_feed(b):
                        return u
    return ""


def youtube_feed_url(handle: str) -> str:
    """The channel's official Atom feed, from its @handle or UC channel id."""
    h = (handle or "").strip()
    if re.fullmatch(r"UC[\w-]{22}", h):
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={h}"
    code, body = http_get("https://www.youtube.com/" + (h if h.startswith("@") else "@" + h), 25, browser=True)
    if code != 200:
        return ""
    m = re.search(r"channel_id=(UC[\w-]{22})", body) or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', body) or re.search(r"youtube\.com/channel/(UC[\w-]{22})", body)
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}" if m else ""


def feed_url_for(s: dict) -> str:
    if s["type"] == "youtube":
        return youtube_feed_url(s.get("handle", ""))
    if s.get("url"):
        return s["url"]
    return discover_feed(s["home"]) if s.get("home") else ""


# ------------------------------------------------------------------ verify

def verify_source(f: dict, s: dict) -> dict:
    t = s["type"]
    if t == "gutenberg":
        b = gutenberg_resolve(f, s)
        return ({"ok": True, "detail": f"Project Gutenberg #{b['id']}: {b['title'][:60]}", "gid": b["id"], "gtitle": b["title"], "url": b["text_url"]} if b
                else {"ok": False, "detail": "no Project Gutenberg book of that title by this author was found (add \"id\": <its number from gutenberg.org/ebooks/...> to the source in the roster, or change the title)"})
    if t == "wikiquote":
        q = wikiquote_get(s["page"])
        return {"ok": len(q) >= 3, "detail": f"{len(q)} sourced quotations on Wikiquote" if q else "no Wikiquote page found"}
    if t in ("feed", "youtube"):
        url = feed_url_for(s)
        if not url:
            return {"ok": False, "detail": "no feed found (" + ("channel not found" if t == "youtube" else "the homepage advertises no RSS or Atom feed") + ")"}
        code, body = http_get(url)
        items = parse_feed(body) if code == 200 else []
        return {"ok": bool(items), "detail": f"{len(items)} recent item(s) at {url}" if items else f"feed did not answer or had no items ({url})", "url": url}
    if t == "books":
        bad = []
        sur = [w for w in re.findall(r"[a-z]{4,}", f["name"].lower())][-1:] or [""]
        for b in s.get("list", []):
            found = False
            for title in dict.fromkeys([b["title"], re.split(r"[:(]", b["title"])[0].strip(), re.sub(r"^(the|a|an)\s+", "", re.split(r"[:(]", b["title"])[0].strip(), flags=re.I)]):
                code, body = http_get("https://openlibrary.org/search.json?limit=5&title=" + requests.utils.quote(title))
                try:
                    docs = json.loads(body).get("docs", []) if code == 200 else []
                except ValueError:
                    docs = []
                if any(sur[0] in " ".join(d.get("author_name", [])).lower() for d in docs):
                    found = True
                    break
                time.sleep(PAUSE / 3)
            if not found:
                bad.append(b["title"])
        return {"ok": not bad, "detail": ("all titles found on Open Library" if not bad else "not found on Open Library under this author: " + "; ".join(bad) + " (check the spelling of the title in the roster)")}
    if t == "links":
        bad = [k for k in s.get("urls", {}) if k not in LINK_NETWORKS and k not in ("home", "site")]
        return {"ok": not bad, "detail": "links only, never fetched" + (f"; unknown network {bad}" if bad else "")}
    return {"ok": False, "detail": "unknown source type"}


def verify(fid: str = "") -> str:
    fs = [figure(fid)] if fid else roster()
    st = load_state()
    lines, ok_n, bad_n = [], 0, 0
    for f in fs:
        for s in f.get("sources", []):
            res = verify_source(f, s)
            st["verified"][src_key(f, s)] = {**res, "checked": dt.date.today().isoformat(), "v": CHECK_VERSION}
            ok_n += res["ok"]
            bad_n += not res["ok"]
            lines.append(f"{'OK  ' if res['ok'] else 'FAIL'} {f['name']}: {s['type']}: {res['detail']}")
            time.sleep(PAUSE)
    save_state(st)
    return "\n".join(["# Voices: source check", "", *lines, "", f"{ok_n} source(s) verified, {bad_n} failed. Only verified sources are ever fetched or used. A failed source can be fixed in voices/roster.json (a different title, page or homepage) and checked again.", ""])


# ------------------------------------------------------------------ fetch and index

def fig_dir(fid: str) -> Path:
    return STORE / "library" / fid


def index_path(fid: str) -> Path:
    return STORE / "index" / f"{fid}.json"


def load_index(fid: str) -> list[dict]:
    try:
        return json.loads(index_path(fid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def notes_path(fid: str) -> Path:
    return STORE / "notes" / f"{fid}.json"


def load_notes(fid: str) -> list[dict]:
    try:
        return json.loads(notes_path(fid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def fetch(fid: str) -> str:
    f = figure(fid)
    st = load_state()
    passages, lines = [], []
    for s in f.get("sources", []):
        if s["type"] not in ("gutenberg", "wikiquote"):
            continue
        if not is_verified(f, s, st):
            lines.append(f"- skipped {s['type']} ({s.get('search') or s.get('page')}): not verified yet. Run: python dse.py voices verify {fid}")
            continue
        if s["type"] == "gutenberg":
            v = st["verified"].get(src_key(f, s), {})
            gid, url = v.get("gid"), v.get("url", "")
            if not gid or not url:
                lines.append(f"- {s.get('title') or s['search']}: no checked book address: run voices verify {fid}")
                continue
            code, body = http_get(url, 90)
            if code != 200 or len(body) < 2000:
                lines.append(f"- Gutenberg #{gid}: the text did not download")
                continue
            text = strip_gutenberg(body)
            fig_dir(fid).mkdir(parents=True, exist_ok=True)
            (fig_dir(fid) / f"gutenberg-{gid}.txt").write_text(text, encoding="utf-8")
            title = (s.get("title") or v.get("gtitle") or "").strip()
            chunks = chunk_text(title, text)
            for c in chunks:
                passages.append({**c, "kind": "text", "credit": f"{f['name']}, {c['locator']} (Project Gutenberg #{gid}, public domain)"})
            lines.append(f"- {title}: {len(chunks)} passages from Project Gutenberg #{gid}")
        else:
            qs = wikiquote_get(s["page"])
            for q in qs:
                passages.append({"text": q["text"], "locator": q["source"] or "Wikiquote", "kind": "quote",
                                 "credit": f"{f['name']}{', ' + q['source'] if q['source'] else ''} (Wikiquote, CC BY-SA 4.0)"})
            lines.append(f"- Wikiquote: {len(qs)} sourced quotations")
        time.sleep(PAUSE)
    for n in load_notes(fid):
        passages.append({"text": n["text"], "locator": n["source"], "kind": "note", "credit": f"your own note ({n['source']})"})
    index_path(fid).parent.mkdir(parents=True, exist_ok=True)
    index_path(fid).write_text(json.dumps(passages), encoding="utf-8")
    return f"# Voices: {f['name']}\n\n" + "\n".join(lines or ["- nothing to fetch: this figure has no public-domain text or Wikiquote page verified yet"]) + f"\n\nIndexed {len(passages)} passage(s). Ask with: python dse.py voices ask \"...\" --figure {fid}\n"


# ------------------------------------------------------------------ search (plain BM25, no AI model)

STOP = set("a an and are as at be but by for from has have how i in is it its my of on or so than that the their them then there these they this to was were what when which who why will with you your do does did should would could can me we our".split())


def tokens(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", (s or "").lower()) if w not in STOP]


def stem(w: str) -> str:
    for suf in ("ing", "ers", "ed", "es", "er", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def bm25(query: str, passages: list[dict]) -> list[tuple[float, dict]]:
    q = [stem(w) for w in tokens(query)]
    if not q or not passages:
        return []
    docs = [[stem(w) for w in tokens(p["text"])] for p in passages]
    n, avg = len(docs), (sum(len(d) for d in docs) / len(docs)) or 1
    df = {w: sum(1 for d in docs if w in d) for w in set(q)}
    out = []
    for d, p in zip(docs, passages):
        if not d:
            continue
        score = 0.0
        for w in set(q):
            tf = d.count(w)
            if tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if score > 0:
            out.append((score, p))
    return sorted(out, key=lambda x: -x[0])


def shorten(text: str, words: int = SHOW_WORDS) -> str:
    w = text.split()
    return text if len(w) <= words else " ".join(w[:words]) + " ..."


def pool(figure_id: str = "", stratum: str = "", path: str = "") -> list[tuple[dict, list[dict]]]:
    fs = [figure(figure_id)] if figure_id else [f for f in roster() if (not stratum or stratum in f.get("strata", [])) and (not path or path in f.get("paths", []))]
    return [(f, load_index(f["id"]) or [{"text": n["text"], "locator": n["source"], "kind": "note", "credit": f"your own note ({n['source']})"} for n in load_notes(f["id"])]) for f in fs]


def ask(question: str, figure_id: str = "", stratum: str = "", path: str = "", n: int = 3) -> str:
    if len((question or "").strip()) < 4:
        raise ValueError("Ask a question or give a topic (at least a few letters).")
    if stratum and stratum not in STRATA:
        raise ValueError("Stratum is one of: " + ", ".join(STRATA))
    if path and path not in PATHS:
        raise ValueError("Path is one of: " + ", ".join(PATHS))
    if not 1 <= n <= 8:
        raise ValueError("Ask for 1 to 8 passages.")
    scoped = pool(figure_id, stratum, path)
    allp, empty = [], []
    for f, ps in scoped:
        if not ps:
            empty.append(f["name"])
        for p in ps:
            allp.append({**p, "who": f["name"], "fid": f["id"]})
    hits = bm25(question, allp)
    out = [f"# Voices: \"{question.strip()[:80]}\"", ""]
    if not hits:
        out.append("Nothing in the library matches that yet." + (f" Nothing is fetched yet for: {', '.join(empty[:6])}{'...' if len(empty) > 6 else ''}. Set the library up once: HQ Tools, Voices: set up the library (or python dse.py voices setup)." if empty else " Try other words."))
        return "\n".join(out) + "\n"
    seen_f: dict[str, int] = {}
    shown = 0
    for score, p in hits:
        if seen_f.get(p["fid"], 0) >= 2 and len({h[1]["fid"] for h in hits}) > 1 and shown < n:
            continue
        seen_f[p["fid"]] = seen_f.get(p["fid"], 0) + 1
        shown += 1
        out += [f"{shown}. \"{shorten(p['text'])}\"", f"   {p['credit']}", ""]
        if shown >= n:
            break
    out.append("From the Voices library: real passages with their sources, found by matching your words. No AI model wrote or changed them, and they are not the person speaking now.")
    return "\n".join(out) + "\n"


def today(stratum: str = "wisdom", day: dt.date | None = None) -> str:
    day = day or dt.date.today()
    if stratum not in STRATA:
        raise ValueError("Stratum is one of: " + ", ".join(STRATA))
    cands = []
    for f, ps in pool("", stratum, ""):
        for p in ps:
            if p["kind"] in ("quote", "note") or len(p["text"].split()) <= 70:
                cands.append({**p, "who": f["name"]})
    note = ""
    if not cands:                      # nothing in this area yet: say so, and offer a passage from any area that has some
        for other in STRATA:
            if other == stratum:
                continue
            for f, ps in pool("", other, ""):
                cands += [{**p, "who": f["name"]} for p in ps if p["kind"] in ("quote", "note") or len(p["text"].split()) <= 70]
            if cands:
                note = f"(Nothing is fetched yet for {STRATA[stratum]}, so this one is from {STRATA[other]}.)" + chr(10) * 2
                break
    if not cands:
        return "The library is empty on this PC. Set it up once: HQ Tools, Voices: set up the library (or python dse.py voices setup). It checks every source, repairs what it can and downloads what is lawful to keep." + chr(10)
    h = int(hashlib.sha1(f"{day.isoformat()}|{stratum}".encode()).hexdigest(), 16)
    p = sorted(cands, key=lambda c: c["credit"] + c["text"][:30])[h % len(cands)]
    return f"# Today ({STRATA[stratum]}, {day.isoformat()})\n\n" + note + f"\"{shorten(p['text'], 90)}\"\n{p['credit']}\n\nA passage chosen by the date, from the Voices library. No AI model.\n"


def note(fid: str, text: str, source: str) -> str:
    f = figure(fid)
    text, source = re.sub(r"\s+", " ", text or "").strip(), re.sub(r"\s+", " ", source or "").strip()
    if not 8 <= len(text) <= 1200:
        raise ValueError("Your note is 8 to 1,200 characters.")
    if len(source) < 3:
        raise ValueError("Say where it comes from (book and page, video and time, talk and date): a note without a source is not kept.")
    ns = load_notes(fid)
    ns.append({"text": text, "source": source, "added": dt.date.today().isoformat()})
    notes_path(fid).parent.mkdir(parents=True, exist_ok=True)
    notes_path(fid).write_text(json.dumps(ns), encoding="utf-8")
    idx = [p for p in load_index(fid) if p.get("kind") != "note"]
    idx += [{"text": n["text"], "locator": n["source"], "kind": "note", "credit": f"your own note ({n['source']})"} for n in ns]
    index_path(fid).parent.mkdir(parents=True, exist_ok=True)
    index_path(fid).write_text(json.dumps(idx), encoding="utf-8")
    return f"Saved your note for {f['name']} ({source}). It is marked as yours wherever it appears.\n"


# ------------------------------------------------------------------ update (living figures' own feeds)

def feeds_path(fid: str) -> Path:
    return STORE / "feeds" / f"{fid}.json"


def update(fid: str = "", today_: dt.date | None = None) -> str:
    fs = [figure(fid)] if fid else [f for f in roster() if any(s["type"] in ("feed", "youtube") for s in f.get("sources", []))]
    st = load_state()
    new_total, lines = 0, []
    for f in fs:
        got = []
        for s in f.get("sources", []):
            if s["type"] not in ("feed", "youtube"):
                continue
            if not is_verified(f, s, st):
                continue
            url = st["verified"][src_key(f, s)].get("url") or feed_url_for(s)
            code, body = http_get(url) if url else (0, "")
            items = parse_feed(body) if code == 200 else []
            seen = set(st["seen"].setdefault(f["id"], []))
            fresh = [i for i in items if i["link"] not in seen]
            for i in fresh:
                seen.add(i["link"])
            st["seen"][f["id"]] = sorted(seen)[-400:]
            old = []
            try:
                old = json.loads(feeds_path(f["id"]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            feeds_path(f["id"]).parent.mkdir(parents=True, exist_ok=True)
            feeds_path(f["id"]).write_text(json.dumps((fresh + old)[:60]), encoding="utf-8")
            got += [{**i, "kind": "video" if s["type"] == "youtube" else "post"} for i in fresh]
            time.sleep(PAUSE)
        if got:
            new_total += len(got)
            lines += [f"## {f['name']}: {len(got)} new"] + [f"- {i['title']} ({i['date'][:10] or 'undated'}, {i['kind']}): {i['link']}" + (f"\n    {shorten(i['summary'], 40)}" if i["summary"] else "") for i in got[:5]]
    save_state(st)
    return "\n".join(["# Voices: what is new", "", *(lines or ["Nothing new since last time (or no figure has a verified feed yet: run python dse.py voices verify)."]), "",
                      f"{new_total} new item(s). These are titles, dates, links and short descriptions from their own feeds: follow the link to read or watch. Nothing from social networks is fetched."]) + "\n"


# ------------------------------------------------------------------ list and show

def list_figures(stratum: str = "", path: str = "") -> str:
    if stratum and stratum not in STRATA:
        raise ValueError("Stratum is one of: " + ", ".join(STRATA))
    if path and path not in PATHS:
        raise ValueError("Path is one of: " + ", ".join(PATHS))
    fs = [f for f in roster() if (not stratum or stratum in f.get("strata", [])) and (not path or path in f.get("paths", []))]
    st = load_state()
    L = [f"# Voices: {len(fs)} figure(s)" + (f", {STRATA[stratum]}" if stratum else "") + (f", path {path}" if path else ""), ""]
    for f in fs:
        ver = sum(1 for s in f.get("sources", []) if is_verified(f, s, st))
        L.append(f"- {f['id']}: {f['name']} ({f.get('era', '')}){'  [check: unconfirmed]' if f.get('check') else ''}: {f['known_for']}  [{ver}/{len(f.get('sources', []))} sources verified; {'fetched' if load_index(f['id']) else 'not fetched'}]")
    return "\n".join(L) + "\n"


def show(fid: str) -> str:
    f = figure(fid)
    st = load_state()
    L = [f"# {f['name']} ({f.get('era', '')})", "", f["known_for"] + ("" if not f.get("check") else "  [unconfirmed: check this entry and its sources before relying on it]"), "",
         "Strata: " + (", ".join(STRATA[s] for s in f.get("strata", [])) or "none") + ". Paths: " + (", ".join(f.get("paths", [])) or "none") + ".", "", "## Sources"]
    for s in f.get("sources", []):
        v = st["verified"].get(src_key(f, s))
        what = s.get("title") or s.get("page") or s.get("search") or s.get("handle") or s.get("home") or s.get("url") or ""
        if s["type"] == "books":
            what = "; ".join(f"{b['title']} ({b.get('year', '?')})" for b in s.get("list", []))
        if s["type"] == "links":
            what = ", ".join(f"{k}: {u}" for k, u in s.get("urls", {}).items())
        L.append(f"- {s['type']}: {what}: " + ("not checked yet" if not v else ("verified " + v["checked"] + ", " + v["detail"] if v["ok"] else "FAILED " + v["checked"] + ", " + v["detail"])))
    L += ["", f"Library: {len(load_index(f['id']))} indexed passage(s), {len(load_notes(f['id']))} of your notes."]
    try:
        items = json.loads(feeds_path(f["id"]).read_text(encoding="utf-8"))[:5]
    except (OSError, ValueError):
        items = []
    if items:
        L += ["", "## Latest from their own feeds"] + [f"- {i['title']} ({i['date'][:10] or 'undated'}): {i['link']}" for i in items]
    L += ["", "Social profiles are links only and are never fetched. Books in copyright are listed by title and year only."]
    return "\n".join(L) + "\n"


def roster_problems() -> list[str]:
    """Rules the roster itself must keep: counts, unique ids, known strata and paths, allowed source types."""
    out, fs = [], roster()
    ids = [f["id"] for f in fs]
    if len(ids) != len(set(ids)):
        out.append("duplicate figure ids")
    for s in STRATA:
        n = sum(1 for f in fs if s in f.get("strata", []))
        if n != 10:
            out.append(f"stratum {s} has {n} figures, not 10")
    for p in PATHS:
        n = sum(1 for f in fs if p in f.get("paths", []))
        if n != 7:
            out.append(f"path {p} has {n} figures, not 7")
    for f in fs:
        if any(s not in STRATA for s in f.get("strata", [])) or any(p not in PATHS for p in f.get("paths", [])):
            out.append(f"{f['id']}: unknown stratum or path")
        for s in f.get("sources", []):
            if s["type"] not in SOURCE_TYPES:
                out.append(f"{f['id']}: source type {s['type']} is not allowed")
            if s["type"] == "links" and any(k not in LINK_NETWORKS + ("home", "site") for k in s.get("urls", {})):
                out.append(f"{f['id']}: unknown link network")
        if not f.get("known_for") or len(f["known_for"]) > 160:
            out.append(f"{f['id']}: known_for missing or too long")
    return out


# ------------------------------------------------------------------ setup: verify, repair, fetch and update in one step

FRESH_OK_DAYS, FRESH_FAIL_DAYS, REFETCH_DAYS = 30, 3, 30
CHECK_VERSION = 2          # raise it when the checks get better: results from older checks are done again, not trusted


def _age_days(iso: str) -> int:
    try:
        return (dt.date.today() - dt.date.fromisoformat(iso[:10])).days
    except ValueError:
        return 10 ** 6


def _index_age_days(fid: str) -> int:
    p = index_path(fid)
    return int((time.time() - p.stat().st_mtime) // 86400) if p.exists() else 10 ** 6


def setup(fid: str = "", minutes: int = 25, force: bool = False, say=lambda *_: None) -> str:
    """The one step that makes the library work: for each figure, check every source (repairing what can be repaired: another feed address, the right
    Project Gutenberg book, a simpler book title), download what is lawful to keep, and read what the living have published. Safe to run again and again:
    a source checked recently is skipped, a failed one is retried after 3 days, and it stops cleanly when the time is up and carries on next time.
    Prints each figure as it goes (say). Nothing here sends anything or reads a social network."""
    start, budget = time.time(), max(1, minutes) * 60
    fs = [figure(fid)] if fid else sorted(roster(), key=lambda f: (f.get("era") == "living", 0))
    ready, partial, help_, left = [], [], [], []
    for f in fs:
        if time.time() - start > budget:
            left.append(f["name"])
            continue
        st = load_state()
        notes = []
        for s in f.get("sources", []):
            key = src_key(f, s)
            v = st["verified"].get(key)
            age = _age_days((v or {}).get("checked", ""))
            if not force and v and v.get("v") == CHECK_VERSION and age <= (FRESH_OK_DAYS if v.get("ok") else FRESH_FAIL_DAYS):
                continue
            res = verify_source(f, s)
            st["verified"][key] = {**res, "checked": dt.date.today().isoformat(), "v": CHECK_VERSION}
            save_state(st)
            time.sleep(PAUSE)
        st = load_state()
        fetchable = [s for s in f.get("sources", []) if s["type"] in ("gutenberg", "wikiquote") and is_verified(f, s, st)]
        if fetchable and (force or _index_age_days(f["id"]) > REFETCH_DAYS):
            try:
                fetch(f["id"])
            except Exception as e:                      # one figure's trouble must not stop the rest
                notes.append(f"download failed ({type(e).__name__})")
        n = len(load_index(f["id"]))
        feeds = sum(1 for s in f.get("sources", []) if s["type"] in ("feed", "youtube") and is_verified(f, s, load_state()))
        bad = [(s, load_state()["verified"].get(src_key(f, s), {})) for s in f.get("sources", []) if not is_verified(f, s, load_state()) and s["type"] != "links"]
        line = f"{f['name']}: " + (f"{n} passages" if n else "no passages") + (f", {feeds} live feed(s)" if feeds else "")
        if n or feeds:
            (partial if bad else ready).append(line)
        elif not f.get("sources") or all(s["type"] in ("books", "links") for s in f.get("sources", [])):
            partial.append(f"{f['name']}: titles and links only (books in copyright are not copied; add your own notes with voices note)")
        for s, v in bad:
            help_.append(f"{f['name']} ({s['type']}): {v.get('detail', 'not checked')}")
        say(line + ("" if not bad else f"  [{len(bad)} source(s) still failing]"))
    if feeds_any(fs):
        try:
            update(fid)
        except Exception:
            pass
    out = ["# Voices: set up", "", f"{len(ready)} figure(s) fully ready, {len(partial)} partly ready, {len(help_)} source(s) still need a fix.", ""]
    out += ["## Ready"] + [f"- {x}" for x in ready] if ready else []
    out += ["", "## Partly ready"] + [f"- {x}" for x in partial] if partial else []
    if help_:
        out += ["", "## Still failing, and what to do"] + [f"- {x}" for x in help_[:60]]
    if left:
        out += ["", f"Time ran out before: {', '.join(left[:12])}{'...' if len(left) > 12 else ''}. Run it again to carry on (it skips what is done)."]
    out += ["", "Ask the library: HQ Tools, Voices: ask the library. Nothing here sends anything or reads a social network."]
    return chr(10).join(out) + chr(10)


def feeds_any(fs: list[dict]) -> bool:
    return any(s["type"] in ("feed", "youtube") for f in fs for s in f.get("sources", []))
