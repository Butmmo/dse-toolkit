"""Tests for first name, last name and work email on an existing grid (dse/gridpeople.py).   python tests/test_gridpeople.py
Nothing real is contacted: Citadel and the website reader are fakes that record every call."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import gridpeople as G  # noqa: E402

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
check("a name is split into first and last, honorifics, suffixes and a middle initial dropped",
      G.split_name("Dr. Mary Ann Smith, MBA") == ("Mary", "Smith") and G.split_name("Ian R. Clark") == ("Ian", "Clark") and G.split_name("Lewis Sadler Jr.") == ("Lewis", "Sadler"))
check("one word is a first name only, an initial first is kept, nothing gives nothing",
      G.split_name("Madonna") == ("Madonna", "") and G.split_name("J. Smith") == ("J", "Smith") and G.split_name("") == ("", "") and G.split_name("Dr.") == ("", ""))


# ---------------------------------------------------------------- which email
def site(emails, domain="acme.example", people=None, guesses=None, mx=""):
    return {"domain": domain, "emails": [{"email": e, "kind": k} for e, k in emails], "people": people or [], "guesses": guesses or [], "mx": mx}


S1 = site([("info@acme.example", "generic"), ("pat.jones@acme.example", "personal"), ("owen@acme.example", "personal")])
check("the person's own address wins over another personal one and the general one", G.pick_work_email(S1, "Owen", "Hart") == ("owen@acme.example", "personal"))
check("with nothing matching the person, any personal address on the domain wins over info@", G.pick_work_email(S1, "Zed", "Quill") == ("pat.jones@acme.example", "personal"))
check("only a general address is a role address", G.pick_work_email(site([("info@acme.example", "generic")]), "Owen", "Hart") == ("info@acme.example", "role address"))
check("an address on another company's domain is not a work email, a gmail is a personal mailbox",
      G.pick_work_email(site([("seo@agency.example", "generic")]), "", "") == ("", "") and G.pick_work_email(site([("bob@gmail.com", "freemail")]), "Bob", "Day") == ("bob@gmail.com", "personal mailbox"))
check("a subdomain of the business is its own domain, another company is not", G.own_domain("a@mail.acme.example", "www.acme.example") and G.own_domain("a@acme.example", "acme.example") and not G.own_domain("a@acme.example.evil.com", "acme.example"))
G1 = site([], people=[{"name": "Owen Hart", "title": "Owner"}], guesses=["owen@acme.example", "owen.hart@acme.example", "ohart@acme.example"], mx="yes")
check("nothing is guessed unless asked", G.pick_work_email(G1, "Owen", "Hart") == ("", ""))
check("a guess is first.last on a domain that receives mail, and is marked guess", G.pick_work_email(G1, "Owen", "Hart", guess=True) == ("owen.hart@acme.example", "guess"))
check("no guess when the domain does not receive mail or there is no last name", G.pick_work_email(dict(G1, mx="no"), "Owen", "Hart", guess=True) == ("", "") and G.pick_work_email(G1, "Owen", "", guess=True) == ("", ""))
check("the person comes from the most senior name on the site", G.person_of(site([], people=[{"name": "Dr. Owen Hart", "title": "Owner"}, {"name": "Jo Lee", "title": "Manager"}])) == ("Owen", "Hart") and G.person_of({}) == ("", ""))


# ---------------------------------------------------------------- a grid
def doc(extra=()):
    cols = [{"key": "c_company", "label": "Company", "type": "text"}, {"key": "c_site", "label": "Website", "type": "url"}, {"key": "c_note", "label": "Notes", "type": "text"}] + list(extra)
    return json.dumps({"custom": cols, "view": {}, "views": []})


GRID = {"id": "11111111-1111-4111-8111-111111111111", "name": "Leads", "workbook": "Tree surgeons", "doc": doc()}
ROWS = [{"id": "r1", "data": {"c_company": "Acme", "c_site": "acme.example"}},
        {"id": "r2", "data": {"c_company": "Bright", "c_site": "bright.example"}},
        {"id": "r3", "data": {"c_company": "No site"}},
        {"id": "r4", "data": {"c_company": "Down", "c_site": "down.example"}},
        {"id": "r5", "data": {"c_company": "Role only", "c_site": "role.example"}}]
SITES = {"acme.example": site([("owen@acme.example", "personal"), ("info@acme.example", "generic")], people=[{"name": "Owen Hart", "title": "Owner"}]),
         "bright.example": site([("bright@gmail.com", "freemail")], domain="bright.example", people=[{"name": "Dr. Mary Ann Smith", "title": "Director"}]),
         "role.example": site([("office@role.example", "generic")], domain="role.example")}
READ = []


def fake_site(web):
    READ.append(web)
    if web == "down.example":
        raise OSError("no route")
    return SITES.get(web, {})


class Api:
    def __init__(self, rows=ROWS, grid=GRID):
        self.rows, self.grid, self.calls, self.cells, self.added = [json.loads(json.dumps(r)) for r in rows], dict(grid), [], {}, []

    def rpc(self, name, body, tries=3):
        self.calls.append((name, body))
        if name == "hq_grid_list":
            return [self.grid]
        if name == "hq_grid_rows":
            return self.rows[body["p_offset"]: body["p_offset"] + body["p_limit"]]
        if name == "hq_grid_add_columns":
            out = []
            for i, c in enumerate(body["p_cols"]):
                out.append({"key": "c_new" + str(len(self.added) + i), "label": c["label"], "type": c["type"], "created": True})
            self.added += [(o["key"], o["label"]) for o in out]
            return out
        if name == "hq_grid_set_cells":
            for u in body["p_updates"]:
                self.cells.setdefault(u["id"], {}).update(u["cells"])
            return len(body["p_updates"])
        raise RuntimeError("unexpected " + name)


def go(api, **kw):
    lines = []
    READ.clear()
    out = G.run("Leads", say=lines.append, api=api, site=fake_site, **kw)
    return out, lines


api = Api()
out, lines = go(api)
by_label = {lbl: key for key, lbl in api.added}
check("the four columns the grid lacked are added, with an email type for the address",
      [lbl for _k, lbl in api.added] == ["First name", "Last name", "Work email", "Email type"]
      and next(c for n, b in api.calls if n == "hq_grid_add_columns" for c in b["p_cols"] if c["label"] == "Work email")["type"] == "email")
r1 = api.cells["r1"]
check("a row gets first name, last name, work email and its type",
      r1 == {by_label["First name"]: "Owen", by_label["Last name"]: "Hart", by_label["Work email"]: "owen@acme.example", by_label["Email type"]: "personal"}, str(r1))
check("a gmail owner is a personal mailbox, the middle name and title are dropped",
      api.cells["r2"] == {by_label["First name"]: "Mary", by_label["Last name"]: "Smith", by_label["Work email"]: "bright@gmail.com", by_label["Email type"]: "personal mailbox"}, str(api.cells.get("r2")))
check("a site with only a general address gives a role address and no name cells",
      api.cells["r5"] == {by_label["Work email"]: "office@role.example", by_label["Email type"]: "role address"}, str(api.cells.get("r5")))
check("a row with no website is never read, an unreachable site is counted and does not stop the run",
      "r3" not in api.cells and "down.example" in READ and "r4" not in api.cells and "1 failed" in out and "3 with a work email" in out and "2 with a first and last name" in out, out)
check("progress lines are reported for Citadel", any(x.startswith("PROGRESS ") for x in lines) and out.startswith("FINISHED"))
check("every row's site is read once", sorted(READ) == ["acme.example", "bright.example", "down.example", "role.example"], str(READ))

# a second run only does what is still empty, and never replaces what is there
cols2 = [{"key": k, "label": lbl, "type": "text"} for k, lbl in api.added]
rows2 = []
for r in api.rows:
    rows2.append({"id": r["id"], "data": {**r["data"], **api.cells.get(r["id"], {})}})
rows2[0]["data"][by_label["Work email"]] = "mine@acme.example"
api2 = Api(rows=rows2, grid=dict(GRID, doc=doc(cols2)))
out2, _ = go(api2)
check("nothing is added a second time when the columns exist, and rows already complete are skipped (Down and Role only are retried: they still lack a name or an address)",
      not any(n == "hq_grid_add_columns" for n, _b in api2.calls) and READ == ["down.example", "role.example"], str(READ))
api3 = Api(rows=rows2, grid=api2.grid)
out3, _ = go(api3, mode="all")
check("a value already in a cell is kept in the normal mode and replaced in mode all",
      api2.cells.get("r1") is None and api3.cells["r1"][by_label["Work email"]] == "owen@acme.example", str(api3.cells.get("r1")))

# a name you typed is never replaced by the normal run, only the empty cells are filled
typed = [{"id": "t1", "data": {"c_site": "acme.example", by_label["First name"]: "Owen-by-hand"}}]
api_t = Api(rows=typed, grid=dict(GRID, doc=doc(cols2)))
go(api_t)
check("a first name you typed is kept, and the empty cells of the same row are still filled",
      by_label["First name"] not in api_t.cells["t1"] and api_t.cells["t1"][by_label["Last name"]] == "Hart" and api_t.cells["t1"][by_label["Work email"]] == "owen@acme.example", str(api_t.cells))

# an existing column under another name is used, not duplicated
grid_b = dict(GRID, doc=doc([{"key": "c_fn", "label": "First Name", "type": "text"}, {"key": "c_ln", "label": "Surname", "type": "text"}, {"key": "c_em", "label": "Email", "type": "email"}]))
api4 = Api(grid=grid_b)
go(api4)
check("columns the grid has under similar names (First Name, Surname, Email) are used, only Email type is added",
      [lbl for _k, lbl in api4.added] == ["Email type"] and api4.cells["r1"]["c_fn"] == "Owen" and api4.cells["r1"]["c_ln"] == "Hart" and api4.cells["r1"]["c_em"] == "owen@acme.example", str(api4.cells.get("r1")))

# options
api5 = Api()
out5, _ = go(api5, dry=True)
check("a dry run reads nothing, adds nothing, saves nothing", READ == [] and not api5.added and not api5.cells and "Dry run" in out5 and "Would add columns" in out5)
api6 = Api()
go(api6, limit=1)
check("--limit reads only the first rows", READ == ["acme.example"], str(READ))
SITES["acme.example"] = dict(G1, domain="acme.example")
api7 = Api(rows=[{"id": "r9", "data": {"c_site": "acme.example"}}])
out7, _ = go(api7, guess=True)
labels7 = {lbl: k for k, lbl in api7.added}
check("--guess fills a likely address, marked guess",
      api7.cells["r9"][labels7["Work email"]] == "owen.hart@acme.example" and api7.cells["r9"][labels7["Email type"]] == "guess" and "No addresses were guessed" not in out7, str(api7.cells))
api8 = Api(rows=[{"id": "r9", "data": {"c_site": "acme.example"}}])
out8, _ = go(api8)
labels8 = {lbl: k for k, lbl in api8.added}
check("without --guess nothing is guessed and the run says so", "No addresses were guessed" in out8 and labels8["Work email"] not in api8.cells.get("r9", {}), str(api8.cells))
SITES["acme.example"] = site([("owen@acme.example", "personal")], people=[{"name": "Owen Hart", "title": "Owner"}])

# problems are explained
no_site_grid = dict(GRID, doc=json.dumps({"custom": [{"key": "c_a", "label": "Company", "type": "text"}]}))
check("a grid with no website column is explained", "website column" in str(_try(lambda: G.run("Leads", api=Api(grid=no_site_grid), site=fake_site))))
check("a named website column that does not exist is explained, an unknown mode is refused",
      "no column called" in str(_try(lambda: G.run("Leads", from_ref="Nope", api=Api(), site=fake_site))) and "mode must be" in str(_try(lambda: G.run("Leads", mode="x", api=Api()))))
their = dict(GRID, doc=doc([{"key": "c_url2", "label": "Their page", "type": "text"}]))
check("the website column can be named", G.find_columns(G.gridpush.columns_of(their["doc"]), "Their page")["website"]["key"] == "c_url2")
check("the text uses no em dash", chr(0x2014) not in Path(G.__file__).read_text(encoding="utf-8"))

sys.exit(1 if fails else 0)
