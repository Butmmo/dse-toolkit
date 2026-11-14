"""One-off generator: adds the Student Success Desk tool to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.success", None)
T["dse.success"] = {
    "label": "Student Success Desk: who needs a check-in, and expected DFY income", "group": "My engines",
    "help": "For your DFY students (the filings that Pull students' DFY months brought in). Shows each student's progress (qualified months out of 12, amount remitted out of the $18,000 cap) and flags who needs a check-in, with the facts behind every flag: has not filed, never filed, filed 0 repeatedly, under the $2,000 line (shown as an opportunity when close), a sharp drop against their own average, few qualified months, a remittance overdue, or nearly through. Each flag comes with a short, kind draft message in your name for you to send yourself. The forecast shows your expected DFY income for the coming months from each student's own last three filed months (likely and low), stopping at the cap or 12 qualified months, and leaving out students with too little history. It is a projection, not a promise. Nothing is sent.",
    "script": "dse.py",
    "args": [{"lit": "success"}, {"field": "engine"}, {"opt": "--view", "field": "view"}, {"opt": "--months", "field": "months"}],
    "fields": [{"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []},
               {"name": "view", "label": "Show", "type": "choice", "required": False, "default": "overview",
                "choices": [{"value": "overview", "label": "Overview (progress, flags, the top draft, forecast)"}, {"value": "flags", "label": "Flags only"}, {"value": "drafts", "label": "All draft messages"}, {"value": "forecast", "label": "Expected DFY income only"}]},
               {"name": "months", "label": "Forecast months", "type": "int", "min": 1, "max": 24, "default": 6}],
    "timeout_min": 1, "outputs": ["engines/*/success-desk.md"],
}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
