"""Add the Ledger formula assistant to the runner catalog."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
catalog = json.loads(p.read_text(encoding="utf-8"))
catalog["tools"].pop("dse.formula_assist", None)
catalog["tools"]["dse.formula_assist"] = {
    "label": "Grids: suggest a formula (local AI)", "group": "Grow",
    "help": "Suggests a grid formula from your plain-language description using an Ollama model installed on this PC. Your request passes through Citadel's HQ job queue to this PC, then goes to local Ollama, not a cloud AI. The formula is only a suggestion; review and validate it in the grid before saving.",
    "script": "dse.py", "args": [{"lit": "formula-assist"}, {"opt": "--request", "field": "request"}, {"opt": "--columns", "field": "columns"}, {"opt": "--result-type", "field": "result_type"}, {"opt": "--model", "field": "model"}, {"opt": "--current-formula", "field": "current_formula"}],
    "fields": [
        {"name": "request", "label": "Formula description", "type": "text", "required": True, "max": 2000},
        {"name": "columns", "label": "Available grid columns (JSON)", "type": "text", "required": True, "max": 5000},
        {"name": "result_type", "label": "Expected result type", "type": "text", "required": False, "default": "text", "max": 20},
        {"name": "model", "label": "Local Ollama model", "type": "text", "required": False, "default": "auto", "max": 80},
        {"name": "current_formula", "label": "Current formula to improve", "type": "text", "required": False, "max": 500},
    ], "timeout_min": 5, "outputs": []
}
p.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("formula_assist tool added")
