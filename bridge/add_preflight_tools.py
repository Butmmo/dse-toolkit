"""One-off generator: adds the Outreach Preflight tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.preflight", "dse.preflight_domain"):
    T.pop(k, None)
DOMAIN = {"name": "domain", "label": "Your sending domain (the part after the @), optional", "type": "text", "required": False, "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9-]+)+$"}


def tool(label, help_, args, fields):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 3, "outputs": []}


T["dse.preflight"] = tool("Outreach Preflight: check a list before you send", "Checks a send list row by row before anything goes out. Blockers: on your do-not-contact list, a missing or invalid address, already contacted, an unfilled placeholder left in the message. Warnings: spam trigger words, ALL CAPS, too many links, a long message, role or free mailboxes, no easy way to say no, no sender name or postal address, more email than your own cap. Optionally also checks your sending domain (mail servers, SPF, DMARC, DKIM). Tick the last box to save a copy without the blocked rows (the original is never touched). Guidance, not legal advice. It sends nothing.",
                          [{"lit": "preflight"}, {"field": "csv"}, {"opt": "--domain", "field": "domain"}, {"flag": "--clean", "field": "clean"}],
                          [{"name": "csv", "label": "Send list", "type": "file", "required": True, "glob": "engines/*/send-lists/*.csv", "exclude": "drafts"}, DOMAIN,
                           {"name": "clean", "label": "Also save a copy without the blocked rows", "type": "bool", "default": False}])
T["dse.preflight_domain"] = tool("Outreach Preflight: check my sending domain", "Looks up your domain's mail servers, SPF record, DMARC record and the common DKIM names, and says what to fix before you send cold email from it. Nothing is sent or changed.",
                                 [{"lit": "preflight"}, {"opt": "--domain", "field": "domain"}], [{**DOMAIN, "label": "Your sending domain (the part after the @)", "required": True}])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
