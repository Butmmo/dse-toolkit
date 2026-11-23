"""Expose safe, one-variant-per-lead assignment as a local HQ Tools action."""
import json
from pathlib import Path

path = Path(__file__).resolve().parent / "catalog.json"
catalog = json.loads(path.read_text(encoding="utf-8"))
catalog["tools"]["dse.waterfall_assign_outreach"] = {
    "label": "Waterfall experiments: assign outreach variants",
    "group": "Waterfall experiments",
    "help": "Takes a verified paired-results CSV created by the Pair verified A/B results tool. It checks the local cohort manifest and paired-file hash, then assigns each stable lead ID to exactly one outreach variant using the experiment ID and seed. It checks the selected Engine's prior exposure history and saves the assigned CSV to that PC's local Engine imports folder. The CSV stays local; this tool does not attach lead rows to its job result, upload them, or send outreach. Continue with the PC Engine workflow and inspect the import before outreach.",
    "script": "dse.py",
    "args": [
        {"lit": "eval-enrichment"}, {"lit": "assign-outreach"}, {"field": "csv"},
        {"opt": "--experiment-id", "field": "experiment_id"}, {"opt": "--seed", "field": "seed"},
        {"opt": "--engine", "field": "engine"},
    ],
    "fields": [
        {"name": "csv", "label": "Combined paired A/B enrichment CSV", "type": "file", "required": True,
         "glob": "my-lists/waterfall-experiment-*-paired.csv"},
        {"name": "experiment_id", "label": "Waterfall experiment ID", "type": "text", "required": True,
         "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"},
        {"name": "seed", "label": "Assignment seed (keep the same to reproduce assignments)", "type": "text",
         "required": True, "default": "42", "max": 80},
        {"name": "engine", "label": "Engine that will use these assigned leads", "type": "choice", "required": True,
         "choices_from": "engines", "choices": []},
    ],
    "timeout_min": 5,
    "outputs": [
        {"glob": "my-lists/*-outreach-assigned.csv", "upload": False, "label": "Assigned lead CSV kept on this PC"},
        {"glob": "my-lists/*-outreach-assigned-assignment.json", "upload": False, "label": "Data-minimized assignment audit"},
        {"glob": "engines/*/imports/*-outreach-assigned.csv", "upload": False, "label": "Engine import for the PC workflow"},
        {"glob": "engines/*/imports/*-outreach-assigned-assignment.json", "upload": False, "label": "Engine assignment audit"},
        {"glob": "my-lists/waterfall-experiment-*-cohort.json", "upload": False, "label": "Local experiment cohort record"},
    ],
    "category": "enrich",
    "source": "Paired enrichment CSV selected from this PC",
    "cost": "No provider calls, internet searches, paid services, cloud AI, or lead-row uploads by the runner. Assignment is computed locally from the experiment ID, seed, and stable lead ID. The assigned CSV is saved to this PC's Engine imports folder and is not attached to the HQ Tool result.",
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
