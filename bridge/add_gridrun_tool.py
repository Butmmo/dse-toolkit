"""One-off generator: adds the Run column tool to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.grid_run", None)

T["dse.grid_run"] = {
    "label": "Grids: run a column (ask Claude, or read a website, for each row)", "group": "Grow",
    "help": "Fills one column of a grid of your Ledgers, row by row, on this PC. You normally press Run column in Citadel (the column menu of a grid): this is the tool behind it. The column's run setting says what it does: "
            "ask Claude a question about each row (uses your own Claude key and counts toward your daily token limit), or read one fact (best email, phone, decision maker, a social link ...) from the business's own public website (free). "
            "A column can have several sources tried in order for each row (for example the free website reading first, then Claude only for the rows it found nothing for): the first answer that fits wins. "
            "A run leaves a small fingerprint on each row it fills or tries, so 'Empty or out-of-date rows' re-runs only rows whose inputs or sources changed (values typed by hand are never touched). "
            "It works on empty rows unless you ask for another mode, and 'first N rows' lets you test on a few before running them all. Answers are saved in small batches, so Stop keeps what is done. "
            "It writes only into that one column of your own grid, through this PC's own connection to your account.",
    "script": "dse.py", "args": [{"lit": "grid"}, {"lit": "run"}, {"field": "grid"}, {"field": "column"}, {"opt": "--mode", "field": "mode"}, {"opt": "--limit", "field": "limit"}],
    "fields": [
        {"name": "grid", "label": "Grid (its id, its name, or Ledger/grid name)", "type": "text", "required": True, "max": 120},
        {"name": "column", "label": "Column (its name or key)", "type": "text", "required": True, "max": 60},
        {"name": "mode", "label": "Which rows", "type": "choice", "required": False, "default": "empty",
         "choices": [{"value": "empty", "label": "Empty rows only"}, {"value": "stale", "label": "Empty or out-of-date rows (inputs or sources changed since the last run)"}, {"value": "all", "label": "Every row (replaces what is there)"}]},
        {"name": "limit", "label": "Only the first N rows (empty = all of them)", "type": "int", "required": False, "min": 1, "max": 5000},
    ],
    "timeout_min": 240, "outputs": []}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("grid_run tool added; tools:", len(T))
