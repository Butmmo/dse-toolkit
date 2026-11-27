"""Grid dedupe checks: grouping, merge preview, cross-engine flags, and apply, against a fake grid API.
Run: python tests/test_grid_dedupe.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dse import grid_dedupe as dd

fails = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


COLS = [
    {"key": "c_name", "label": "Business name", "type": "text"},
    {"key": "c_website", "label": "Website", "type": "url"},
    {"key": "c_email", "label": "Email", "type": "email"},
    {"key": "c_phone", "label": "Phone", "type": "phone"},
]
DOC = json.dumps({"custom": COLS})


def grid(gid, workbook, name):
    return {"id": gid, "name": name, "workbook": workbook, "workbook_id": "w-" + workbook, "doc": DOC}


class FakeApi:
    def __init__(self, grids, rows, delete_ok=True):
        self.grids = grids
        self.rows = {gid: [dict(r, data=dict(r["data"])) for r in rs] for gid, rs in rows.items()}
        self.delete_ok = delete_ok
        self.set_calls = []
        self.delete_calls = []

    def rpc(self, name, params, tries=2):
        if name == "hq_grid_list":
            return self.grids
        if name == "hq_grid_rows":
            rs = self.rows[params["p_grid"]]
            return rs[params["p_offset"]:params["p_offset"] + params["p_limit"]]
        if name == "hq_grid_set_cells":
            self.set_calls.append(params)
            n = 0
            for u in params["p_updates"]:
                for r in self.rows[params["p_grid"]]:
                    if r["id"] == u["id"]:
                        r["data"].update(u["cells"])
                        n += 1
            return n
        if name == "hq_grid_delete_rows":
            if not self.delete_ok:
                raise Exception("Could not find the function public.hq_grid_delete_rows")
            self.delete_calls.append(params)
            before = len(self.rows[params["p_grid"]])
            self.rows[params["p_grid"]] = [r for r in self.rows[params["p_grid"]] if r["id"] not in params["p_ids"]]
            return before - len(self.rows[params["p_grid"]])
        raise AssertionError("unexpected rpc " + name)


def fresh_api(delete_ok=True):
    g1 = grid("g1", "Dentists UK", "Leads")
    g2 = grid("g2", "Clinics UK", "Leads")
    rows1 = [
        {"id": "r1", "data": {"c_name": "Bright Smiles", "c_website": "https://www.brightsmiles.co.uk/", "c_email": "", "c_phone": ""}},
        {"id": "r2", "data": {"c_name": "Bright Smiles Dental", "c_website": "brightsmiles.co.uk", "c_email": "hello@brightsmiles.co.uk", "c_phone": "020 111"}},
        {"id": "r3", "data": {"c_name": "Other Practice", "c_website": "other.co.uk", "c_email": "team@other.co.uk", "c_phone": ""}},
        {"id": "r4", "data": {"c_name": "Bright Smiles (dup)", "c_website": "http://brightsmiles.co.uk/about", "c_email": "hello@brightsmiles.co.uk", "c_phone": "020 222"}},
        {"id": "r5", "data": {"c_name": "Solo", "c_website": "solo.co.uk", "c_email": "a@solo.co.uk", "c_phone": ""}},
    ]
    rows2 = [
        {"id": "x1", "data": {"c_name": "Other Practice Ltd", "c_website": "https://other.co.uk", "c_email": "team@other.co.uk", "c_phone": ""}},
        {"id": "x2", "data": {"c_name": "Unrelated", "c_website": "unrelated.co.uk", "c_email": "", "c_phone": ""}},
    ]
    return FakeApi([g1, g2], {"g1": rows1, "g2": rows2}, delete_ok)


# --- normalisers and column finding
check("domain_of strips scheme, www, path and case", dd.domain_of("HTTPS://www.BrightSmiles.co.uk/about?x=1") == "brightsmiles.co.uk")
check("domain_of rejects a bare word", dd.domain_of("brightsmiles") == "")
check("email_of normalises case and rejects junk", dd.email_of(" Hello@Example.co.uk ") == "hello@example.co.uk" and dd.email_of("not-an-email") == "")
check("the key column is found by meaning", dd.find_key_column(COLS, "domain")["key"] == "c_website" and dd.find_key_column(COLS, "email")["key"] == "c_email")

# --- the plan
api = fresh_api()
plan = dd.build_plan(api, grid("g1", "Dentists UK", "Leads"), "domain")
check("one duplicate group by domain, across www/scheme/path variants", len(plan["groups"]) == 1 and plan["groups"][0]["key"] == "brightsmiles.co.uk")
g = plan["groups"][0]
check("the oldest row stays and the other two are absorbed", g["keep_id"] == "r1" and g["absorbed_ids"] == ["r2", "r4"])
fills = {f["label"]: f["value"] for f in g["fills"]}
check("empty cells are filled from the absorbed rows", fills.get("Email") == "hello@brightsmiles.co.uk" and fills.get("Phone") == "020 111")
check("a differing later value is a reported clash, not a silent overwrite", any(c["label"] == "Phone" and c["kept"] == "020 111" and c["dropped"] == "020 222" for c in g["conflicts"]))
check("a differing business name is a reported clash", any(c["label"] == "Business name" for c in g["conflicts"]))
check("the cross-engine flag names the other grid for a non-duplicate row", any(f["key"] == "other.co.uk" and "Clinics UK / Leads" in f["also_in"] for f in plan["flags"]))
check("the duplicate group's cross-engine field is empty when it lives nowhere else", g["also_in"] == [])

text = dd.render(plan)
check("the preview says it changed nothing and counts the merge", "Preview only: nothing was changed" in text and "1 duplicate group(s): 2 row(s) would be merged away" in text)
check("the preview shows fills, clashes and flags in plain words", "Fills Email: hello@brightsmiles.co.uk" in text and "Clash on Phone" in text and "Also living in other engines" in text)

# --- email mode groups differently
plan_e = dd.build_plan(fresh_api(), grid("g1", "Dentists UK", "Leads"), "email")
check("dedupe by email groups the two rows sharing an address", len(plan_e["groups"]) == 1 and plan_e["groups"][0]["keep_id"] == "r2")

# --- preview changes nothing on the PC side either
api = fresh_api()
dd.run("g1", "domain", apply=False, api=api, say=lambda *_: None)
check("preview writes no cells and deletes no rows", api.set_calls == [] and api.delete_calls == [] and len(api.rows["g1"]) == 5)

# --- apply merges
api = fresh_api()
out = dd.run("g1", "domain", apply=True, api=api, say=lambda *_: None)
rows = {r["id"]: r for r in api.rows["g1"]}
check("apply removes the absorbed rows and keeps the rest", sorted(rows) == ["r1", "r3", "r5"])
check("apply fills the survivor's empty cells and keeps its own values", rows["r1"]["data"]["c_email"] == "hello@brightsmiles.co.uk" and rows["r1"]["data"]["c_phone"] == "020 111" and rows["r1"]["data"]["c_name"] == "Bright Smiles")
check("apply reports the merge counts", "Merged: 2 row(s) removed, 1 surviving row(s) filled in" in out)

# --- without the delete migration, apply stops before changing anything
api = fresh_api(delete_ok=False)
try:
    dd.run("g1", "domain", apply=True, api=api, say=lambda *_: None)
    stopped = False
except RuntimeError as e:
    stopped = "20270122120000_grid_delete_rows.sql" in str(e) and "Nothing was changed" in str(e)
check("a missing delete function stops the merge with the migration named", stopped)
check("... and truly nothing changed", api.set_calls == [] and len(api.rows["g1"]) == 5)

# --- a grid with no website column refuses in plain words
bare = {"id": "g9", "name": "Bare", "workbook": "W", "doc": json.dumps({"custom": [{"key": "c_name", "label": "Name", "type": "text"}]})}
api = FakeApi([bare], {"g9": [{"id": "q1", "data": {"c_name": "X"}}]})
try:
    dd.build_plan(api, bare, "domain")
    refused = False
except ValueError as e:
    refused = "no website or domain column" in str(e)
check("a grid with no website column refuses in plain words", refused)

print("FAILED: " + str(len(fails))) if fails else print("ALL PASS")
sys.exit(1 if fails else 0)
