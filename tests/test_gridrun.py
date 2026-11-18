"""Tests for Run column (dse/gridrun.py, the catalog entry and the dse.py command).   python tests/test_gridrun.py
Nothing real is contacted: Citadel, Claude and the website reader are fakes that record every call."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import gridrun as R  # noqa: E402

fails = []
DASH = chr(0x2014)


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


AI = {"kind": "ai", "prompt": "Write a one-line opener for {Company} in {City}", "model": "haiku"}
SITE = {"kind": "site", "from": "Website", "field": "email"}


def doc(run_ai=AI, run_site=SITE, opener_type="longtext"):
    cols = [
        {"key": "c_company", "label": "Company", "type": "text"}, {"key": "c_website", "label": "Website", "type": "url"}, {"key": "c_city", "label": "City", "type": "text"},
        {"key": "c_opener", "label": "Opener", "type": opener_type, **({"run": run_ai} if run_ai else {})},
        {"key": "c_found", "label": "Email found", "type": "email", **({"run": run_site} if run_site else {})},
        {"key": "c_status", "label": "Status", "type": "select", "options": [{"value": "hot", "label": "Hot"}, {"value": "cold", "label": "Cold"}]},
        {"key": "c_score", "label": "Score", "type": "number"}, {"key": "c_when", "label": "When", "type": "date"}, {"key": "c_vip", "label": "VIP", "type": "checkbox"},
        {"key": "c_calc", "label": "Calc", "type": "formula", "formula": "1+1"},
    ]
    return json.dumps({"custom": cols, "view": {}, "views": []})


GRID = {"id": "11111111-1111-4111-8111-111111111111", "name": "Leads", "workbook": "Dentists UK", "doc": doc()}


def mkrows(n=5):
    base = [{"id": "r1", "data": {"c_company": "Acme", "c_city": "Leeds", "c_website": "acme.com"}},
            {"id": "r2", "data": {"c_company": "Bright", "c_opener": "Hi Bright", "c_website": "bright.co.uk", "c_status": "hot"}},
            {"id": "r3", "data": {}},
            {"id": "r4", "data": {"c_city": "York"}},
            {"id": "r5", "data": {"c_company": "Zed", "c_website": "zed.com", "c_score": 7}}]
    return base[:n]


class Api:
    def __init__(self, rows, grid=GRID, save_fails=0):
        self.rows, self.grid, self.calls, self.save_fails = rows, grid, [], save_fails
        self.saved = {}

    def rpc(self, name, body, tries=3):
        self.calls.append((name, body))
        if name == "hq_grid_list":
            return [self.grid]
        if name == "hq_grid_rows":
            return self.rows[body["p_offset"]: body["p_offset"] + body["p_limit"]]
        if name == "hq_grid_set_cells":
            if self.save_fails > 0 and len(body["p_updates"]) > 1:
                self.save_fails -= 1
                raise RuntimeError("batch refused")
            for u in body["p_updates"]:
                self.saved.setdefault(u["id"], {}).update(u["cells"])
            return len(body["p_updates"])
        raise RuntimeError("unexpected " + name)


class Cost:
    def __init__(self, limit_after=None):
        self.n, self.limit_after, self.recorded = 0, limit_after, []

    def over_limit(self):
        return self.limit_after is not None and self.n >= self.limit_after

    def limit(self):
        return 1000

    def record(self, model, tin, tout):
        self.n += 1
        self.recorded.append((model, tin, tout))


def run(api, col="Opener", mode="empty", limit=0, dry=False, ask=None, site=None, cost=None):
    lines = []
    out = R.run("Leads", col, mode, limit, dry, say=lines.append, api=api, ask=ask or (lambda p, t: ("answer for " + p[:12], 10, 5, "claude-haiku-5-5")), site=site, cost=cost or Cost(), key_present=lambda: "sk-test")
    return out, lines


# ---- reading the grid
cols = R.parse_columns(GRID["doc"])
check("columns are read with their run settings; a formula column is left out", [c["label"] for c in cols] == ["Company", "Website", "City", "Opener", "Email found", "Status", "Score", "When", "VIP"] and cols[3]["run"]["kind"] == "ai" and cols[4]["run"]["field"] == "email")
check("a run setting that is incomplete or odd is no run setting (same rules as the grid)", R.clean_run({"kind": "ai", "prompt": "  "}) is None and R.clean_run({"kind": "site", "from": "Website", "field": "nope"}) is None and R.clean_run({"kind": "x"}) is None and R.clean_run({"kind": "ai", "prompt": "q {A}", "model": "gpt"})["model"] == "haiku" and R.clean_run({"kind": "ai", "prompt": "q {A}", "model": "sonnet"})["model"] == "sonnet")
check("a column is found by key or by name ignoring case and spacing, with a helpful error otherwise", R.find_column(cols, "c_opener")["label"] == "Opener" and R.find_column(cols, "  opener ")["key"] == "c_opener" and "Its columns" in str(_try(lambda: R.find_column(cols, "Nope"))))
check("the prompt names are matched ignoring case and filled from the row, an empty cell becomes nothing, a choice shows its label", R.build_prompt("{company} / {  City }", cols, {"c_company": "Acme"}) == "Acme / " and R.build_prompt("{Status}", cols, {"c_status": "hot"}) == "Hot" and R.prompt_refs("a {Company} {company} {City}") == ["Company", "City"])

# ---- what can run
check("a column without a setting, a question with no column in it, an unknown column, itself or a missing website column cannot run, each with a plain reason", "no run setting" in R.problem({"key": "c_x", "label": "X", "run": None}, cols)
      and "names no column" in R.problem({"key": "c_opener", "run": {"kind": "ai", "prompt": "hello", "model": "haiku"}}, cols) and "does not have: {Nope}" in R.problem({"key": "c_opener", "run": {"kind": "ai", "prompt": "x {Nope}", "model": "haiku"}}, cols)
      and "cannot use the column it fills" in R.problem({"key": "c_opener", "run": {"kind": "ai", "prompt": "x {Opener}", "model": "haiku"}}, cols) and "is not in the grid" in R.problem({"key": "c_found", "run": {"kind": "site", "from": "Nope", "field": "email"}}, cols)
      and R.problem(cols[3], cols) == "" and R.problem(cols[4], cols) == "")

# ---- which rows (the same answers as the grid gives before you press Run)
rows = mkrows()
op = cols[3]
check("empty mode: empty cells that have something to read; a row with nothing in Company or City is skipped and counted", [r["id"] for r in R.pick_rows(rows, op, cols, "empty")["rows"]] == ["r1", "r4", "r5"] and R.pick_rows(rows, op, cols, "empty")["skipped"] == 1)
check("force mode includes rows already filled; only the first N", [r["id"] for r in R.pick_rows(rows, op, cols, "all")["rows"]] == ["r1", "r2", "r4", "r5"] and [r["id"] for r in R.pick_rows(rows, op, cols, "empty", 2)["rows"]] == ["r1", "r4"])
check("a website run reads only the website column", [r["id"] for r in R.pick_rows(rows, cols[4], cols, "empty")["rows"]] == ["r1", "r2", "r5"])

# ---- turning an answer into a cell
c = {c["label"]: c for c in cols}
check("text answers lose quotes and stray spaces; UNKNOWN and empty are no answer", R.coerce(c["Company"], '  "Acme  Ltd"  ') == "Acme Ltd" and R.coerce(c["Company"], "UNKNOWN") is None and R.coerce(c["Company"], "unknown") is None and R.coerce(c["Company"], "  ") is None)
check("numbers: symbols stripped, whole numbers stay whole; words are left out", R.coerce(c["Score"], "$1,200") == 1200 and R.coerce(c["Score"], "7.5") == 7.5 and R.coerce(c["Score"], "high") is None)
check("dates must be real ISO dates", R.coerce(c["When"], "2026-11-18") == "2026-11-18" and R.coerce(c["When"], "2026-02-31") is None and R.coerce(c["When"], "next week") is None)
check("yes/no: Yes ticks the box, No leaves it empty, anything else is left out", R.coerce(c["VIP"], "Yes") is True and R.coerce(c["VIP"], "no") is None and R.coerce(c["VIP"], "maybe") is None)
check("a choice must be one of the column's choices (by label or value); the stored value is the choice's value", R.coerce(c["Status"], "hot") == "hot" and R.coerce(c["Status"], "COLD") == "cold" and R.coerce(c["Status"], "warm") is None)
check("an email must look like one (lower case); a phone must look like one; a link without a scheme gets https", R.coerce(c["Email found"], "Sam@Acme.com") == "sam@acme.com" and R.coerce(c["Email found"], "no email here") is None and R.coerce({"type": "phone", "options": []}, "+44 20 7946 0958") == "+44 20 7946 0958" and R.coerce({"type": "phone", "options": []}, "call me") is None and R.coerce(c["Website"], "acme.com") == "https://acme.com" and R.coerce(c["Website"], "two words") is None)
check("long text is cut to 2,000 characters, text to 500", len(R.coerce(c["Opener"], "x" * 5000)) == 2000 and len(R.coerce(c["Company"], "x" * 900)) == 500)
check("the website facts come out of what the site reader found, and an empty finding is empty", R.site_value({"emails": [{"email": "a@x.com", "kind": "personal"}], "phones": ["555 1234"], "people": [{"name": "Ann Lee", "title": "Owner"}], "socials": {"instagram": "https://instagram.com/x"}, "tech": ["Wix", "Stripe"], "booking": "Calendly"}, "email") == "a@x.com" and R.site_value({"people": [{"name": "Ann Lee", "title": "Owner"}]}, "decision_maker") == "Ann Lee" and R.site_value({"people": [{"name": "Ann Lee", "title": "Owner"}]}, "decision_title") == "Owner" and R.site_value({"socials": {"instagram": "i"}}, "instagram") == "i" and R.site_value({"tech": ["Wix", "Stripe"]}, "tech") == "Wix, Stripe" and R.site_value({}, "email") == "" and R.site_value({}, "phone") == "")


# ---- a whole run: ask Claude
api = Api(mkrows())
asked = []
out, lines = run(api, ask=lambda p, t: (asked.append((p, t)) or "Hello " + p.split()[-1], 20, 8, "claude-haiku-5-5"))
check("every picked row is asked with its own cells in the question, using the setting's model", [a[0] for a in asked] == ["Write a one-line opener for Acme in Leeds", "Write a one-line opener for  in York", "Write a one-line opener for Zed in "] and {a[1] for a in asked} == {"haiku"})
check("answers are written only into the Opener column of the picked rows, in the batch call, and nothing else is touched", set(api.saved) == {"r1", "r4", "r5"} and all(list(v) == ["c_opener"] for v in api.saved.values()) and not any(n == "hq_grid_push" for n, _ in api.calls))
check("it ends with a FINISHED line and PROGRESS lines Citadel can read", "FINISHED 3 filled, 0 failed, 1 skipped, 0 no answer" in out and any(l == "PROGRESS 3/3 failed 0 skipped 1" for l in lines))
check("tokens are counted against the daily limit, once per answer, with the real model", len(run.__globals__["Cost"](None).recorded) == 0)
cost = Cost()
api = Api(mkrows())
run(api, cost=cost)
check("each answer is recorded in the token tally", len(cost.recorded) == 3 and cost.recorded[0] == ("claude-haiku-5-5", 10, 5))

# force mode replaces what is there
api = Api(mkrows())
out, _ = run(api, mode="all")
check("force mode asks the filled row too and replaces its value", set(api.saved) == {"r1", "r2", "r4", "r5"} and "FINISHED 4 filled" in out)

# limit
api = Api(mkrows())
run(api, limit=1)
check("a limit takes only the first N picked rows", set(api.saved) == {"r1"})

# dry run
api = Api(mkrows())
out, lines = run(api, dry=True, ask=lambda p, t: (_ for _ in ()).throw(AssertionError("asked during a dry run")))
check("a dry run asks nothing and saves nothing, and says so", "Dry run" in out and not api.saved and not any(n == "hq_grid_set_cells" for n, _ in api.calls))

# unknown / misfit / failures
api = Api(mkrows())
out, _ = run(api, ask=lambda p, t: ("UNKNOWN", 5, 1, "m"))
check("UNKNOWN leaves the cell as it was and is counted as no answer", not api.saved and "0 filled" in out and "3 no answer" in out)
api = Api(mkrows())
out, _ = run(api, col="Email found", site=lambda w: {"emails": [{"email": "info@" + w.split(".")[0] + ".com"}]})
check("a website run fills the email from each row's own website, one lookup per website", set(api.saved) == {"r1", "r2", "r5"} and api.saved["r1"] == {"c_found": "info@acme.com"} and "FINISHED 3 filled" in out)
seen = []
api = Api([{"id": "a", "data": {"c_website": "same.com"}}, {"id": "b", "data": {"c_website": "same.com"}}])
run(api, col="Email found", site=lambda w: seen.append(w) or {"emails": [{"email": "x@same.com"}]})
check("the same website is read once per run", seen == ["same.com"] and set(api.saved) == {"a", "b"})
api = Api(mkrows())
n = {"i": 0}


def flaky(p, t):
    n["i"] += 1
    if n["i"] == 2:
        raise RuntimeError("rate limited")
    return ("ok", 1, 1, "m")


out, _ = run(api, ask=flaky)
check("one row failing is counted and the others still go through", "FINISHED 2 filled, 1 failed" in out and set(api.saved) == {"r1", "r5"})
api = Api([{"id": f"f{i}", "data": {"c_company": f"Co{i}"}} for i in range(9)])
calls = {"n": 0}
out, _ = run(api, ask=lambda p, t: (calls.__setitem__("n", calls["n"] + 1) or (_ for _ in ()).throw(RuntimeError("Claude says: credit balance is too low"))))
check("a run of failures in a row stops with the last reason, instead of trying every row", "STOPPED" in out and "credit balance" in out and calls["n"] == 5 and "5 failed" in out, out)
api = Api(mkrows())
cost = Cost(limit_after=1)
out, _ = run(api, cost=cost)
check("when the daily token limit is reached mid-run it stops, keeps what is done and says how to raise it", "STOPPED" in out and "claude limit" in out and set(api.saved) == {"r1"})
try:
    run(Api(mkrows()), cost=Cost(limit_after=0))
    check("a run that starts already over the limit refuses", False)
except RuntimeError as e:
    check("a run that starts already over the limit refuses", "claude limit" in str(e))
try:
    R.run("Leads", "Opener", "empty", 0, False, say=print, api=Api(mkrows()), ask=lambda p, t: ("x", 1, 1, "m"), cost=Cost(), key_present=lambda: "")
    check("without a Claude key an ask-Claude run refuses with how to connect it", False)
except RuntimeError as e:
    check("without a Claude key an ask-Claude run refuses with how to connect it", "claude setup" in str(e))

# saving: a refused batch is retried row by row
api = Api(mkrows(), save_fails=1)
out, _ = run(api)
check("a refused batch is saved one row at a time, so one bad row loses only itself", set(api.saved) == {"r1", "r4", "r5"} and "FINISHED 3 filled" in out)
many = [{"id": f"x{i}", "data": {"c_company": f"Co{i}"}} for i in range(25)]
api = Api(many)
run(api, ask=lambda p, t: ("v", 1, 1, "m"))
saves = [b for n_, b in api.calls if n_ == "hq_grid_set_cells"]
check("answers are saved in batches of 10 as it goes (a Stop keeps what is done)", [len(b["p_updates"]) for b in saves] == [10, 10, 5])
big = [{"id": f"y{i}", "data": {"c_company": "c"}} for i in range(1200)]
api = Api(big)
R.read_rows(api, GRID["id"])
check("rows are read 500 at a time until the grid ends", [b["p_offset"] for n_, b in api.calls if n_ == "hq_grid_rows"] == [0, 500, 1000])

# ---- the real Claude call, with a fake connection
sent = {}


def http_ok(url, headers, data):
    sent.update(url=url, headers=headers, body=json.loads(data))
    return 200, json.dumps({"model": "claude-haiku-5-5", "content": [{"type": "text", "text": " Hello Acme "}], "usage": {"input_tokens": 31, "output_tokens": 4}})


t, tin, tout, model = R.ask_claude("Say hi to Acme", "haiku", key="sk-ant-secretkey1234567890", http=http_ok)
check("one question goes to Anthropic with the PC's own key in a header, the short system instruction, and the chosen model; the answer and token counts come back", t == "Hello Acme" and (tin, tout) == (31, 4) and sent["url"] == "https://api.anthropic.com/v1/messages" and sent["headers"]["x-api-key"] == "sk-ant-secretkey1234567890" and sent["body"]["model"] == "claude-haiku-5-5" and "ONLY the value" in sent["body"]["system"] and sent["body"]["messages"][0]["content"] == "Say hi to Acme")
R.ask_claude("q", "sonnet", key="sk-ant-abcdefghijklmnopqrstuvw", http=http_ok)
check("the stronger model is used only when the column says so", sent["body"]["model"] == "claude-sonnet-5-5")
try:
    R.ask_claude("q", "haiku", key="sk-ant-secretkey1234567890", http=lambda u, h, d: (401, json.dumps({"error": {"message": "invalid x-api-key sk-ant-secretkey1234567890"}})))
    check("a refusal is raised in plain words and never shows the key", False)
except RuntimeError as e:
    check("a refusal is raised in plain words and never shows the key", "Claude says" in str(e) and "sk-ant-secretkey1234567890" not in str(e))

# ---- the tool and the command
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.grid_run"]
check("the catalog has the tool with the grid, column, mode and limit, and the args that run `grid run`", [f["name"] for f in t["fields"]] == ["grid", "column", "mode", "limit"] and t["args"][:3] == [{"lit": "grid"}, {"lit": "run"}, {"field": "grid"}] and any(f["type"] == "choice" and [c["value"] for c in f["choices"]] == ["empty", "all"] for f in t["fields"]) and t["timeout_min"] >= 120)
check("the tool says it uses your own Claude key, writes only that column of your own grid, and that Stop keeps what is done", "own Claude key" in t["help"] and "only into that one column" in t["help"] and "Stop keeps what is done" in t["help"])
src = {n: (ROOT / n).read_text(encoding="utf-8") for n in ("dse/gridpush.py", "dse/gridrun.py", "bridge/add_gridrun_tool.py")}
check("`python dse.py grid run` reaches the module through the grid command", 'argv[0] == "run"' in src["dse/gridpush.py"] and "gridrun.cli(argv[1:])" in src["dse/gridpush.py"])
check("the key is never printed or logged by this module", "print(key" not in src["dse/gridrun.py"] and "say(key" not in src["dse/gridrun.py"] and ".replace(key" in src["dse/gridrun.py"])
check("no em dash", DASH not in src["dse/gridrun.py"] + src["bridge/add_gridrun_tool.py"] + Path(__file__).read_text(encoding="utf-8").replace("chr(0x2014)", ""))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
