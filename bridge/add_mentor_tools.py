"""One-off generator: the "mentors" choice on the DBI-AI question tool (chat.ask) in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
t = c["tools"]["chat.ask"]
t["fields"] = [f for f in t["fields"] if f["name"] != "mentors"]
t["fields"].append({"name": "mentors", "label": "Mentor passages from the Voices library", "type": "choice", "required": False, "default": "auto",
                    "choices": [{"value": "auto", "label": "Auto: only when I ask for a mentor, a quote or name someone"}, {"value": "only", "label": "Mentor passages only (no AI)"}, {"value": "off", "label": "Off"}]})
t["args"] = [a for a in t["args"] if a.get("field") != "mentors"] + [{"opt": "--mentors", "field": "mentors"}]
t["help"] = t["help"].rstrip() + " Mentors: ask for a quote, a mentor, or name someone (what did Seneca say about anger?) and real passages from the Voices library, with their sources, are shown beside the answer. Matching is by words, not by meaning, so they are never added to an ordinary answer unasked."
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("ok")
