"""Expose safe, one-variant-per-lead assignment as a local HQ Tools action."""
import json
from pathlib import Path

path = Path(__file__).resolve().parent / "catalog.json"
catalog = json.loads(path.read_text(encoding="utf-8"))
catalog["tools"]["dse.waterfall_assign_outreach"] = {
    "label": "Waterfall experiments: assign outreach variants",
    "group": "Waterfall experiments",
    "help": "Takes a combined CSV containing both enriched variants for the same leads, assigns each stable lead ID to exactly one outreach variant using the experiment ID and seed, checks the selected Engine's prior exposure history, and saves the assigned CSV directly into that Engine's imports. It does not send anything or upload lead rows. Keep the paired source CSV outside the Engine imports folder.",
    "script": "dse.py",
    "args": [
        {"lit": "eval-enrichment"}, {"lit": "assign-outreach"}, {"field": "csv"},
        {"opt": "--experiment-id", "field": "experiment_id"}, {"opt": "--seed", "field": "seed"},
        {"opt": "--engine", "field": "engine"},
    ],
    "fields": [
        {"name": "csv", "label": "Combined paired A/B enrichment CSV", "type": "file", "required": True,
         "glob": "my-lists/*.csv", "exclude": "outreach-assigned"},
        {"name": "experiment_id", "label": "Waterfall experiment ID", "type": "text", "required": True,
         "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"},
        {"name": "seed", "label": "Assignment seed (keep the same to reproduce assignments)", "type": "text",
         "required": True, "default": "42", "max": 80},
        {"name": "engine", "label": "Engine that will use these assigned leads", "type": "choice", "required": True,
         "choices_from": "engines", "choices": []},
    ],
    "timeout_min": 5,
    "outputs": ["my-lists/*-outreach-assigned.csv", "my-lists/*-outreach-assigned-assignment.json",
                "engines/*/imports/*-outreach-assigned.csv", "engines/*/imports/*-outreach-assigned-assignment.json"],
    "category": "enrich",
    "source": "Paired enrichment CSV selected from this PC",
    "cost": "No provider calls, internet searches, paid services, or cloud AI. Assignment is computed locally from the experiment ID, seed, and stable lead ID.",
    "outputs_summary": [
        "One assigned A or B row per paired stable lead ID",
        "Repeatable assignment for the same experiment, seed, and lead ID",
        "Assignment experiment, variant, and seed columns for Engine and Send Desk audit",
        "Destination Engine exposure history is checked before the import file is written",
        "Data-minimized assignment audit records source and output hashes, seed, counts, and destination Engine",
        "The original paired enrichment CSV is not modified",
    ],
}
path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("waterfall outreach assignment HQ Tool added")
