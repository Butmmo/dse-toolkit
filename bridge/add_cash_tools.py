"""One-off generator: adds the Cash Desk tools to catalog.json. Safe to re-run (replaces the dse.cash* entries)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dse.cash")]:
    del T[k]

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
MONTH = {"name": "month", "label": "Month (YYYY-MM, empty = this month)", "type": "text", "required": False, "max": 7, "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"}
TARGET = {"name": "target", "label": "Monthly income target ($, empty = keep the saved one)", "type": "int", "min": 50, "max": 1000000, "default": 0}
KINDS = [{"value": k, "label": k} for k in ("commission", "retainer", "project", "bonus", "other", "refund")]


def tool(label, help_, args, fields, tmo=1):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": tmo, "outputs": []}


T["dse.cash"] = tool("Cash Desk: am I on track this month?", "Money you logged as received against your monthly target, the pace to the end of the month, the steps (messages, replies, calls, sales) from your own logs, and what it would take to close the gap using your own rates. Every figure comes from files on this PC and the report says so when there is too little data to trust a rate.",
                     [{"lit": "cash"}, {"field": "engine"}, {"opt": "--month", "field": "month"}, {"opt": "--target", "field": "target"}], [ENG, MONTH, TARGET])
T["dse.cash_all"] = tool("Cash Desk: all engines together", "The same report for every engine added up, with the targets added up too.",
                         [{"lit": "cash"}, {"lit": "all"}, {"opt": "--month", "field": "month"}], [MONTH])
T["dse.cashin"] = tool("Cash Desk: log money I received", "Writes one line to the engine's cash file: the day, the amount, what kind of money it was and a short note. Log only money that has actually arrived (a refund is logged as a refund, not as a minus). Then shows the updated report.",
                       [{"lit": "cashin"}, {"field": "engine"}, {"opt": "--amount", "field": "amount"}, {"opt": "--kind", "field": "kind"}, {"opt": "--note", "field": "note"}, {"opt": "--date", "field": "date"}],
                       [ENG, {"name": "amount", "label": "Amount received ($)", "type": "int", "required": True, "min": 1, "max": 10000000},
                        {"name": "kind", "label": "What kind", "type": "choice", "required": False, "choices": KINDS, "default": "commission"},
                        {"name": "note", "label": "Who paid / what for (optional)", "type": "text", "required": False, "max": 100, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 .'&/()!:_#-]{0,99}$"},
                        {"name": "date", "label": "Date received (empty = today)", "type": "date", "required": False}])
T["dse.cashlog"] = tool("Cash Desk: money I logged", "Every payment logged for the engine, with the total.", [{"lit": "cashlog"}, {"field": "engine"}], [ENG])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.cash")]), "cash tools,", len(T), "in all")
