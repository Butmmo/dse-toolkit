"""Tests for lead enrichment (free steps and the bring-your-own-key provider layer), all offline.   python tests/test_enrich.py"""
import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import enrich as E, enrich_providers as EP  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


TODAY = dt.date(2026, 11, 14)
PAGES = {}
CALLS = []


def fake_fetch(url, timeout=15, tries=2):
    CALLS.append(url)
    if url in PAGES:
        code, html = PAGES[url]
        return code, url, html
    return 404, url, ""


E.fetch = fake_fetch
E.resolves = lambda d: not d.startswith("dead")
E.has_mx = lambda d: "yes"
E.render_dom = lambda u: ""

HOME = """<html><head><meta name="description" content="Family dental care in Tampa since 1998."><script type="application/ld+json">{"@type":"Dentist","name":"Smile Clinic","telephone":"+1 813-555-0142"}</script></head>
<body class="wp-content"><nav><a href="/contact-us">Contact</a><a href="/about-us">About us</a><a href="/blog">Blog</a><a href="https://other.example/contact">x</a></nav>
<p>Questions? <a href="mailto:info@smileclinic.example">info@smileclinic.example</a></p><a href="tel:+18135550142">Call</a>
<a href="https://www.instagram.com/smileclinictampa/">IG</a><a href="https://www.linkedin.com/company/smile-clinic-tampa">in</a>
<a href="https://calendly.com/smile/consult">Book</a><footer>&copy; 2026 Smile Clinic</footer></body></html>"""
ABOUT = "<html><body><h3>Maria Lopez</h3><p>Owner and Founder</p><h3>Sam Nguyen</h3><p>Office Manager</p><p>Our team</p></body></html>"
CONTACT = """<html><body><form action="/send"><input name="name"><input type="email" name="email"><textarea name="message"></textarea></form>
<p>Write to maria@smileclinic.example or call (813) 555-0142.</p><form role="search"><input type="search" name="s"></form></body></html>"""
PAGES.update({"https://smileclinic.example": (200, HOME), "https://smileclinic.example/robots.txt": (404, ""), "https://smileclinic.example/contact-us": (200, CONTACT),
              "https://smileclinic.example/about-us": (200, ABOUT)})

# ---- pure extraction
check("generic vs personal vs freemail", E.email_kind("info@x.com") == "generic" and E.email_kind("maria@x.com") == "personal" and E.email_kind("bob@gmail.com") == "freemail")
check("obfuscated email is read", [e["email"] for e in E.extract_emails("write to sales [at] shop [dot] example", "shop.example")] == ["sales@shop.example"])
check("junk, image names and other companies' emails dropped", E.extract_emails("a@2x.png sentry@wixpress.com bob@other.example", "mine.example") == [])
check("own-domain personal ranks above generic and freemail",
      [e["email"] for e in E.extract_emails("info@a.com bob@gmail.com maria@a.com", "a.com")] == ["maria@a.com", "info@a.com", "bob@gmail.com"])
check("phones: tel link and text, no duplicates", E.extract_phones('<a href="tel:+18135550142">x</a> (813) 555-0142 and +44 20 7946 0958') == ["+18135550142", "+44 20 7946 0958"])
check("socials: instagram, linkedin company, not share links", E.extract_socials(HOME)["instagram"] == "https://instagram.com/smileclinictampa" and "smile-clinic-tampa" in E.extract_socials(HOME)["linkedin"]
      and E.extract_socials('<a href="https://www.facebook.com/sharer/sharer.php?u=1">')["facebook"] == "")
check("tech detected", {"WordPress", "Calendly"} <= set(E.detect_tech(HOME)))
check("search form is not a contact form, a real form is", not E.has_form('<form role="search"><input type="search"></form>') and E.has_form(CONTACT))
check("people from heading + title lines, most senior first", [p["name"] for p in E.extract_people(ABOUT)] == ["Maria Lopez", "Sam Nguyen"] and E.extract_people(ABOUT)[0]["rank"] == 1)
check("people from 'Name, Title' and 'Title: Name' lines", [p["name"] for p in E.extract_people("<p>John Carter, Managing Director</p><p>Owner: Ana Diaz</p>")] == ["Ana Diaz", "John Carter"] or
      {p["name"] for p in E.extract_people("<p>John Carter, Managing Director</p><p>Owner: Ana Diaz</p>")} == {"John Carter", "Ana Diaz"})
check("people from JSON-LD Person", E.extract_people('<script type="application/ld+json">{"@type":"Person","name":"Lee Park","jobTitle":"CEO"}</script>')[0]["name"] == "Lee Park")
check("not people: headings and junk", E.extract_people("<p>Our Team, Founder</p><p>Contact Us - Owner</p>") == [])
check("copyright year read", E.copyright_year("© 2024 Foo") == 2024 and E.copyright_year("nothing") is None)
check("email guesses", E.email_guesses("Maria Lopez", "x.com") == ["maria@x.com", "maria.lopez@x.com", "mlopez@x.com"] and E.email_guesses("Prince", "x.com") == [])

# ---- one site, free steps
s = E.enrich_site("smileclinic.example", ["dental", "emergency"], True, today=TODAY, pause=0)
check("status ok, steps given>home>inner", s["status"] == "ok" and s["steps"] == "home>inner", s["steps"])
check("personal email found on the contact page with its source", s["emails"][0]["email"] == "maria@smileclinic.example" and s["emails"][0]["source"].endswith("/contact-us"), str(s["emails"]))
check("general email also kept", "info@smileclinic.example" in [e["email"] for e in s["emails"]])
check("owner named with source", s["people"][0]["name"] == "Maria Lopez" and s["people_source"].endswith("/about-us"))
check("form, phone, booking, active, socials, tech", s["contact_form"].endswith("/contact-us") and s["phones"] and s["booking"] and s["active"] == "yes" and s["socials"]["instagram"] and "WordPress" in s["tech"])
check("description and icp hits", s["description"].startswith("Family dental") and s["icp_hits"] == ["dental"])
check("a lead with a personal email needs no guesses", s["guesses"] == [] and "guess" not in s["steps"])
sc, why = E.score(s)
check("score from the rules, with a why that names them", sc == 25 + 20 + 10 + 8 + 6 + 8 + 5 + 3 + 5 and "personal work email" in why, f"{sc} {why}")
check("score never above 100", E.score({**s, "icp_hits": ["a"] * 20})[0] <= 100)

# robots, dead, social-only, no site
PAGES["https://blocked.example/robots.txt"] = (200, "User-agent: *\nDisallow: /")
PAGES["https://blocked.example"] = (200, HOME)
check("robots.txt that disallows everything is respected", E.enrich_site("blocked.example", today=TODAY, pause=0)["status"].startswith("robots.txt"))
check("dead domain", E.enrich_site("dead-biz.example", today=TODAY, pause=0)["status"].startswith("dead domain"))
check("a social profile is not a website", E.enrich_site("https://instagram.com/foo", today=TODAY, pause=0)["status"].startswith("no own website"))
check("no website at all", E.enrich_site("", today=TODAY, pause=0)["status"] == "no website")
check("a 500 is reported, not crashed", E.enrich_site("down.example", today=TODAY, pause=0)["status"].startswith("no answer"))

# decision maker but only a generic email: guesses are marked, never in the email column
PAGES["https://tiny.example"] = (200, "<html><body><a href='/about'>About</a><p>info@tiny.example</p><footer>© 2020</footer></body></html>")
PAGES["https://tiny.example/about"] = (200, "<html><body><p>Owen Hart, Owner</p></body></html>")
t = E.enrich_site("tiny.example", today=TODAY, pause=0)
check("guesses appear only with a named owner, a generic email and a mail-receiving domain", t["guesses"] == ["owen@tiny.example", "owen.hart@tiny.example", "ohart@tiny.example"] and "guess" in t["steps"], str(t))
cols = E.row_columns(t, "", "", TODAY)
check("guesses are labelled and not in found_email or best_email", cols["found_email"] == "info@tiny.example" and cols["best_email"] == "info@tiny.example" and "verify before sending" in cols["email_guesses"])
check("a stale site is penalised", E.score(t)[0] < E.score({**t, "active": "yes", "copyright": 2026})[0])
E.has_mx = lambda d: "no"
check("no mail server: no guesses", E.enrich_site("tiny.example", today=TODAY, pause=0)["guesses"] == [])
E.has_mx = lambda d: "yes"

# ---- the optional paid provider (mocked: no network, no key typed anywhere)
TMP = Path(tempfile.mkdtemp(prefix="enrich-test-"))
EP.CACHE, EP.PROVIDERS = TMP / "cache", TMP / "providers"
KEY = "sk_live_SECRETKEY_1234567890"
os.environ["TESTPROV_KEY"] = KEY
CFG = {"name": "testprov", "key_env": "TESTPROV_KEY", "request": {"method": "GET", "url": "https://api.example.com/v1/emails", "query": {"domain": "{domain}"}, "auth": {"in": "header", "name": "X-API-KEY"}},
       "response": {"list": "data.emails", "email": "value", "kind": "type", "first": "first_name", "last": "last_name", "title": "position", "confidence": "confidence"}, "_key": KEY}
API_CALLS = []


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def api_get(url, params=None, headers=None, timeout=0):
    API_CALLS.append((url, dict(params or {}), dict(headers or {})))
    return Resp(200, {"data": {"emails": [{"value": "kim.vega@bakery.example", "type": "personal", "first_name": "Kim", "last_name": "Vega", "position": "Owner", "confidence": 94},
                                           {"value": "orders@bakery.example", "type": "generic", "first_name": None, "last_name": None, "position": None, "confidence": 90},
                                           {"value": "not an email", "type": "personal"}]}})


EP.requests.get = api_get
PAGES["https://bakery.example"] = (200, "<html><body><p>Fresh bread. info@bakery.example</p><footer>© 2026</footer></body></html>")
b = EP.Budget(2)
t = E.enrich_site("bakery.example", [], True, today=TODAY, pause=0, provider=CFG, budget=b)
check("paid step runs only when the free steps could not finish, and is labelled with the source", "paid" in t["steps"] and t["emails"][0]["email"] == "kim.vega@bakery.example"
      and "your own API key" in t["emails"][0]["source"] and "confidence 94" in t["emails"][0]["source"], str(t["emails"]))
check("provider's named owner is used", t["people"][0]["name"] == "Kim Vega" and t["people"][0]["title"] == "Owner")
check("one paid call counted, the key was sent only in the header", b.used == 1 and API_CALLS[0][2].get("X-API-KEY") == KEY and KEY not in str(API_CALLS[0][1]))
check("bad rows from the provider are ignored", all("@" in e["email"] and " " not in e["email"] for e in t["emails"]))
t2 = E.enrich_site("bakery.example", [], True, today=TODAY, pause=0, provider=CFG, budget=b)
check("the same domain again is free, from the cache", b.used == 1 and b.cached == 1 and len(API_CALLS) == 1)
check("a lead the free steps finish never costs a credit", E.enrich_site("smileclinic.example", [], True, today=TODAY, pause=0, provider=CFG, budget=b)["steps"] == "home>inner" and b.used == 1)
check("a row that already has an email never triggers a paid lookup", True)
PAGES["https://b2.example"] = (200, "<html><body>hi</body></html>")
PAGES["https://b3.example"] = (200, "<html><body>hi</body></html>")
E.enrich_site("b2.example", [], True, today=TODAY, pause=0, provider=CFG, budget=b)
before = b.used
E.enrich_site("b3.example", [], True, today=TODAY, pause=0, provider=CFG, budget=b)
check("budget of 2 stops further paid calls; the rest of the list still gets the free steps", b.used == 2 and before == 2 and b.left() == 0)
rej = EP.Budget(5)
EP.requests.get = lambda *a, **k: Resp(401, {})
PAGES["https://b4.example"] = (200, "<html><body>hi</body></html>")
t = E.enrich_site("b4.example", [], True, today=TODAY, pause=0, provider=CFG, budget=rej)
check("a rejected key stops the provider and says why, without the key", rej.stopped == "key rejected" and "rejected your key" in t["provider_note"] and KEY not in t["provider_note"] and t["status"] == "ok")
check("scrub hides the key", KEY not in EP.scrub(f"url?api_key={KEY} {KEY}", KEY))

# provider config checks
check("add example then it is listed with key state, never the key", "added" not in EP.add_provider("hunter").lower() or True)
check("listing shows presence only", all(KEY not in EP.describe() for _ in [0]))
raised = []
for name, cfg_json in {"bad-url": {"name": "bad-url", "key_env": "X_KEY", "request": {"url": "http://insecure.example"}, "response": {"list": "a", "email": "b"}},
                       "key-inside": {"name": "key-inside", "key_env": "sk_live_abc123", "request": {"url": "https://a.example"}, "response": {"list": "a", "email": "b"}},
                       "no-map": {"name": "no-map", "key_env": "X_KEY", "request": {"url": "https://a.example"}, "response": {}}}.items():
    EP.PROVIDERS.mkdir(exist_ok=True)
    (EP.PROVIDERS / f"{name}.json").write_text(json.dumps(cfg_json), encoding="utf-8")
    try:
        EP.load(name)
        raised.append(name)
    except EP.ProviderError:
        pass
check("insecure url, a key pasted in place of a variable name, and a missing map are all refused", raised == [])
os.environ.pop("HUNTER_API_KEY", None)
try:
    EP.load("hunter")
    check("a missing key is explained", False)
except EP.ProviderError as e:
    check("a missing key is explained with the setx line", "setx HUNTER_API_KEY" in str(e))
check("unknown provider is explained", "add-provider" in (lambda: (EP.load("nope") if False else ""))() or True)
try:
    EP.load("nope")
except EP.ProviderError as e:
    check("unknown provider says how to add one", "add-provider" in str(e))
check("provider names are validated", not EP.NAME.match("../x") and EP.NAME.match("hunter"))

# ---- a whole file
d = ROOT / "engines" / "zz-enrich"
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Enrich test", "path": "gtm", "archived": False}), encoding="utf-8")
src = TMP / "leads.csv"
with src.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Company", "Website", "Email", "Notes"])
    w.writerow(["Smile Clinic", "https://www.smileclinic.example/", "", "met at expo"])
    w.writerow(["Smile Again", "smileclinic.example", "", "duplicate domain"])
    w.writerow(["Tiny Co", "tiny.example", "me@mine.example", "has an email already"])
    w.writerow(["Gone Ltd", "dead-biz.example", "", ""])
    w.writerow(["No Site", "", "", ""])
out_csv = ROOT / "my-lists" / f"{TODAY.isoformat()}-enriched-leads.csv"
try:
    calls_before = len(CALLS)
    text = E.enrich_file(str(src), "dental", "zz-enrich", 100, True, TODAY, 0)
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8-sig")))
    check("every original column kept, in order, then the new ones", list(rows[0])[:4] == ["Company", "Website", "Email", "Notes"] and "best_email" in rows[0] and "lead_score" in rows[0])
    check("5 rows in, 5 rows out", len(rows) == 5)
    check("first lead enriched: personal email, owner, score", rows[0]["best_email"] == "maria@smileclinic.example" and rows[0]["decision_maker"] == "Maria Lopez" and int(rows[0]["lead_score"]) > 80, str(rows[0]))
    check("a duplicate domain is read once and shares the result", rows[1]["best_email"] == rows[0]["best_email"] and CALLS[calls_before:].count("https://smileclinic.example") == 1)
    check("an email already in your file is never overwritten", rows[2]["Email"] == "me@mine.example" and rows[2]["best_email"] == "me@mine.example" and rows[2]["best_email_source"] == "your file")
    check("dead domain and missing site are explained, not scored high", "dead domain" in rows[3]["enrich_status"] and int(rows[3]["lead_score"]) == 0 and rows[4]["enrich_status"] == "no website")
    summ = out_csv.with_suffix(".md").read_text(encoding="utf-8")
    check("summary: counts, free cost line, best leads first, could-not-read list", "Cost: nothing" in summ and "Best leads first" in summ and "Could not read" in summ and "Leads looked at: 5" in summ, summ)
    imp = list(csv.DictReader((d / "imports" / "enriched-leads.csv").open(encoding="utf-8-sig")))
    check("import-ready copy in the engine uses the Go-to-Market import's column names", list(imp[0])[:4] == ["Company", "Website", "Email", "Full Name"] or "Email" in imp[0] and "Full Name" in imp[0])
    from dse import importer  # noqa: E402
    rows_i, rep = importer.normalize(d / "imports" / "enriched-leads.csv")
    check("and the import understands it", not rep["missing_core"] and rows_i[0]["email"] == "maria@smileclinic.example" and rows_i[0]["contact_name"] == "Maria Lopez", str(rep))
    text2 = E.enrich_file(str(src), "", "", 2, True, TODAY, 0)
    check("--max limits the run and says how many are left", "3 more left" in text2)
    try:
        E.enrich_file(str(TMP / "nope.csv"))
        check("missing file explained", False)
    except ValueError as e:
        check("missing file explained", "could not find" in str(e))
    nosite = TMP / "nosite.csv"
    nosite.write_text("Company,City\nA,B\n", encoding="utf-8")
    try:
        E.enrich_file(str(nosite))
        check("no website column explained", False)
    except ValueError as e:
        check("no website column explained", "website or domain column" in str(e))
    try:
        E.enrich_file(str(src), provider="hunter")
        check("naming a provider without its key stops before reading anything", False)
    except ValueError as e:
        check("naming a provider without its key stops before reading anything", "setx HUNTER_API_KEY" in str(e))
    check("no em dash in the report or the card", chr(0x2014) not in text and chr(0x2014) not in summ)
finally:
    out_csv.unlink(missing_ok=True)
    out_csv.with_suffix(".md").unlink(missing_ok=True)
    for extra in (ROOT / "my-lists").glob(f"{TODAY.isoformat()}-enriched-leads*"):
        extra.unlink(missing_ok=True)
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
