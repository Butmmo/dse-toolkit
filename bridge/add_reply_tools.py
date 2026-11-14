"""One-off generator: adds the Reply Desk tools to catalog.json. Safe to re-run (replaces dse.reply and dse.dnc)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.reply", "dse.dnc"):
    T.pop(k, None)

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}


def tool(label, help_, args, fields):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 1, "outputs": []}


T["dse.reply"] = tool("Reply Desk: what kind of reply, and what to say", "Paste a reply you received (line breaks become spaces). It says what kind it is (interested, question, price objection, already has someone, not now, not interested, wrong person, points to someone else, asks to stop, out of office, or unclear), shows the words that decided it, drafts a short honest answer in your name with [brackets] for facts only you know, and works out the day to follow up. Tick Record it, with the list name and row number, to put it in your send log (follow-ups stop) and to put unsubscribes and 'no thanks' on your do-not-contact list. It never sends anything.",
                      [{"lit": "reply"}, {"field": "engine"}, {"opt": "--text", "field": "text"}, {"opt": "--name", "field": "name"}, {"opt": "--source", "field": "source"}, {"opt": "--row", "field": "row"},
                       {"opt": "--email", "field": "email"}, {"flag": "--log", "field": "log"}],
                      [ENG, {"name": "text", "label": "Their reply (paste it)", "type": "text", "required": True, "max": 1500},
                       {"name": "name", "label": "Their first name (optional)", "type": "text", "required": False, "max": 40, "pattern": r"^[A-Za-z][A-Za-z .'-]{0,39}$"},
                       {"name": "source", "label": "List it answers (for example 2026-11-09), only to record it", "type": "text", "required": False, "max": 30, "pattern": r"^\d{4}-\d{2}-\d{2}(-followups)?$"},
                       {"name": "row", "label": "Row number on that list, only to record it", "type": "text", "required": False, "max": 6, "pattern": r"^\d{1,6}$"},
                       {"name": "email", "label": "Their email (only for the do-not-contact list)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"},
                       {"name": "log", "label": "Record it (send log and do-not-contact list)", "type": "bool", "default": False}])
T["dse.dnc"] = tool("Reply Desk: my do-not-contact list", "Everyone who asked you to stop or said no, with the date and why. Outreach Preflight checks every list against it. No tool removes an entry.", [{"lit": "dnc"}, {"field": "engine"}], [ENG])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
