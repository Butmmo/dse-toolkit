"""Tests for the website technology detector (18 Nov 2026): fingerprints by category, no false hits on look-alike words, plain gap lines, and the CSV mode.   python tests/test_tech.py"""
import csv
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import tech as T  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TODAY = date(2026, 11, 18)

# ---------------------------------------------------------------- the rules file itself
bad = [(c, n) for c in T.CATEGORIES for n, sigs in T.RULES[c].items() if not sigs]
check("every technology has at least one fingerprint", not bad, str(bad))
for c in T.CATEGORIES:
    for n, sigs in T.RULES[c].items():
        for s in sigs:
            if s.startswith("rx:"):
                re.compile(s[3:])
check("every pattern in the rules compiles", True)
check("the note is not treated as a category", "_note" not in T.CATEGORIES and len(T.CATEGORIES) == 10)
check("every category has an output column", set(T.CATEGORIES) == set(T.COLUMNS))

# ---------------------------------------------------------------- detection
WP = ('<html><head><meta name="viewport" content="width=device-width"><meta name="generator" content="WordPress 6.5">'
      '<script src="/wp-content/themes/divi/x.js"></script><script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ"></script>'
      '<script>fbq("init","123")</script><script type="application/ld+json">{}</script></head><body><div class="wpcf7">form</div>'
      '<a href="https://calendly.com/dr-smith">Book</a><p>&copy; 2019 Smile Dental. Book now.</p></body></html>')
d = T.detect(WP, {"Server": "nginx/1.25", "CF-Ray": "abc"})
check("a WordPress site is recognised with its builder", "WordPress" in d["platform"] and "Divi (WordPress)" in d["platform"], str(d["platform"]))
check("analytics, pixel, form and booking tool are found", "Google Analytics" in d["analytics"] and "Meta Pixel" in d["ads_tracking"] and "Contact Form 7" in d["forms_crm"] and "Calendly" in d["booking"])
check("a real booking tool beats 'there is a book-now link'", d["booking"] == ["Calendly"], str(d["booking"]))
check("hosting comes from the response headers", "Nginx" in d["hosting"] and "Cloudflare" in d["hosting"])
check("a header that is not there detects nothing", T.detect("<html></html>", {})["hosting"] == [])
check("a book-now link alone is reported as that, not as a tool", T.detect("<p>Book now</p>")["booking"] == [T.GENERIC_BOOKING])
check("Wix is recognised from its file host or its header", "Wix" in T.detect('<img src="https://static.wixstatic.com/a.png">')["platform"] and "Wix" in T.detect("", {"X-Wix-Request-Id": "1"})["platform"])

# look-alike words that must NOT be flagged (these were loose substrings once)
traps = '<a href="https://upgrade.us/x">a</a><a href="https://local.com/y">b</a><a href="https://reaffirm.com/z">c</a><a href="https://blacksmith.ai">d</a><a href="https://form.me/q">e</a><p>sample.mc.usa</p>'
d = T.detect(traps)
check("grade.us, cal.com, affirm.com, smith.ai and m.me do not match look-alike addresses", not d["reviews"] and not d["booking"] and not d["payments_financing"] and not d["chat"], str(d))
check("the real addresses are found", "Grade.us" in T.detect('<a href="https://grade.us/acme">')["reviews"] and "Cal.com" in T.detect('<a href="https://cal.com/acme">')["booking"] and "Affirm" in T.detect('<script src="https://cdn1.affirm.com/js/v2/affirm.js">')["payments_financing"])

# ---------------------------------------------------------------- facts and gaps
prof = T.profile(WP, {}, "https://smile.example/")
check("https, mobile setting, structured data and the footer year are read", prof["https"] and prof["mobile_ready"] and prof["structured_data"] and prof["copyright_year"] == 2019)
check("a copyright range uses its last year", T.copyright_year("(c) Copyright 2010 - 2024 Acme") == 2024 and T.copyright_year("no year here") is None)
g = T.gaps(prof, TODAY)
check("an old footer year is called out", any("2019" in x and "out of date" in x for x in g), str(g))
check("what the site does have is not listed as missing", not any("booking" in x or "analytics" in x for x in g), str(g))
check("what is missing is listed (chat, email sign-up, reviews)", any("chat" in x for x in g) and any("email sign-up" in x for x in g) and any("review" in x for x in g))
check("every gap line says it was detected or found, never absolute", all(re.search(r"detected|found|says|not served|built on", x) for x in g), str(g))
bare = T.profile("<html><body>Hello</body></html>", {}, "http://plain.example/")
gb = T.gaps(bare, TODAY)
check("a bare http page is missing the most", len(gb) >= 9 and any("https" in x for x in gb) and any("mobile" in x for x in gb))
wix = T.profile('<img src="https://static.wixstatic.com/a.png"><meta name="viewport" content="x">', {}, "https://w.example/")
check("a DIY site builder is named", any("built on Wix" in x for x in T.gaps(wix, TODAY)))

# ---------------------------------------------------------------- columns
cols = T.columns(prof, "ok", TODAY)
check("the columns carry the technologies and the gap count", cols["tech_platform"].startswith("WordPress") and cols["tech_booking"] == "Calendly" and cols["tech_gap_count"] == len(g) and cols["tech_scanned_on"] == "2026-11-18")
check("a site we could not read has empty tech columns and says why", T.empty_columns("unreachable", TODAY)["tech_status"] == "unreachable" and T.empty_columns("unreachable", TODAY)["tech_platform"] == "")

# ---------------------------------------------------------------- scan() and the CSV mode, with a fake network
class Resp:
    def __init__(self, status, text, url, headers=None):
        self.status_code, self.text, self.url, self.headers = status, text, url, headers or {"content-type": "text/html", "Server": "nginx"}


SITES = {"https://smile.example": Resp(200, WP, "https://smile.example/"), "https://down.example": Resp(500, "", "https://down.example/"), "https://nope.example": Resp(404, "", "https://nope.example/")}
calls = []


def fake_get(url, **k):
    calls.append(url)
    if url.rstrip("/") not in SITES:
        raise OSError("no route")
    return SITES[url.rstrip("/")]


T.requests.get = fake_get
T.render_dom = lambda url, timeout=40: ""
import dse.enrich as E  # noqa: E402
E.robots_ok = lambda url: "blocked.example" not in url

c, p = T.scan("smile.example", render=False, today=TODAY)
check("scan reads one page and returns the columns", c["tech_status"] == "ok" and c["tech_platform"].startswith("WordPress") and calls == ["https://smile.example"], str(calls))
check("a site that is down, missing or has no address says so", T.scan("down.example", False, TODAY)[0]["tech_status"].startswith("error") and T.scan("nope.example", False, TODAY)[0]["tech_status"] == "error 404"
      and T.scan("gone.example", False, TODAY)[0]["tech_status"] == "unreachable" and T.scan("", False, TODAY)[0]["tech_status"] == "no website")
n = len(calls)
check("a site whose robots.txt says no is not opened", T.scan("blocked.example", False, TODAY)[0]["tech_status"] == "robots.txt says no" and len(calls) == n)

tmp = Path(tempfile.mkdtemp(prefix="zz-tech-"))
src = tmp / "leads.csv"
with open(src, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["business", "Website", "city"])
    w.writerows([["Smile", "smile.example", "Leeds"], ["No Site", "", "Hull"], ["Down", "down.example", "York"], ["Extra", "smile.example", "Bath"]])
out = tmp / "out.csv"
T.tech_file(str(src), max_rows=2, render=False, out=str(out), today=TODAY)
rows = list(csv.DictReader(open(out, newline="", encoding="utf-8-sig")))
check("every row and its order are kept", [r["business"] for r in rows] == ["Smile", "No Site", "Down", "Extra"])
check("a row with a site gets the tech columns, one without says no website", rows[0]["tech_platform"].startswith("WordPress") and rows[1]["tech_status"] == "no website" and rows[2]["tech_status"].startswith("error"))
check("rows over the limit are marked, not silently skipped", rows[3]["tech_status"] == "not scanned (over the limit)")
check("the original columns are untouched", rows[0]["city"] == "Leeds" and rows[0]["Website"] == "smile.example")
bad_csv = tmp / "nosite.csv"
bad_csv.write_text("a,b\n1,2\n", encoding="utf-8")
try:
    T.tech_file(str(bad_csv), out=str(tmp / "x.csv"))
    msg = ""
except SystemExit as e:
    msg = str(e)
check("a CSV without a website column is explained", "No website column" in msg)
check("the card lists what is detected and what is missing", "WordPress" in T.card("smile.example", False) and "missing (" in T.card("smile.example", False))

sys.exit(1 if fails else 0)
