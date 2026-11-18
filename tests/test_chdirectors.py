"""Tests for Companies House directors (dse/chdirectors.py, `python dse.py directors`, `grid people --companies-house`).   python tests/test_chdirectors.py
Nothing real is contacted: the register's API is a fake that records every request."""
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import chdirectors as CH, common as CM, gridpeople as G  # noqa: E402
from bridge import runner as R  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def _try(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        return e
    return None


# ---------------------------------------------------------------- names
check("'SURNAME, Forenames' becomes first and last name, with case fixed and the first forename only",
      CH.ch_name("SMITH, John Michael") == ("John", "Smith") and CH.ch_name("O'NEIL, Mary") == ("Mary", "O'Neil") and CH.ch_name("SMITH-JONES, Ann") == ("Ann", "Smith-Jones"))
check("an honorific in the forenames is dropped, a name without a comma is read as first then last", CH.ch_name("HART, Dr Owen") == ("Owen", "Hart") and CH.ch_name("Owen Hart") == ("Owen", "Hart") and CH.ch_name("") == ("", ""))

# ---------------------------------------------------------------- which company
def co(title, number, status="active", locality="Leeds"):
    return {"title": title, "company_number": number, "company_status": status, "address_snippet": f"1 High St, {locality}, LS1 1AA", "address": {"locality": locality}}


check("the same name apart from Ltd and Limited is an exact match", CH.choose_company([co("ACME TREE SERVICES LIMITED", "1")], "Acme Tree Services Ltd")[1] == "exact")
check("a trade name that is part of the company's name is a close match", CH.choose_company([co("ACE ROOFING SERVICES LTD", "2")], "Ace Roofing")[1] == "close")
check("a dissolved company is never matched", CH.choose_company([co("ACME TREE SERVICES LTD", "3", "dissolved")], "Acme Tree Services")[0] is None)
check("a different company with a few words in common is not matched", CH.choose_company([co("ACME FINANCE HOLDINGS LTD", "4")], "Acme Tree Services")[0] is None)
two = [co("SMITH TREE CARE LTD", "5", locality="Leeds"), co("SMITH TREE CARE LTD", "6", locality="Hull")]
check("two companies that fit equally well: no town means no match, the town breaks the tie",
      CH.choose_company(two, "Smith Tree Care")[0] is None and CH.choose_company(two, "Smith Tree Care", "Hull")[0]["company_number"] == "6" and CH.choose_company(two, "Smith Tree Care", "York")[0] is None)
check("an empty search or no name gives no match", CH.choose_company([], "Acme")[0] is None and CH.norm_tokens("Ltd") == [])

# ---------------------------------------------------------------- which director
OFF = [{"name": "DOE, Jane", "officer_role": "secretary", "appointed_on": "2001-01-01"},
       {"name": "OLD, Bob", "officer_role": "director", "appointed_on": "2005-05-05", "resigned_on": "2015-01-01"},
       {"name": "NOMINEE SERVICES LTD", "officer_role": "corporate-director", "appointed_on": "2000-01-01"},
       {"name": "HART, Owen James", "officer_role": "director", "appointed_on": "2010-03-03"},
       {"name": "LEE, Jo", "officer_role": "director", "appointed_on": "2018-08-08"}]
d = CH.pick_director(OFF)
check("the longest-serving active human director is picked: not a secretary, a resigned officer or a company", d and (d["first"], d["last"]) == ("Owen", "Hart") and d["role"] == "director", str(d))
check("nobody active gives no director", CH.pick_director(OFF[:3]) is None and CH.pick_director([]) is None)

# ---------------------------------------------------------------- the lookup, with a fake register
REQ = []


def fake_http(path, params):
    REQ.append((path, dict(params)))
    if path == "/search/companies":
        q = params["q"].lower()
        if "acme" in q:
            return 200, {"items": [co("ACME TREE SERVICES LTD", "01234567")]}
        if "broken" in q:
            return 500, {}
        if "denied" in q:
            return 401, {}
        return 200, {"items": []}
    if path.startswith("/company/01234567/officers"):
        return 200, {"items": OFF}
    return 404, {}


def client(sleep=None):
    return CH.Client("k", http=fake_http, sleep=sleep or (lambda s: None))


REQ.clear()
r = CH.director_for(client(), "Acme Tree Services Ltd", "Leeds")
check("a business is found by name and its director read: two requests",
      r == {"first": "Owen", "last": "Hart", "role": "director", "company": "ACME TREE SERVICES LTD", "number": "01234567", "match": "exact"} and [p for p, _ in REQ] == ["/search/companies", "/company/01234567/officers"], str(r))
check("no company means no second request and a reason", CH.director_for(client(), "Nobody Ltd").get("why") == "no company of that name")
check("a server error is a reason, not a crash, and a refused key is explained with how to get one", "HTTP 500" in CH.director_for(client(), "Broken Co")["why"] and "free API key" in str(_try(lambda: CH.director_for(client(), "Denied Co"))))
check("an empty name is not searched", CH.director_for(client(), "  ").get("why") == "no business name")

# pacing and slow-down
slept = []
c = CH.Client("k", http=fake_http, sleep=slept.append)
c.get("/search/companies", {"q": "x"})
c.get("/search/companies", {"q": "y"})
check("requests are paced (about 0.6 s apart) to stay inside the register's limit", any(0 < s <= CH.PACE for s in slept), str(slept))
n429 = []


def flaky(path, params):
    n429.append(1)
    return (429, {}) if len(n429) == 1 else (200, {"items": []})


slept2 = []
c2 = CH.Client("k", http=flaky, sleep=slept2.append)
status, _ = c2.get("/search/companies", {"q": "x"})
check("a 429 waits and tries once more", status == 200 and len(n429) == 2 and 5 in slept2, str(slept2))

# ---------------------------------------------------------------- the key
os.environ.pop(CH.ENV, None)
saved = CH.api_key
CH.api_key = lambda: ""
err = str(_try(CH.need_key))
check("with no key the message says how to get one and where to set it, and never contains a key", "developer.company-information.service.gov.uk" in err and CH.ENV in err and "setx" in err)
CH.api_key = saved
os.environ[CH.ENV] = "  secret-key-123  "
check("a key in the environment is read and trimmed", CH.api_key() == "secret-key-123")
os.environ.pop(CH.ENV)
check("the key is never written into the module text or the catalog", "secret-key-123" not in Path(CH.__file__).read_text(encoding="utf-8"))

# ---------------------------------------------------------------- a CSV list
TMP = Path(tempfile.mkdtemp(prefix="zz-chd-"))
CM.LISTS = TMP
src = TMP / "leads.csv"
CM.write_csv(src, [{"Company": "Acme Tree Services Ltd", "City": "Leeds"}, {"Company": "Nobody Ltd", "City": "Hull"}, {"Company": "", "City": "York"}, {"Company": "Acme Tree Services Ltd", "City": "Leeds"}])
REQ.clear()
dst = CH.file(str(src), max_rows=2, out=str(TMP / "out.csv"), client=client())
rows = list(csv.DictReader(open(dst, encoding="utf-8-sig")))
check("the list gets the director columns, the original columns are kept, rows without a name are skipped",
      rows[0]["director_first"] == "Owen" and rows[0]["director_last"] == "Hart" and rows[0]["ch_number"] == "01234567" and rows[0]["ch_match"] == "exact" and rows[0]["Company"] == "Acme Tree Services Ltd"
      and rows[1]["ch_match"] == "no company of that name" and rows[2]["director_first"] == "" and len(rows) == 4, str(rows))
check("--max stops the lookups: the fourth row is not looked up", rows[3]["ch_match"].startswith("not looked up") and len([1 for p, _ in REQ if p == "/search/companies"]) == 2, str(REQ))
check("a list without a business name column is explained", "business name column" in str(_try(lambda: CH.file(str(TMP / "none.csv"), client=client()) if CM.write_csv(TMP / "none.csv", [{"x": "1"}]) is None else None)))

# ---------------------------------------------------------------- grid people with Companies House
def doc(extra=()):
    cols = [{"key": "c_company", "label": "Company", "type": "text"}, {"key": "c_site", "label": "Website", "type": "url"}, {"key": "c_city", "label": "City", "type": "text"}] + list(extra)
    return json.dumps({"custom": cols, "view": {}, "views": []})


GRID = {"id": "11111111-1111-4111-8111-111111111111", "name": "Leads", "workbook": "Trees", "doc": doc()}


class Api:
    def __init__(self, rows, grid=GRID):
        self.rows, self.grid, self.cells, self.added = rows, grid, {}, []

    def rpc(self, name, body, tries=3):
        if name == "hq_grid_list":
            return [self.grid]
        if name == "hq_grid_rows":
            return self.rows[body["p_offset"]: body["p_offset"] + body["p_limit"]]
        if name == "hq_grid_add_columns":
            out = [{"key": "c_n" + str(len(self.added) + i), "label": c["label"], "type": c["type"]} for i, c in enumerate(body["p_cols"])]
            self.added += [(o["key"], o["label"]) for o in out]
            return out
        if name == "hq_grid_set_cells":
            for u in body["p_updates"]:
                self.cells.setdefault(u["id"], {}).update(u["cells"])
            return len(body["p_updates"])
        raise RuntimeError(name)


SITES = {"named.example": {"domain": "named.example", "emails": [{"email": "sam@named.example", "kind": "personal"}], "people": [{"name": "Sam Rowe", "title": "Owner"}]},
         "quiet.example": {"domain": "quiet.example", "emails": [], "people": []}}
rows = [{"id": "a", "data": {"c_company": "Named Ltd", "c_site": "named.example"}},
        {"id": "b", "data": {"c_company": "Acme Tree Services Ltd", "c_site": "quiet.example", "c_city": "Leeds"}}]
REQ.clear()
api = Api(rows)
out = G.run("Leads", say=lambda m: None, api=api, site=lambda w: SITES[w], companies_house=True, ch=client(), mx=lambda d: "yes", guess=True)
lab = {l: k for k, l in api.added}
check("the Name source column is added only for this option", "Name source" in lab and "First name" in lab)
check("a website that names the owner is never sent to the register, and its source says website", all("named" not in p["q"].lower() for p, p in [(a, b) for a, b in REQ if a == "/search/companies"]) and api.cells["a"][lab["Name source"]] == "website", str(REQ))
check("a website that names nobody: the director from the register, with the company and number as the source",
      api.cells["b"][lab["First name"]] == "Owen" and api.cells["b"][lab["Last name"]] == "Hart" and api.cells["b"][lab["Name source"]] == "Companies House: ACME TREE SERVICES LTD (01234567)", str(api.cells.get("b")))
check("with --guess and a domain that receives mail, the register's name gives a marked guess", api.cells["b"][lab["Work email"]] == "owen.hart@quiet.example" and api.cells["b"][lab["Email type"]] == "guess", str(api.cells.get("b")))
check("the run reports how many names came from Companies House", "1 from Companies House" in out, out)
api2 = Api(rows)
G.run("Leads", say=lambda m: None, api=api2, site=lambda w: SITES[w], companies_house=True, ch=client(), mx=lambda d: "no", guess=True)
check("no guess when the domain does not receive mail", "c_n2" not in api2.cells["b"] and not any(v == "owen.hart@quiet.example" for v in api2.cells["b"].values()), str(api2.cells.get("b")))
api2b = Api(rows)
G.run("Leads", say=lambda m: None, api=api2b, site=lambda w: SITES[w], companies_house=True, ch=client(), mx=lambda d: "yes")
check("without --guess the register's name never produces a guessed address", api2b.cells["b"].get({l: k for k, l in api2b.added}["First name"]) == "Owen" and not any("@" in str(v) for v in api2b.cells["b"].values()), str(api2b.cells.get("b")))
api3 = Api(rows)
G.run("Leads", say=lambda m: None, api=api3, site=lambda w: SITES[w], ch=client())
check("without the option the register is not asked and there is no Name source column", "Name source" not in {l for _k, l in api3.added} and "b" not in api3.cells)
nocomp = dict(GRID, doc=json.dumps({"custom": [{"key": "c_site", "label": "Website", "type": "url"}]}))
check("the option needs a business name column, and says so", "business name column" in str(_try(lambda: G.run("Leads", api=Api(rows, nocomp), site=lambda w: SITES[w], companies_house=True, ch=client()))))
CH.api_key = lambda: ""
check("with the option and no key the run stops at once with how to get one, before reading any site", "free API key" in str(_try(lambda: G.run("Leads", api=Api(rows), site=lambda w: 1 / 0, companies_house=True))))
CH.api_key = saved

# ---------------------------------------------------------------- the commands and buttons
helptext = subprocess.run([sys.executable, str(ROOT / "dse.py"), "directors", "--help"], capture_output=True, text=True).stdout
check("python dse.py directors exists", "--company-column" in helptext and "--city-column" in helptext)
cat = R.load_catalog(base_only=True)
tool, gp = cat["tools"].get("dse.directors"), cat["tools"].get("dse.grid_people")
check("the directors button is in Find clients, the list is chosen from your lists, and every field is used",
      tool and tool["group"] == "Find clients" and all(f["name"] in {a.get("field") for a in tool["args"]} for f in tool["fields"]) and all(a["field"] in {f["name"] for f in tool["fields"]} for a in tool["args"] if "field" in a))
(ROOT / "my-lists").mkdir(exist_ok=True)
(ROOT / "my-lists" / "zz-test-leads.csv").write_text("Company,City\nAcme,Leeds\n", encoding="utf-8")
try:
    argv, _ = R.build_command(cat, "dse.directors", {"csv": "my-lists/zz-test-leads.csv", "company_column": "Company", "city_column": "City", "max": 50})
finally:
    (ROOT / "my-lists" / "zz-test-leads.csv").unlink()
check("the directors button builds a command with the list, both columns and the limit", argv[argv.index("directors") + 1:] == ["my-lists/zz-test-leads.csv", "--company-column", "Company", "--city-column", "City", "--max", "50"], str(argv))
check("the grid button has the Companies House box, off by default", gp and any(f["name"] == "companies_house" and f["default"] is False for f in gp["fields"]) and any(a.get("flag") == "--companies-house" for a in gp["args"]))
check("no em dash in the button text or the module", chr(0x2014) not in json.dumps([tool, gp]) and chr(0x2014) not in Path(CH.__file__).read_text(encoding="utf-8"))

sys.exit(1 if fails else 0)
