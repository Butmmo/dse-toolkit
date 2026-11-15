"""One-off generator: the Daily Brief tool and its background sync in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T["dse.brief"] = {
    "label": "Daily Brief: what to do first today", "group": "My engines",
    "help": "The few things to do first today across all your engines, in the Weekly Review's fixed order (closest to money first), each with the tool that does it. Your PC builds this by itself in the background and shows it on your Dashboard; run it here to refresh it now. Nothing is sent or changed.",
    "script": "dse.py", "args": [{"lit": "brief"}, {"opt": "--top", "field": "top"}],
    "fields": [{"name": "top", "label": "How many things", "type": "int", "required": False, "min": 1, "max": 8, "default": 3}],
    "timeout_min": 2, "outputs": []}
per = [x for x in c.get("periodic", []) if x.get("script") != "bridge/brief_sync.py"]
per.append({"script": "bridge/brief_sync.py", "every_s": 900, "what": "Daily Brief: what to do first today, sent to your Dashboard (nothing is sent to anyone else)"})
c["periodic"] = per
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools,", len(per), "background helpers")
