"""Expose the local Send Desk waterfall experiment readout in HQ Tools."""
import json
from pathlib import Path

path = Path(__file__).resolve().parent / "catalog.json"
catalog = json.loads(path.read_text(encoding="utf-8"))
catalog["tools"]["dse.waterfall_score_outcomes"] = {
    "label": "Waterfall experiments: score Send Desk outcomes",
    "group": "Waterfall experiments",
    "help": "Reads this Engine's local send-list and explicit Send Desk log records, then creates aggregate A/B outcome JSON and Markdown reports. It reports assignment mode, provider setup, send coverage, reply categories, maturity-window outcomes, and uncertainty. It does not read message bodies, make provider calls, send messages, or choose a winning variant.",
    "script": "dse.py",
    "args": [
        {"lit": "eval-enrichment"}, {"lit": "score-send-outcomes"},
        {"field": "engine"}, {"opt": "--experiment-id", "field": "experiment_id"},
        {"opt": "--maturity-days", "field": "maturity_days"},
    ],
    "fields": [
        {"name": "engine", "label": "Engine to summarize", "type": "choice", "required": True,
         "choices_from": "engines", "choices": []},
        {"name": "experiment_id", "label": "Only this experiment (optional; blank includes all tagged experiments)",
         "type": "text", "required": False, "max": 80,
         "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"},
        {"name": "maturity_days", "label": "Fixed outcome observation window after first confirmed send",
         "type": "int", "required": True, "min": 1, "max": 365, "default": 14},
    ],
    "timeout_min": 5,
    "outputs": [
        "engines/*/data/waterfall-send-outcomes*.json",
        "engines/*/data/waterfall-send-outcomes*.md",
    ],
    "category": "enrich",
    "source": "Selected Engine's local send-lists and data/log.csv",
    "cost": "No provider calls, searches, paid services, or cloud AI. Only aggregate report files are attached to the HQ Tool result; source list rows and message contents are not uploaded by this tool.",
    "outputs_summary": [
        "Aggregate sent, skipped, unmarked, replied, booked and won counts by variant",
        "Reply categories and fixed-window maturity outcomes",
        "Provider order, config fingerprint and outreach assignment audit",
        "Descriptive rate intervals and cautions; no automatic winner selection",
        "JSON data report and readable Markdown brief",
    ],
}
path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("waterfall Send Desk outcome HQ Tool added")
