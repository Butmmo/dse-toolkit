"""One-off generator: the CRM sync tool and its background helper in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
T["dse.crm"] = {
    "label": "CRM sync: keep this engine's leads, replies and calls in my BPS CRM", "group": "My engines",
    "help": "Your engine already knows every lead, who replied (and what they said), who booked a call and who became a client. This puts them in your BPS CRM so you stop copying: one lead per business, the right stage, and a block in the notes that keeps itself up to date. It is OFF until you turn it on for an engine. Preview shows exactly what the CRM would get. A stage only moves forward, what you wrote in the CRM is never overwritten, and a lead you added yourself is matched by its website and adopted, not duplicated. Nothing is sent to anyone but your own account.",
    "script": "dse.py", "args": [{"lit": "crm"}, {"field": "action"}, {"field": "engine"}],
    "fields": [{"name": "action", "label": "What to do", "type": "choice", "required": True, "default": "preview",
                "choices": [{"value": "preview", "label": "Preview what the CRM would get"}, {"value": "on", "label": "Turn on for this engine"}, {"value": "off", "label": "Turn off for this engine"},
                            {"value": "sync", "label": "Send now (it also runs by itself every 5 minutes when on)"}, {"value": "status", "label": "Status of this engine"}]}, ENG],
    "timeout_min": 3, "outputs": []}
per = [x for x in c.get("periodic", []) if x.get("script") != "bridge/crm_sync.py"]
per.append({"script": "bridge/crm_sync.py", "every_s": 300, "what": "CRM: the leads, replies and calls of engines you turned on, kept in your BPS CRM (only your own account)"})
c["periodic"] = per
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools,", len(per), "helpers")
