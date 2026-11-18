"""Tests for owner names and work emails (18 Nov 2026): a page heading or review widget is not an owner, an address on another company's domain is not the business's email,
a server's default page is not a website, and the HQ button for first name, last name and work email on a grid.   python tests/test_owner_email.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import enrich as E, gridpeople as G, places as P  # noqa: E402
from bridge import runner as R  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- a name is a person, not a heading
check("'Google Reviews' and other widgets and headings are not names", not any(E.good_name(n) for n in ("Google Reviews", "Tree Services", "Meet Team", "Contact Us", "Facebook Page", "Our Gallery", "Opening Hours", "Privacy Policy")))
check("real names are still names", all(E.good_name(n) for n in ("Lewis Sadler", "Ian Clark", "Mary O'Neil", "Jean-Luc Picard", "Owen Hart")))
LINES = "<html><body><p>Google Reviews</p><p>Meet the Owner</p><p>Our trees are safe with us.</p></body></html>"
check("a review widget beside a 'Meet the Owner' heading is not an owner", E.extract_people(LINES) == [], str(E.extract_people(LINES)))
CARD = "<html><body><h3>Lewis Sadler</h3><p>Owner and Director</p><p>Ian Clark, Managing Director</p><p>Contact Us: Maria Lopez</p></body></html>"
names = {p["name"] for p in E.extract_people(CARD)}
check("real people with real titles are found, a 'Contact Us' label is not a title", {"Lewis Sadler", "Ian Clark"} <= names and "Maria Lopez" not in names, str(names))
HEAD = "<html><body><p>Jane Doe, Meet the Owner</p><p>Tom Reed - Our Director</p></body></html>"
check("a heading in the title place is not a job title, even beside a real name", E.extract_people(HEAD) == [], str(E.extract_people(HEAD)))
check("a heading is not a job title", all(E.HEADING_TITLE.match(t) for t in ("Meet the Owner", "Our Team", "About the Director", "The Owner")) and not E.HEADING_TITLE.match("Owner and Director"))

# ---------------------------------------------------------------- an email on another company's domain
check("an address on the business's own domain or a free mailbox belongs to it, another company's does not",
      E.email_belongs("info@krakentreecare.com", "krakentreecare.com") and E.email_belongs("bob@gmail.com", "krakentreecare.com") and E.email_belongs("a@mail.krakentreecare.com", "krakentreecare.com")
      and not E.email_belongs("seo@dmf-group.co.uk", "krakentreecare.com"))
site = E.blank("kraken.example")
site.update(status="ok", emails=[{"email": "info@kraken.example", "kind": "generic", "source": "https://kraken.example/"}])
cols = E.row_columns(site, "SEO@agency.example", "", E.dt.date(2026, 11, 18))
check("the agency's address in your file is not the best email when the site shows its own, and the file says why and keeps your column",
      cols["best_email"] == "info@kraken.example" and "agency" in cols["email_check"] and "SEO@agency.example" in cols["email_check"], str(cols["best_email"]))
cols2 = E.row_columns(dict(site, emails=[]), "SEO@agency.example", "", E.dt.date(2026, 11, 18))
check("with nothing better on the site the address in your file is kept, still flagged", cols2["best_email"] == "SEO@agency.example" and "another domain" in cols2["email_check"])
cols3 = E.row_columns(site, "owner@kraken.example", "", E.dt.date(2026, 11, 18))
check("an address in your file on the business's own domain is kept and not flagged", cols3["best_email"] == "owner@kraken.example" and cols3["email_check"] == "")
agency = E.row_columns(dict(site, domain="kraken.example"), "SEO@agency.example", "", E.dt.date(2026, 11, 18))
own = E.row_columns(dict(site, domain="kraken.example"), "owner@kraken.example", "", E.dt.date(2026, 11, 18))
check("an agency's address does not earn the 'email given' score points, the business's own does", int(agency["lead_score"]) < int(own["lead_score"]), f"{agency['lead_score']} vs {own['lead_score']}")

# ---------------------------------------------------------------- a server's default page
check("a web server's default page is rejected as a website", all(P.BAD_TITLE.search(t) for t in ("Web Server's Default Page", "Apache2 Ubuntu Default Page: It works", "Test Page for the Apache HTTP Server")) and not P.BAD_TITLE.search("Default Dental Care"))

# ---------------------------------------------------------------- the HQ button
cat = R.load_catalog(base_only=True)
tool = cat["tools"].get("dse.grid_people")
check("the button is in the catalog, in Grow, and needs a grid", tool and tool["group"] == "Grow" and next(f for f in tool["fields"] if f["name"] == "grid")["required"])
check("every argument refers to a field and every field is used", all(a["field"] in {f["name"] for f in tool["fields"]} for a in tool["args"] if "field" in a) and all(f["name"] in {a.get("field") for a in tool["args"]} for f in tool["fields"]))
argv, _ = R.build_command(cat, "dse.grid_people", {"grid": "Tree surgeons/Leads", "website_column": "Their page", "mode": "all", "limit": 20, "guess": True, "dry": True})
from dse import gridpush as GP  # noqa: E402
seen = {}
real_run = G.run
G.run = lambda *a, **k: seen.update(args=a) or "FINISHED\n"
try:
    code0 = GP.cli(["people", "Leads", "--guess"])
finally:
    G.run = real_run
check("python dse.py grid people is wired into the grid command", code0 == 0 and seen["args"][0] == "Leads" and seen["args"][4] is True, str(seen))
seen = {}
real_run = G.run
G.run = lambda *a, **k: seen.update(args=a) or "FINISHED\n"
try:
    code = G.cli(argv[argv.index("people") + 1:])
finally:
    G.run = real_run
check("the button's command is understood by the tool: grid, website column, mode, limit, guess and dry run arrive",
      code == 0 and seen["args"][:6] == ("Tree surgeons/Leads", "Their page", "all", 20, True, True), str(seen))
argv2, _ = R.build_command(cat, "dse.grid_people", {"grid": "Leads"})
seen.clear()
G.run = lambda *a, **k: seen.update(args=a) or "FINISHED\n"
try:
    G.cli(argv2[argv2.index("people") + 1:])
finally:
    G.run = real_run
check("by default: first rows, nothing guessed, not a dry run", seen["args"][:6] == ("Leads", "", "empty", 0, False, False), str(seen))
check("the button text uses no em dash", chr(0x2014) not in str(tool))

sys.exit(1 if fails else 0)
