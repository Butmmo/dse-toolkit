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
        self.fps = {}

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
                vals = {k: v for k, v in u["cells"].items() if not k.startswith("_")}
                if vals:
                    self.saved.setdefault(u["id"], {}).update(vals)                 # the values written into the column
                self.fps.setdefault(u["id"], {}).update({k: v for k, v in u["cells"].items() if k.startswith("_")})   # the fingerprints left on rows
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

# ---- sources in order (a waterfall)
S_SITE = {"kind": "site", "from": "Website", "field": "email"}
S_AI = {"kind": "ai", "prompt": "Guess the best email for {Company}", "model": "haiku"}
WF = {**S_SITE, "then": [S_AI]}
wf_grid = {**GRID, "doc": doc(run_site=WF)}


def wf_api(rows):
    return Api(rows, grid=wf_grid)


wf_rows = [{"id": "w1", "data": {"c_website": "acme.com", "c_company": "Acme"}},
           {"id": "w2", "data": {"c_website": "bright.co.uk", "c_company": "Bright"}},
           {"id": "w3", "data": {"c_company": "Cee Ltd"}},
           {"id": "w4", "data": {}}]
check("a setting with several sources: the first is the setting, the others follow, junk is dropped, at most four more, a nested chain is ignored", (lambda a, many: [s["kind"] for s in R.steps_of(a)] == ["site", "ai", "ai"] and len(R.steps_of(many)) == 5 and R.steps_of(a)[2].get("then") is None and R.clean_run({**S_SITE, "then": "no"}).get("then") is None and R.clean_run({"kind": "x", "then": [S_SITE]}) is None and R.steps_of(None) == [])(
    R.clean_run({**S_SITE, "then": [S_AI, {"kind": "x"}, {"kind": "ai", "prompt": " "}, {**S_AI, "then": [S_SITE]}]}), R.clean_run({**S_SITE, "then": [S_AI] * 9})))
wcols = R.parse_columns(wf_grid["doc"])
wcol = [c for c in wcols if c["label"] == "Email found"][0]
check("a source that cannot work is named by its place when there are several (and plainly when there is one)", R.problem(wcol, wcols) == "" and R.problem({**wcol, "run": {**S_SITE, "then": [{**S_AI, "prompt": "x {Nope}"}]}}, wcols).startswith("Source 2: The question uses a column the grid does not have") and R.problem({**wcol, "run": {**S_SITE, "from": "Nope"}}, wcols).startswith("The website column"))
check("a row can run when ANY source has something to read", R.has_inputs(WF, wcols, {"c_website": "a.com"}) and R.has_inputs(WF, wcols, {"c_company": "X"}) and not R.has_inputs(WF, wcols, {"c_city": "York"}))
api = wf_api(wf_rows)
asked = []
fetched = []
out, lines = run(api, col="Email found", ask=lambda p, t: (asked.append(p) or "info@" + p.split()[-1].lower() + ".com", 5, 2, "claude-haiku-5-5"), site=lambda w: fetched.append(w) or ({"emails": [{"email": "hi@acme.com"}]} if w == "acme.com" else {}))
check("the free source is tried first and Claude is only asked for rows it found nothing for", asked == ["Guess the best email for Bright", "Guess the best email for Cee Ltd"] and fetched == ["acme.com", "bright.co.uk"])
check("each row gets the answer of the first source that gave one, and the row with nothing to read is skipped", api.saved == {"w1": {"c_found": "hi@acme.com"}, "w2": {"c_found": "info@bright.com"}, "w3": {"c_found": "info@ltd.com"}} and "1 skipped" in out)
check("the end line says how many each source supplied", "FINISHED 3 filled, 0 failed, 1 skipped, 0 no answer, by source: 1st 1, 2nd 2" in out, out)
api = wf_api(wf_rows[:1])
run(api, col="Email found", ask=lambda p, t: (_ for _ in ()).throw(AssertionError("asked although the website answered")), site=lambda w: {"emails": [{"email": "hi@acme.com"}]})
check("a paid source is never asked when an earlier source answered", api.saved == {"w1": {"c_found": "hi@acme.com"}})
api = wf_api([wf_rows[1]])
out, _ = run(api, col="Email found", ask=lambda p, t: ("no idea", 1, 1, "m"), site=lambda w: {})
check("an answer that does not fit the column type is not stored, and the row is counted as not fitting", not api.saved and "did not fit the column type" in out)
chain = {"kind": "ai", "prompt": "Guess the email for {Company}", "model": "haiku", "then": [S_SITE]}
api = Api([{"id": "m1", "data": {"c_company": "Bright", "c_website": "bright.co.uk"}}], grid={**GRID, "doc": doc(run_site=chain)})
out, _ = run(api, col="Email found", ask=lambda p, t: ("not an email", 1, 1, "m"), site=lambda w: {"emails": [{"email": "found@bright.co.uk"}]})
check("when the first source's answer does not fit, the next source is tried", api.saved == {"m1": {"c_found": "found@bright.co.uk"}} and "by source: 1st 0, 2nd 1" in out)
api = Api([{"id": "e1", "data": {"c_company": "Bright", "c_website": "bright.co.uk"}}], grid={**GRID, "doc": doc(run_site={**S_SITE, "then": [S_AI]})})
out, _ = run(api, col="Email found", ask=lambda p, t: ("ok@bright.co.uk", 1, 1, "m"), site=lambda w: (_ for _ in ()).throw(RuntimeError("timed out")))
check("a source that fails does not fail the row: the next source is still tried", api.saved == {"e1": {"c_found": "ok@bright.co.uk"}} and "0 failed" in out)
api = Api([{"id": f"f{i}", "data": {"c_company": f"Co{i}", "c_website": f"s{i}.com"}} for i in range(9)], grid=wf_grid)
calls = {"n": 0}
out, _ = run(api, col="Email found", ask=lambda p, t: (_ for _ in ()).throw(RuntimeError("credit balance is too low")), site=lambda w: calls.__setitem__("n", calls["n"] + 1) or (_ for _ in ()).throw(RuntimeError("offline")))
check("a row where every source failed is a failed row, and five in a row stop the run with the last reason", "STOPPED" in out and "5 failed" in out and calls["n"] == 5, out)
seen = []
two_site = {**S_SITE, "then": [{"kind": "site", "from": "Website", "field": "phone"}]}
api = Api([{"id": "s1", "data": {"c_website": "same.com"}}], grid={**GRID, "doc": doc(run_site=two_site)})
run(api, col="Email found", site=lambda w: seen.append(w) or {"phones": ["555 1234"]})
check("two website sources on one row read the website once", seen == ["same.com"] and not api.saved)
api = wf_api([wf_rows[0], wf_rows[2]])
cost = Cost(limit_after=0)
out, _ = run(api, col="Email found", cost=cost, site=lambda w: {"emails": [{"email": "hi@acme.com"}]}, ask=lambda p, t: (_ for _ in ()).throw(AssertionError("asked over the limit")))
check("with a free source first, a run over the Claude limit still fills what the website answers, then stops with how to raise it at the first row that needs Claude", api.saved == {"w1": {"c_found": "hi@acme.com"}} and "STOPPED" in out and "claude limit" in out, out)
run_src = (ROOT / "dse" / "gridrun.py").read_text(encoding="utf-8")
check("the module says several sources are tried in order and the first answer wins", "SEVERAL sources" in run_src and "MAX_STEPS = 5" in run_src)

# ---- out-of-date rows (fingerprints)
check("the hash is FNV-1a 32 of the UTF-8 bytes: the published test values, an empty text and a non-ASCII text", R.fnv1a32("hello") == "4f9f2cab" and R.fnv1a32("") == "811c9dc5" and R.fnv1a32("Ünï€") == "1fcb8fc2")
fpc = [{"key": "c_company", "label": "Company", "type": "text", "options": [], "run": None}, {"key": "c_website", "label": "Website", "type": "url", "options": [], "run": None},
       {"key": "c_city", "label": "City", "type": "text", "options": [], "run": None}, {"key": "c_opener", "label": "Opener", "type": "longtext", "options": [], "run": R.clean_run(AI)}]
fp_wf = {**fpc[3], "run": R.clean_run({"kind": "site", "from": "Website", "field": "email", "then": [{"kind": "ai", "prompt": "Guess the best email for {Company}", "model": "sonnet"}]})}
check("THE SHARED TEST VALUES: these exact fingerprints are also asserted in Citadel's tests (src/lib/crm-run.ts), so the two always agree", R.fingerprint(fpc[3], fpc, {"c_company": "Acme", "c_city": "Leeds"}) == "faa98a36" and R.fingerprint(fp_wf, fpc, {"c_website": "  acme.com ", "c_company": "Ünïcode Ltd", "c_city": "x"}) == "e92d2c24" and R.fingerprint(fp_wf, fpc, {}) == "0404fcdf")
check("the fingerprint changes when a cell the sources read changes, when the question changes, when the order of sources changes, and not for an unrelated cell or stray spaces", (lambda base: base != R.fingerprint(fpc[3], fpc, {"c_company": "Acme Ltd", "c_city": "Leeds"}) and base != R.fingerprint({**fpc[3], "run": R.clean_run({**AI, "prompt": AI["prompt"] + "!"})}, fpc, {"c_company": "Acme", "c_city": "Leeds"})
      and base == R.fingerprint(fpc[3], fpc, {"c_company": "Acme", "c_city": "Leeds", "c_website": "x.com"}) and base == R.fingerprint(fpc[3], fpc, {"c_company": "  Acme ", "c_city": "Leeds"})
      and R.fingerprint(fp_wf, fpc, {}) != R.fingerprint({**fp_wf, "run": {**R.steps_of(fp_wf["run"])[1], "then": [R.steps_of(fp_wf["run"])[0]]}}, fpc, {}))(R.fingerprint(fpc[3], fpc, {"c_company": "Acme", "c_city": "Leeds"})))
check("a prompt with runs of blank lines is cleaned the same way as the grid cleans it (so the hash agrees)", R.clean_run({"kind": "ai", "prompt": "a  {Company}" + chr(10) * 4 + "b", "model": "haiku"})["prompt"] == "a {Company}" + chr(10) * 2 + "b")
sc = {"key": "c_found", "label": "Email found", "type": "email", "options": [], "run": R.clean_run(S_SITE)}
scols = [{"key": "c_website", "label": "Website", "type": "url", "options": [], "run": None}, sc]
fpn = lambda d: R.fingerprint(sc, scols, d)  # noqa: E731
srows = [{"id": "s1", "data": {"c_website": "a.com", "c_found": "x@a.com", "_c_found": fpn({"c_website": "a.com"})}},          # filled by a run, inputs unchanged
         {"id": "s2", "data": {"c_website": "b.com", "c_found": "x@old.com", "_c_found": fpn({"c_website": "old.com"})}},       # filled by a run, website since changed
         {"id": "s3", "data": {"c_website": "c.com", "c_found": "typed@by.hand"}},                                              # typed by hand: no fingerprint
         {"id": "s4", "data": {"c_website": "d.com"}},                                                                          # never run, empty
         {"id": "s5", "data": {"c_website": "e.com", "_c_found": fpn({"c_website": "e.com"})}},                                 # tried, no answer, inputs unchanged
         {"id": "s6", "data": {"c_website": "f.com", "_c_found": fpn({"c_website": "old.com"})}}]                               # tried, no answer, website since changed
pk = R.pick_rows(srows, sc, scols, "stale")
check("stale mode picks rows never run and still empty, plus rows whose fingerprint no longer matches; never a hand-typed value, never a row tried with unchanged inputs", [r["id"] for r in pk["rows"]] == ["s2", "s4", "s6"] and pk["outdated"] == 2, str([r["id"] for r in pk["rows"]]))
check("empty mode still means just empty cells (a tried row with an empty cell counts), and force mode everything with something to read", [r["id"] for r in R.pick_rows(srows, sc, scols, "empty")["rows"]] == ["s4", "s5", "s6"] and len(R.pick_rows(srows, sc, scols, "all")["rows"]) == 6)
api = Api(srows, grid={**GRID, "doc": doc(run_site=S_SITE)})
out, lines = run(api, col="Email found", mode="stale", site=lambda w: {"emails": [{"email": "new@" + w}]} if w in ("b.com", "d.com") else {})
check("a stale run fills only the picked rows, leaves the hand-typed value and the untouched row alone", set(api.saved) == {"s2", "s4"} and api.saved["s2"] == {"c_found": "new@b.com"} and "s3" not in api.fps and "s1" not in api.fps)
check("every row a run fills carries a fingerprint, and a row tried with no answer gets one too (so it is not asked again), written under _<column key>", api.fps["s2"] == {"_c_found": fpn({"c_website": "b.com"})} and api.fps["s6"] == {"_c_found": fpn({"c_website": "f.com"})} and set(api.fps) == {"s2", "s4", "s6"})
rows2 = [{"id": r["id"], "data": {**r["data"], **api.saved.get(r["id"], {}), **api.fps.get(r["id"], {})}} for r in srows]
check("running stale again straight away finds nothing to do", R.pick_rows(rows2, sc, scols, "stale")["rows"] == [] and "Nothing to run" in run(Api(rows2, grid={**GRID, "doc": doc(run_site=S_SITE)}), col="Email found", mode="stale", site=lambda w: {})[0])
rows3 = [{**r, "data": {**r["data"], "c_website": "changed.com"}} if r["id"] == "s2" else r for r in rows2]
check("changing a cell a source reads makes just that row out of date again", [r["id"] for r in R.pick_rows(rows3, sc, scols, "stale")["rows"]] == ["s2"])
api = Api([{"id": "q1", "data": {"c_website": "x.com"}}], grid={**GRID, "doc": doc(run_site=S_SITE)})
out, _ = run(api, col="Email found", mode="stale", site=lambda w: (_ for _ in ()).throw(RuntimeError("timed out")))
check("a row where the source failed gets no fingerprint, so it is simply tried again next time", not api.fps and not api.saved)
out, _ = run(Api(srows, grid={**GRID, "doc": doc(run_site=S_SITE)}), col="Email found", mode="stale", dry=True)
check("a dry stale run says how many rows are out of date and saves nothing", "empty or out-of-date rows" in out and "2 out of date" in out and "Dry run" in out)
try:
    R.run("Leads", "Email found", "sometimes", 0, False, say=print, api=Api(srows), key_present=lambda: "k")
    check("an unknown mode is refused", False)
except ValueError as e:
    check("an unknown mode is refused", "empty, stale or all" in str(e))
check("the command takes the stale mode", '"stale"' in (ROOT / "dse" / "gridrun.py").read_text(encoding="utf-8").split("def cli")[1])

# ---- which AI answers (the member's model choice, 28 Nov 2026)
check("the model stored on a source is cleaned like the grid cleans it: menu values pass, legacy values keep their meaning, anything else becomes haiku",
      R.clean_model("haiku") == "haiku" and R.clean_model("sonnet") == "sonnet" and R.clean_model("auto") == "auto" and R.clean_model("claude") == "claude"
      and R.clean_model("claude:haiku") == "claude:haiku" and R.clean_model("claude:opus") == "claude:opus" and R.clean_model("ollama:gemma3:4b") == "ollama:gemma3:4b"
      and R.clean_model("ollama:") == "haiku" and R.clean_model("gpt") == "haiku" and R.clean_model("") == "haiku" and R.clean_model(None) == "haiku")
check("a source can carry a local model or a Claude tier through the cleaner",
      R.clean_step({"kind": "ai", "prompt": "q {A}", "model": "ollama:llama3.1:8b"})["model"] == "ollama:llama3.1:8b"
      and R.clean_step({"kind": "ai", "prompt": "q {A}", "model": "claude:opus"})["model"] == "claude:opus")
check("only Claude choices count as Claude (they use the key and the daily limit)",
      R.is_claude_model("haiku") and R.is_claude_model("claude:opus") and R.is_claude_model("claude") and not R.is_claude_model("ollama:gemma3:4b") and not R.is_claude_model("auto"))


def fake_ollama_http(url, data):
    body = json.loads(data)
    assert body["model"] == "gemma3:4b" and body["messages"][0]["content"] == "q?"
    return 200, json.dumps({"message": {"content": " a value "}, "prompt_eval_count": 11, "eval_count": 7})


check("a local model is asked through Ollama with the same one-cell instruction, and its answer is trimmed",
      R.ask_ollama("q?", "gemma3:4b", http=fake_ollama_http) == ("a value", 11, 7, "gemma3:4b"))
check("when Ollama refuses, the reason is plain",
      "Ollama says" in str(_try(lambda: R.ask_ollama("q?", "nope", http=lambda u, d: (404, json.dumps({"error": "model 'nope' not found"}))))))
check("ask_any sends a local choice to Ollama and a Claude tier to Claude",
      R.ask_any("q?", "ollama:gemma3:4b", ollama_http=fake_ollama_http)[0] == "a value"
      and R.ask_any("q?", "claude:opus", key="sk-test", http=lambda u, h, d: (200, json.dumps({"content": [{"type": "text", "text": "opus answer"}], "usage": {"input_tokens": 3, "output_tokens": 2}, "model": "claude-opus-5-5"}))) == ("opus answer", 3, 2, "claude-opus-5-5"))
check("Automatic resolves to Claude Haiku when a key is connected, and to a local model when none is",
      R.resolve_model({"model": "auto"}, key_present=lambda: "sk-test") == "claude:haiku"
      and R.resolve_model({"model": "auto"}, key_present=lambda: "").startswith("ollama:")
      and R.resolve_model({"model": "ollama:gemma3:4b"}, key_present=lambda: "") == "ollama:gemma3:4b")

ogrid = dict(GRID)
ogrid["doc"] = doc(run_ai={"kind": "ai", "prompt": "Write a one-line opener for {Company} in {City}", "model": "ollama:gemma3:4b"})
seen_models = []
ocost = Cost()
try:
    out_o = R.run("Leads", "Opener", "empty", 0, False, say=lambda m: None, api=Api(mkrows(), grid=ogrid),
                  ask=lambda p, m: (seen_models.append(m), ("Local opener", 0, 0, m))[1], cost=ocost, key_present=lambda: "")
except Exception as e:  # noqa: BLE001
    out_o = f"RAISED {e}"
check("a local-model run fills the column with no Claude key connected, asks the local model, and records no Claude tokens",
      isinstance(out_o, str) and "FINISHED" in out_o and len(seen_models) >= 1 and all(m == "ollama:gemma3:4b" for m in seen_models) and ocost.recorded == [], str(out_o))


# ---- ChatGPT and Gemini sources: the member's own key for that provider, in the Claude pattern
check("ChatGPT and Gemini model choices survive cleaning, are not Claude models, and name their provider",
      R.clean_model("openai") == "openai" and R.clean_model("openai:full") == "openai:full" and R.clean_model("gemini:pro") == "gemini:pro"
      and R.clean_model("gemini:flash") == "gemini:flash" and not R.is_claude_model("openai:full") and not R.is_claude_model("gemini")
      and R.provider_of("openai:mini") == "openai" and R.provider_of("gemini") == "gemini" and R.provider_of("claude:opus") == "" and R.provider_of("ollama:gemma3:4b") == "")
osent = {}
def oai_http(url, headers, data):
    osent.update(url=url, headers=headers, body=json.loads(data))
    return 200, json.dumps({"choices": [{"message": {"content": "gpt answer"}}], "usage": {"prompt_tokens": 21, "completion_tokens": 5}, "model": "gpt-5"})
t, tin, tout, model = R.ask_openai("Fill this for Acme", "openai:full", key="sk-test-openai", http=oai_http)
check("one question goes to OpenAI with the PC's own key in the header, the short system instruction and the picked model; the answer and token counts come back",
      t == "gpt answer" and (tin, tout) == (21, 5) and model == "gpt-5" and osent["url"] == "https://api.openai.com/v1/chat/completions"
      and osent["headers"]["Authorization"] == "Bearer sk-test-openai" and osent["body"]["model"] == "gpt-5" and "ONLY the value" in osent["body"]["messages"][0]["content"])
gsent = {}
def gem_http(url, headers, data):
    gsent.update(url=url, headers=headers, body=json.loads(data))
    return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "gemini answer"}]}}], "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 3}})
t, tin, tout, model = R.ask_gemini("Fill this for Acme", "gemini:pro", key="AIza-test", http=gem_http)
check("one question goes to Gemini with the PC's own key in the header and the picked model in the address; the answer and token counts come back",
      t == "gemini answer" and (tin, tout) == (17, 3) and model == "gemini-2.5-pro" and "gemini-2.5-pro" in gsent["url"]
      and gsent["headers"]["x-goog-api-key"] == "AIza-test" and "ONLY the value" in gsent["body"]["systemInstruction"]["parts"][0]["text"])
check("ask_any sends a ChatGPT choice to OpenAI and a Gemini choice to Google",
      R.ask_any("q?", "openai:mini", key="sk-test-openai", http=oai_http)[0] == "gpt answer"
      and R.ask_any("q?", "gemini:flash", key="AIza-test", http=gem_http)[0] == "gemini answer")
_orig_oai, _orig_gem = R.openai_key, R.gemini_key
R.openai_key, R.gemini_key = (lambda: ""), (lambda: "")
check("without the provider's key the ask refuses with how to connect it",
      "openai setup" in str(_try(lambda: R.ask_openai("q?", "openai", http=oai_http))) and "gemini setup" in str(_try(lambda: R.ask_gemini("q?", "gemini", http=gem_http))))
R.openai_key, R.gemini_key = _orig_oai, _orig_gem


# ---- the tool and the command
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.grid_run"]
check("the catalog has the tool with the grid, column, mode and limit, and the args that run `grid run`", [f["name"] for f in t["fields"]] == ["grid", "column", "mode", "limit"] and t["args"][:3] == [{"lit": "grid"}, {"lit": "run"}, {"field": "grid"}] and any(f["type"] == "choice" and [c["value"] for c in f["choices"]] == ["empty", "stale", "all"] for f in t["fields"]) and t["timeout_min"] >= 120)
check("the tool says it uses your own Claude key, writes only that column of your own grid, and that Stop keeps what is done", "own Claude key" in t["help"] and "only into that one column" in t["help"] and "Stop keeps what is done" in t["help"])
src = {n: (ROOT / n).read_text(encoding="utf-8") for n in ("dse/gridpush.py", "dse/gridrun.py", "bridge/add_gridrun_tool.py")}
check("`python dse.py grid run` reaches the module through the grid command", 'argv[0] == "run"' in src["dse/gridpush.py"] and "gridrun.cli(argv[1:])" in src["dse/gridpush.py"])
check("the key is never printed or logged by this module", "print(key" not in src["dse/gridrun.py"] and "say(key" not in src["dse/gridrun.py"] and ".replace(key" in src["dse/gridrun.py"])
check("no em dash", DASH not in src["dse/gridrun.py"] + src["bridge/add_gridrun_tool.py"] + Path(__file__).read_text(encoding="utf-8").replace("chr(0x2014)", ""))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
