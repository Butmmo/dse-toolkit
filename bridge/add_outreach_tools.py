"""One-off generator: adds the Outreach Pack tool to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.outreach", None)

T["dse.outreach"] = {
    "label": "Outreach Pack: 14-day touch plan and mail-merge file",
    "group": "My engines",
    "help": ("Takes an engine's newest send list and builds two files for you: a mail-merge file (one row per business you can email, with the whole email sequence "
             "and the send dates already worked out) and a 14-day touch calendar (the warm comment the day before, the emails, the likes and replies, the call). "
             "Leaves out anyone on your do-not-contact list, already contacted or listed twice. Marks a row not ready while your sender name, postal address, gap line "
             "or (for the Inquiry door) your Reply Test result is missing. Run Outreach Preflight on the list and your sending domain before you load the file. "
             "It sends nothing: you load the file into your own Gmail merge or sending tool and press start yourself. Guidance, not legal advice."),
    "script": "dse.py",
    "args": [{"lit": "outreach"}, {"field": "engine"}, {"opt": "--door", "field": "door"}, {"opt": "--start", "field": "start"},
             {"opt": "--name", "field": "name"}, {"opt": "--address", "field": "address"}],
    "fields": [
        {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []},
        {"name": "door", "label": "Door", "type": "choice", "required": True, "default": "review",
         "choices": [{"value": "review", "label": "Review door: the four-email Gap, Leak, Lift and Breakup sequence"},
                     {"value": "inquiry", "label": "Inquiry door: the three Reply Test emails (needs your Reply Test result on each row)"}]},
        {"name": "start", "label": "Day of the first email (empty = tomorrow)", "type": "date"},
        {"name": "name", "label": "Your name, as it signs the emails (empty = the engine's)", "type": "text", "required": False, "max": 60},
        {"name": "address", "label": "Your postal address for the footer (empty = the engine's)", "type": "text", "required": False, "max": 160},
    ],
    "timeout_min": 3,
    "outputs": [],
}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
