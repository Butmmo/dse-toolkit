"""One-off generator: adds the Call Desk tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.call_prep", "dse.call_after"):
    T.pop(k, None)
ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
SRC = {"name": "source", "label": "List the lead is on (like 2026-11-09, see the Send Desk)", "type": "text", "required": True, "max": 30, "pattern": r"^\d{4}-\d{2}-\d{2}(-followups)?$"}
ROW = {"name": "row", "label": "Row number on that list", "type": "text", "required": True, "max": 6, "pattern": r"^\d{1,6}$"}


def tool(label, help_, args, fields, outputs):
    return {"label": label, "group": "My engines", "help": help_ + " Nothing is sent.", "script": "dse.py", "args": args, "fields": fields, "timeout_min": 1, "outputs": outputs}


T["dse.call_prep"] = tool("Call Desk: prepare for a booked call", "A one-page brief for a booked call, built only from your own records: what you sent, what they wrote in their own words, what their website check or enrichment found (each fact says where it came from), three facts to open with, a question plan under the five scorecard headings with their gap woven in, your up-front contract script, and what must be in hand before you speak. What is not known is listed as not known. Also creates a notes sheet.",
                          [{"lit": "call"}, {"lit": "prep"}, {"field": "engine"}, {"opt": "--source", "field": "source"}, {"opt": "--row", "field": "row"}], [ENG, SRC, ROW], ["engines/*/calls/*/prep.md", "engines/*/calls/*/notes.md"])
T["dse.call_after"] = tool("Call Desk: what to do the minute the call ends", "Type what you heard (their problem in their words, the monthly cost they gave, the price, what you agreed) and get the recap message to send within 10 minutes, the scorecard command, and for a follow-up call the proposal command already filled in. A sold or lost call is written into your send log so your results stay true. Tick Stop to put them on your do-not-contact list if they asked not to be contacted.",
                           [{"lit": "call"}, {"lit": "after"}, {"field": "engine"}, {"opt": "--source", "field": "source"}, {"opt": "--row", "field": "row"}, {"opt": "--outcome", "field": "outcome"}, {"opt": "--problem", "field": "problem"},
                            {"opt": "--cost-month", "field": "cost_month"}, {"opt": "--price", "field": "price"}, {"opt": "--agreed", "field": "agreed"}, {"flag": "--stop", "field": "stop"}],
                           [ENG, SRC, ROW, {"name": "outcome", "label": "How it went", "type": "choice", "required": True, "default": "follow_up", "choices": [{"value": "follow_up", "label": "Follow-up (a proposal or next call)"}, {"value": "sold", "label": "Sold"}, {"value": "no_sale", "label": "Not a fit"}, {"value": "no_show", "label": "No show"}]},
                            {"name": "problem", "label": "Their problem, in their words", "type": "text", "required": False, "max": 300},
                            {"name": "cost_month", "label": "What they said it costs them each month ($, 0 if not said)", "type": "int", "required": False, "min": 0, "max": 100000000, "default": 0},
                            {"name": "price", "label": "The price you agreed or will quote ($, 0 if not yet)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0},
                            {"name": "agreed", "label": "What you agreed as the next step", "type": "text", "required": False, "max": 200},
                            {"name": "stop", "label": "They asked not to be contacted again", "type": "bool", "default": False}], ["engines/*/calls/*/after.md"])
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
