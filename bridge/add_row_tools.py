"""One-off generator: adds the tool a BPS Table workflow can run for one grid row. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.enrich_row", None)
T["dse.enrich_row"] = {
    "label": "Lead enrichment: one website, for a grid row", "group": "Grow",
    "help": "Looks at one website and finds the owner, an email, a phone number and the score, and prints them as one result line that a workflow of your BPS Tables reads and writes into the row. "
            "A workflow runs this for you with the step 'Run a tool on this PC' (the PC must be on and connected); you can also run it here by hand. It only reads public pages and changes nothing of yours.",
    "script": "dse.py", "args": [{"lit": "enrich"}, {"opt": "--site", "field": "site"}, {"lit": "--result-line"}, {"flag": "--fast", "field": "fast"}],
    "fields": [
        {"name": "site", "label": "Website", "type": "url", "required": True},
        {"name": "fast", "label": "Fast (skip the hidden browser)", "type": "bool", "default": True},
    ],
    "timeout_min": 6, "outputs": []}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("tools:", len(T))
