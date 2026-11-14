"""Authority audit: find experts who know a lot and post little, from profiles and posts YOU read and paste. Nothing is scraped.

    engines/<slug>/pasted/*.csv         one row per expert you looked at (see the columns below)
    python dse.py import <engine>       check the file and show the audit (same command as the Go-to-Market path)
    python dse.py daily <engine>        build the next send list from the audit

Why pasted: LinkedIn does not allow automated reading of profiles and posts, so this reads only what you copy in by hand.
You open a profile, note the details and the last few post dates, paste two or three posts, and the audit does the thinking.

Columns (names are matched loosely; only the first two are needed):
  name, profile_url, headline, company, connections (or followers), post_dates (the last 5 to 10 post dates, separated by ;),
  post_1, post_2, post_3 (the text of their recent posts; or one column 'posts' with --- between posts),
  website, email, engaged (yes if they answered your comment), notes

It scores what the Authority path's own rubric asks (expertise 2, posts rarely 3, sells a high-value service 2, 500+ audience 1,
engaged with you 1) and finds the gap to lead with: the silence, how posts open, walls of text, no ask, talking about 'we' not 'you'.
A post count from dates you noted is only as good as those dates: it says so when there are none.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from .common import ROOT
from .importer import parse_date, squash

ENGINES = ROOT / "engines"
ALIAS = {
    "name": ["name", "fullname", "contact", "person", "expert", "prospect"],
    "profile_url": ["profileurl", "linkedin", "linkedinurl", "profile", "url", "linkedinprofile"],
    "headline": ["headline", "title", "jobtitle", "role", "position"],
    "company": ["company", "organization", "firm", "business"],
    "audience": ["connections", "followers", "audience", "connectionsfollowers", "followerscount", "connectioncount"],
    "post_dates": ["postdates", "dates", "lastposts", "lastpostdates", "postsdates", "recentpostdates"],
    "posts": ["posts", "recentposts", "postsample", "postsamples"],
    "website": ["website", "site", "companywebsite", "domain"],
    "email": ["email", "emailaddress", "workemail"],
    "engaged": ["engaged", "engagedwithme", "replied", "respondedtocomment"],
    "notes": ["notes", "note", "comments"],
}
EXPERT = re.compile(r"\b(\d+\+?\s*(years|yrs)|certified|author|founder|co-?founder|partner|principal|former|ex-[a-z]+|phd|mba|award|bestselling|\$\d|\d+%|\d+x)\b", re.I)
SELLS = re.compile(r"\b(coach|advisor|adviser|consultant|founder|co-?founder|ceo|attorney|lawyer|cmo|fractional|agent|broker|speaker|author|strategist|partner|therapist|trainer)\b", re.I)
GENERIC = re.compile(r"^\s*(i'?m|we'?re|i am|we are)\s+(so\s+)?(excited|thrilled|happy|proud|delighted|humbled)|^\s*(excited|thrilled|happy|proud|delighted|humbled) to\b|^\s*(big news|announcing|great news)\b", re.I)
ASK = re.compile(r"(\?|comment|\bdm\b|message me|book|link in|reply|follow|share|let me know|thoughts|agree)", re.I)


def read_pasted(slug: str) -> list[dict]:
    rows = []
    d = ENGINES / slug / "pasted"
    for f in sorted(d.glob("*.csv")) if d.exists() else []:
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rd = csv.DictReader(text.splitlines(), dialect=dialect)
        sq = {squash(h): h for h in (rd.fieldnames or [])}
        m = {std: next((sq[a] for a in names if a in sq), None) for std, names in ALIAS.items()}
        post_cols = [sq[k] for k in sorted(sq) if re.fullmatch(r"post\d+", k)]
        for r in rd:
            g = lambda k: (r.get(m[k], "") or "").strip() if m.get(k) else ""  # noqa: E731
            posts = [(r.get(c, "") or "").strip() for c in post_cols if (r.get(c, "") or "").strip()]
            if g("posts"):
                posts += [p.strip() for p in re.split(r"\n?\s*---+\s*\n?", g("posts")) if p.strip()]
            if g("name"):
                rows.append({"name": g("name"), "profile_url": g("profile_url"), "headline": g("headline"), "company": g("company"), "audience": g("audience"),
                             "post_dates": g("post_dates"), "posts": posts, "website": g("website"), "email": g("email").lower(), "engaged": g("engaged"),
                             "notes": g("notes"), "_file": f.name})
    return rows


def dates_of(s: str) -> list[dt.date]:
    out = []
    for part in re.split(r"[;\n|]+", s or ""):
        d = parse_date(part.strip())
        if d:
            out.append(d)
    return sorted(out, reverse=True)


def audience_of(v: str) -> int:
    t = (v or "").lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)", t)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * (1000 if m.group(2) == "k" else 1_000_000 if m.group(2) == "m" else 1))


def post_issues(posts: list[str]) -> dict[str, bool]:
    """True where at least half of the pasted posts show the problem (needs 2 or more posts to say anything)."""
    if len(posts) < 2:
        return {}
    half = len(posts) / 2
    walls = sum(1 for p in posts if len(p) > 500 and p.count("\n") < 2)
    generic = sum(1 for p in posts if GENERIC.search(p.strip().split("\n")[0]))
    no_ask = sum(1 for p in posts if not ASK.search(p[-220:]))
    selfish = 0
    for p in posts:
        me = len(re.findall(r"\b(we|our|us|i|my|me)\b", p, re.I))
        you = len(re.findall(r"\b(you|your|you'?re)\b", p, re.I))
        if me >= 6 and me > 2 * max(you, 1):
            selfish += 1
    return {"generic_hook": generic >= half, "wall": walls >= half, "no_ask": no_ask >= half, "selfish": selfish >= half}


def audit_row(r: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    ds = dates_of(r["post_dates"])
    last_days = (today - ds[0]).days if ds else None
    n90 = sum(1 for d in ds if 0 <= (today - d).days <= 90)
    pts, why = 0, []
    if EXPERT.search(r["headline"]):
        pts += 2; why.append("clear expertise in the headline")
    if ds and n90 < 13:                                       # less than one post a week in the last 90 days
        pts += 3; why.append(f"{n90} post{'s' if n90 != 1 else ''} in 90 days")
    elif not ds:
        why.append("no post dates given: add them to score the posting gap")
    if SELLS.search(r["headline"]):
        pts += 2; why.append("sells expertise (coach, advisor, founder...)")
    if audience_of(r["audience"]) >= 500:
        pts += 1; why.append("500+ audience")
    if re.match(r"(y|yes|true|1)", r["engaged"].strip(), re.I):
        pts += 1; why.append("engaged with you")
    issues = post_issues(r["posts"])
    gaps: list[tuple[str, str]] = []                          # (short label, gap_line), strongest first
    if ds and (last_days or 0) > 30:
        gaps.append((f"Last post {last_days} days ago", f"your last post was {last_days} days ago and you posted {n90} time{'s' if n90 != 1 else ''} in the last 90 days"))
    elif ds and n90 < 13:
        gaps.append((f"{n90} posts in 90 days", f"you posted {n90} time{'s' if n90 != 1 else ''} in the last 90 days, so your expertise only reaches your audience now and then"))
    elif not ds and not r["posts"]:
        gaps.append(("No posts found", "I couldn't find recent posts from you, so your expertise is mostly invisible online"))
    if issues.get("generic_hook"):
        gaps.append(("Posts open with an announcement", "your posts open with an announcement instead of a first line that makes people stop"))
    if issues.get("wall"):
        gaps.append(("Walls of text", "your posts are long blocks of text with no breaks, which people scroll past"))
    if issues.get("no_ask"):
        gaps.append(("No question or ask", "your posts end without a question or an invitation, so readers have nothing to answer"))
    if issues.get("selfish"):
        gaps.append(("Talks about 'we' not 'you'", "your posts talk about you and your firm far more than the reader"))
    first = r["name"].split(" ")[0]
    return {"business": r["name"], "contact_name": r["name"], "contact_first": first, "contact_title": r["headline"], "website": re.sub(r"^https?://(www\.)?", "", r["website"]).split("/")[0],
            "email": r["email"], "linkedin": r["profile_url"], "city": "", "gap_line": gaps[0][1] if gaps else "", "gaps_found": "; ".join(g[0] for g in gaps),
            "gap_count": len(gaps), "rubric_score": pts, "check_notes": f"score {pts}/9: " + ", ".join(why), "last_post_days": last_days if last_days is not None else "", "posts_90d": n90 if ds else ""}


def audit(slug: str, min_score: int = 4, today: dt.date | None = None) -> list[dict]:
    out = [audit_row(r, today) for r in read_pasted(slug)]
    out = [o for o in out if o["gap_count"] and o["rubric_score"] >= min_score]
    return sorted(out, key=lambda o: (-o["rubric_score"], -o["gap_count"]))


def preview(slug: str) -> None:
    rows = read_pasted(slug)
    if not rows:
        print(f"No file yet. Make a CSV with the columns name, profile_url, headline, connections, post_dates, post_1, post_2, post_3 and save it in:\n  {ENGINES / slug / 'pasted'}\n"
              "Copy the details by hand from each profile you looked at. Then run this again (or tap Build next list).")
        return
    res = [audit_row(r) for r in rows]
    print(f"{len(rows)} expert(s) read. Best prospects first (score out of 9):")
    for o in sorted(res, key=lambda o: -o["rubric_score"]):
        print(f"  {o['rubric_score']}  {o['business'][:28]:<28} {o['gaps_found'][:70] or 'nothing to lead with yet'}")
