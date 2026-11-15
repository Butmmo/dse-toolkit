"""One-off generator: the "history" option (the memory range) on the DBI-AI question tool (chat.ask) in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
t = c["tools"]["chat.ask"]
t["args"] = [a for a in t["args"] if a.get("field") != "history"] + [{"opt": "--history", "field": "history"}]
t["fields"] = [f for f in t["fields"] if f["name"] != "history"] + [{
    "name": "history", "label": "Earlier messages of this chat (internal: the memory range, the newest few, up to 2400 characters)", "type": "text", "required": False, "max": 2400,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9 ,.'?&/()!:;\\\"%+=#@_*$|-]{0,2399}$"}]
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("history field added")
