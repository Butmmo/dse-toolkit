"""One-off generator: adds the Statement Matcher tool to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.match", None)
ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}

T["dse.match"] = {
    "label": "Statement Matcher: match money received to invoices", "group": "My engines",
    "help": "Reads the CSV you exported from Grey, Payoneer or your bank (saved in the engine's statements folder on your PC) and matches the money that came IN to your open invoices: student cuts and client invoices. It uses the invoice number in the reference, the amount (exact, or short by a normal transfer fee), the sender's name and the date. SURE matches (the invoice number and the amount both fit, nothing else fits as well) can be recorded in one go if you tick Record the SURE matches: that does exactly what Paid does, including the Cash Desk and, for DFY months, Citadel. Everything else (likely, more than one fit, no fit) is only shown, with the command to run if you agree. A credit is never applied twice and a different currency is never matched. Nothing is sent.",
    "script": "dse.py",
    "args": [{"lit": "match"}, {"field": "engine"}, {"field": "statement"}, {"flag": "--apply", "field": "apply"}, {"flag": "--monthfirst", "field": "monthfirst"}, {"opt": "--tolerance", "field": "tolerance"}],
    "fields": [ENG,
               {"name": "statement", "label": "Statement (your exported CSV)", "type": "file", "required": True, "glob": "engines/*/statements/*.csv", "exclude": "-match"},
               {"name": "apply", "label": "Record the SURE matches (only those)", "type": "bool", "default": False},
               {"name": "monthfirst", "label": "Read dates like 03/04/2026 as March 4 (default: day first)", "type": "bool", "default": False},
               {"name": "tolerance", "label": "Transfer fee a payment may be short by (empty = 2% of the invoice, $1 to $20)", "type": "int", "required": False, "min": 0, "max": 100}],
    "timeout_min": 2, "outputs": ["engines/*/statements/*-match.md"],
}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
