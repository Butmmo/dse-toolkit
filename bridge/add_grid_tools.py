"""One-off generator: adds the HQ Tools -> grid tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.grid_push", "dse.grid_list"):
    T.pop(k, None)

NEVER = "It changes only the grid you name, in your own Ledger, through this PC's own connection to your account. The file is never changed."
T["dse.grid_push"] = {
    "label": "Grids: send a list or a tool's result into a grid", "group": "Grow",
    "help": "Takes a CSV from your lists (for example the result of Lead enrichment) and adds its rows to a grid of one of your Ledgers. Headers are matched to the grid's columns by name (Website = URL = Domain, Email = Work email ...); a header the grid does not have becomes a new column unless you tick the box that stops that. "
            "With a key (the Email column unless you pick another) a lead is added once: sending it again fills empty cells and keeps what you typed, unless you tick Replace. Tick Dry run first to see exactly what would happen. Workflows of that Ledger start for the rows it adds. " + NEVER,
    "script": "dse.py", "args": [{"lit": "grid"}, {"lit": "push"}, {"field": "csv"}, {"field": "grid"}, {"opt": "--key", "field": "key"}, {"opt": "--only", "field": "only"}, {"flag": "--no-new-columns", "field": "no_new"}, {"flag": "--overwrite", "field": "overwrite"}, {"flag": "--dry", "field": "dry"}],
    "fields": [
        {"name": "csv", "label": "List (a CSV)", "type": "file", "required": True, "glob": "my-lists/*.csv"},
        {"name": "grid", "label": "Grid (its name, or Ledger/grid name)", "type": "text", "required": True, "max": 120},
        {"name": "key", "label": "Key column: the same value means the same lead (empty = Email)", "type": "text", "required": False, "max": 60},
        {"name": "only", "label": "Only these headers (comma separated, empty = all)", "type": "text", "required": False, "max": 400},
        {"name": "no_new", "label": "Do not make new columns for headers the grid does not have", "type": "bool", "default": False},
        {"name": "overwrite", "label": "Replace cells that already have a value (otherwise only empty cells are filled)", "type": "bool", "default": False},
        {"name": "dry", "label": "Dry run: show what would happen and send nothing", "type": "bool", "default": False},
    ],
    "timeout_min": 10, "outputs": []}
T["dse.grid_list"] = {
    "label": "Grids: show my grids and their columns", "group": "Grow",
    "help": "Lists the grids of your Ledgers with their columns, so you know the name to give 'send a list into a grid'. It changes nothing.",
    "script": "dse.py", "args": [{"lit": "grid"}, {"lit": "list"}], "fields": [], "timeout_min": 3, "outputs": []}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("grid tools:", sum(1 for k in T if k.startswith("dse.grid")), "tools:", len(T))
