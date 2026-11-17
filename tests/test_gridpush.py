"""Tests for HQ Tools into grids (dse/gridpush.py, the catalog entries and the dse.py command).   python tests/test_gridpush.py
Nothing real is contacted: Citadel is a fake that records every call."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import gridpush as G  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def doc(*cols):
    return json.dumps({"custom": [{"key": k, "label": l, "type": t} for k, l, t in cols], "view": {}, "views": []})


GRID = {"id": "11111111-1111-4111-8111-111111111111", "name": "Leads", "workbook": "Dentists UK",
        "doc": doc(("c_company", "Company", "text"), ("c_email", "Email", "email"), ("c_website", "Website", "url"), ("c_score", "Score", "number"), ("c_when", "Booked", "date"), ("c_vip", "VIP", "checkbox"))}
GRID2 = {"id": "22222222-2222-4222-8222-222222222222", "name": "Leads", "workbook": "Plumbers", "doc": doc(("c_email", "Email", "email"))}


class Api:
    def __init__(self, grids=None, fail=None):
        self.calls, self.grids, self.fail = [], grids if grids is not None else [GRID, GRID2], fail

    def rpc(self, name, body, tries=3):
        self.calls.append((name, body))
        if self.fail and name == self.fail:
            raise RuntimeError(f"Could not find the function public.{name}")
        if name == "hq_grid_list":
            return self.grids
        if name == "hq_grid_add_columns":
            return [{"label": c["label"], "key": "c_" + c["label"].lower().replace(" ", "_"), "type": c["type"], "created": c["label"] != "Company"} for c in body["p_cols"]]
        if name == "hq_grid_push":
            return {"added": len(body["p_rows"]), "updated": 0, "unchanged": 0, "skipped": 0, "invalid": 0, "error": ""}
        return None


tmp = Path(tempfile.mkdtemp())
try:
    # ---- reading a file
    f1 = tmp / "a.csv"
    f1.write_bytes("﻿Company,Email,Website\nSmile Ltd,Hi@Smile.co,https://smile.co\n\n,,\nBare Co,,\n".encode("utf-8"))
    h, r = G.load_csv(f1)
    check("a CSV is read with its byte-order mark and blank lines dropped", h == ["Company", "Email", "Website"] and len(r) == 2 and r[0][1] == "Hi@Smile.co")
    f2 = tmp / "b.csv"
    f2.write_text("Company;Email\nA;a@x.co\n", encoding="utf-8")
    f3 = tmp / "c.csv"
    f3.write_text("Company\tEmail\nA\ta@x.co\n", encoding="utf-8")
    check("semicolons and tabs are understood as well as commas", G.load_csv(f2)[0] == ["Company", "Email"] and G.load_csv(f3)[0] == ["Company", "Email"])
    f4 = tmp / "d.csv"
    f4.write_text("Company\n", encoding="utf-8")
    f5 = tmp / "e.csv"
    f5.write_text("Company\n" + "\n".join(f"c{i}" for i in range(5001)), encoding="utf-8")
    errs = []
    for p in (f4, f5):
        try:
            G.load_csv(p)
        except ValueError as e:
            errs.append(str(e))
    check("a file with no data rows, or more than 5,000, is refused with what to do", len(errs) == 2 and "header row" in errs[0] and "5,000" in errs[1])

    # ---- the grid's columns and which grid is meant
    cols = G.columns_of(GRID["doc"])
    check("a grid's columns come from its stored document; formula columns and bad keys are not filled", [c["key"] for c in cols] == ["c_company", "c_email", "c_website", "c_score", "c_when", "c_vip"] and G.columns_of(doc(("c_x", "X", "formula"), ("bad key", "B", "text"))) == [] and G.columns_of("not json") == [] and G.columns_of(None) == [])
    gs = [GRID, GRID2]
    check("a grid is found by id, by 'BPS Table/grid', or by name when only one has it", G.resolve_grid(gs, GRID["id"]) is GRID and G.resolve_grid(gs, "plumbers/leads") is GRID2 and G.resolve_grid([GRID], "leads") is GRID)
    msgs = []
    for ref in ("", "Leads", "nope"):
        try:
            G.resolve_grid(gs, ref)
        except ValueError as e:
            msgs.append(str(e))
    check("an unknown or ambiguous grid says which grids there are, and what to type", len(msgs) == 3 and "Name the grid" in msgs[0] and '"Dentists UK/Leads"' in msgs[1] and "More than one" in msgs[1] and "Your grids" in msgs[2])

    # ---- matching headers
    rows = [["Smile", "hi@smile.co", "smile.co", "7", "Notes here", "yes", "Leeds"], ["Bare", "", "", "8", "", "no", ""]]
    heads = ["Business name", "Work email", "Domain", "Score", "Hobby", "VIP", "City"]
    plan = G.map_headers(heads, cols, rows)
    check("headers match by name or by the usual other names (Business name = Company, Work email = Email, Domain = Website), and the rest become new columns with a guessed type", {i: c["label"] for i, c in plan["mapped"].items()} == {0: "Company", 1: "Email", 2: "Website", 3: "Score", 5: "VIP"} and set(plan["new"]) == {4, 6} and plan["new"][4] == "text" and not plan["ignored"])
    plan2 = G.map_headers(heads, cols, rows, new_columns=False)
    check("with new columns off, a header the grid does not have is left out and listed", plan2["new"] == {} and plan2["ignored"] == ["Hobby", "City"])
    plan3 = G.map_headers(heads, cols, rows, only={"work email", "city"})
    check("--only brings just those headers", set(plan3["mapped"]) == {1} and set(plan3["new"]) == {6} and "Business name" in plan3["ignored"])
    plan4 = G.map_headers(["Email", "Work email"], cols, [["a@x.co", "b@x.co"]])
    check("a column is filled by one header only: a second header for it becomes its own new column", set(plan4["mapped"]) == {0} and set(plan4["new"]) == {1})
    check("types are guessed from the values: numbers, dates, yes/no, emails, links, long text", G.infer_type(["1", "2,500", "-3.5"]) == "number" and G.infer_type(["2026-11-17", "17/11/2026"]) == "date" and G.infer_type(["yes", "No"]) == "checkbox" and G.infer_type(["a@b.co", "c@d.co"]) == "email" and G.infer_type(["https://x.co", "www.y.co"]) == "url" and G.infer_type(["y" * 130]) == "longtext" and G.infer_type([]) == "text" and G.infer_type(["12", "abc"]) == "text")
    check("values are converted to what the column holds: numbers as numbers, yes/no as booleans, dates tidied, empty as nothing", G.convert("1,250", "number") == 1250 and G.convert("7.5", "number") == 7.5 and G.convert("abc", "number") == "abc" and G.convert("Yes", "checkbox") is True and G.convert("no", "checkbox") is False
          and G.convert("2026-11-17T09:00:00Z", "date") == "2026-11-17" and G.convert("17/11/2026", "date") == "2026-11-17" and G.convert("  ", "text") is None and len(G.convert("x" * 3000, "text")) == 2000)
    check("the key is the one asked for (by name or key), else Email, else the website; a wrong name lists the columns", G.choose_key("Website", cols) == "c_website" and G.choose_key("c_company", cols) == "c_company" and G.choose_key("", cols) == "c_email" and G.choose_key("", [{"key": "c_site", "label": "URL", "type": "text"}]) == "c_site" and G.choose_key("", [{"key": "c_n", "label": "Notes", "type": "text"}]) is None)
    try:
        G.choose_key("Nope", cols)
        bad_key = ""
    except ValueError as e:
        bad_key = str(e)
    check("a key that is not a column says which columns there are", "Company" in bad_key and "Email" in bad_key)

    # ---- the whole push
    big = tmp / "big.csv"
    big.write_text("Company,Email,Hobby,Score\n" + "\n".join(f"C{i},e{i}@x.co,golf,{i}" for i in range(250)), encoding="utf-8")
    api = Api()
    out = G.push(big, "Dentists UK/Leads", api=api)
    names = [c[0] for c in api.calls]
    check("a push finds the grid, makes the one new column first, then sends the rows in chunks of 200 (250 rows = 2 calls)", names == ["hq_grid_list", "hq_grid_add_columns", "hq_grid_push", "hq_grid_push"] and [len(c[1]["p_rows"]) for c in api.calls[2:]] == [200, 50])
    p0 = api.calls[2][1]
    check("the rows use the grid's own keys, the new column's key, numbers as numbers, and the key is the Email column", p0["p_key"] == "c_email" and p0["p_rows"][3] == {"c_company": "C3", "c_email": "e3@x.co", "c_hobby": "golf", "c_score": 3} and p0["p_overwrite"] is False and p0["p_grid"] == GRID["id"])
    check("only the new column is created (the matched ones are not asked for again)", api.calls[1][1]["p_cols"] == [{"label": "Hobby", "type": "text"}])
    check("the summary says what was filled, what is new, the key, and how many were added", "Dentists UK / Leads" in out and "Business name" not in out and "Company -> Company" in out and "New columns: Hobby (text)" in out and "Key: Email" in out and "Done: 250 added" in out)
    api2 = Api()
    G.push(big, "Leads", key="Company", overwrite=True, new_columns=False, api=api2) if False else None
    api2 = Api(grids=[GRID])
    out2 = G.push(big, "Leads", key="Company", overwrite=True, new_columns=False, api=api2)
    check("--key and --overwrite are passed on, and with new columns off nothing is created", [c[0] for c in api2.calls].count("hq_grid_add_columns") == 0 and api2.calls[1][1]["p_key"] == "c_company" and api2.calls[1][1]["p_overwrite"] is True and "Left out: Hobby" in out2)
    api3 = Api()
    out3 = G.push(big, "Dentists UK/Leads", dry=True, api=api3)
    check("a dry run shows the plan and sends nothing at all (not even a new column)", [c[0] for c in api3.calls] == ["hq_grid_list"] and "Would make new columns: Hobby" in out3 and "Dry run: nothing was sent." in out3 and "Key: Email" in out3)
    nokey = tmp / "nokey.csv"
    nokey.write_text("Hobby\ngolf\n", encoding="utf-8")
    api4 = Api(grids=[{"id": GRID["id"], "name": "Notes only", "workbook": "X", "doc": doc(("c_n", "Notes", "text"))}])
    out4 = G.push(nokey, "Notes only", api=api4)
    check("with no way to tell leads apart there is no key, and the summary warns that a second run adds them again", api4.calls[-1][1]["p_key"] is None and "Key: none" in out4)
    no_match = tmp / "nm.csv"
    no_match.write_text("Zzz\n1\n", encoding="utf-8")
    try:
        G.push(no_match, "Leads", new_columns=False, api=Api(grids=[GRID]))
        nm = ""
    except ValueError as e:
        nm = str(e)
    check("a file whose headers match nothing (with new columns off) is refused and the grid's columns are listed", "None of the file's headers" in nm and "Company" in nm)
    check("listing grids shows the BPS Table, the grid and its columns, and tells a new member what to do first", "Dentists UK / Leads" in G.list_grids(Api()) and "Plumbers / Leads" in G.list_grids(Api()) and "BPS Tables" in G.list_grids(Api(grids=[])))
    check("the original file is never changed", f1.read_bytes().startswith(b"\xef\xbb\xbfCompany") and big.read_text(encoding="utf-8").startswith("Company,Email,Hobby,Score"))
    res_errs = Api()
    res_errs.rpc = lambda name, body, tries=3: {"added": 1, "updated": 0, "unchanged": 0, "skipped": 0, "invalid": 1, "error": "A grid can hold up to 20,000 rows."} if name == "hq_grid_push" else (GRID and [GRID])
    out5 = G.push(f1, "Leads", new_columns=False, api=res_errs)
    check("a problem the database reports is shown, with how many rows could not be added", "1 could not be added" in out5 and "First problem: A grid can hold up to 20,000 rows." in out5)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- wiring
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.grid_push"]
check("the tool asks for a list from my-lists and a grid, with a key, an only-list and three tick boxes, and passes them as the command expects", [f["name"] for f in t["fields"]] == ["csv", "grid", "key", "only", "no_new", "overwrite", "dry"] and t["fields"][0]["glob"] == "my-lists/*.csv" and t["args"][:2] == [{"lit": "grid"}, {"lit": "push"}] and {"flag": "--dry", "field": "dry"} in t["args"] and {"flag": "--no-new-columns", "field": "no_new"} in t["args"] and {"opt": "--key", "field": "key"} in t["args"])
check("the tool says it changes only the named grid, never the file, and suggests a dry run first", "never changed" in t["help"] and "Dry run first" in t["help"] and "only the grid you name" in t["help"])
check("the list tool takes no input and is in the catalog", cat["tools"]["dse.grid_list"]["fields"] == [] and cat["tools"]["dse.grid_list"]["args"] == [{"lit": "grid"}, {"lit": "list"}])
src = {n: (ROOT / n).read_text(encoding="utf-8") for n in ("dse.py", "dse/gridpush.py", "bridge/add_grid_tools.py")}
check("dse.py has the grid command", 'sub.add_parser("grid"' in src["dse.py"] and "gridpush.cli(a.rest)" in src["dse.py"])
check("nothing in the module prints a token, a key or the file's contents beyond the summary", "token" not in src["dse/gridpush.py"].lower().replace("mobile", "") and "HQ_RUNNER_TOKEN" not in src["dse/gridpush.py"])
check("no em dash", DASH not in src["dse/gridpush.py"] + src["bridge/add_grid_tools.py"] + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
