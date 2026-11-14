"""One-off generator: adds the Client Desk tools to catalog.json. Safe to re-run (replaces the dse.client* entries)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dse.client")]:
    del T[k]

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
CLIENT = {"name": "client", "label": "Client", "type": "file", "required": True, "glob": "engines/*/clients/*/client.json"}
DATE = {"name": "date", "label": "Date (empty = today)", "type": "date", "required": False}


def tool(label, help_, args, fields, outputs=None):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 1, "outputs": outputs or []}


T["dse.client_won"] = tool("Client Desk: this proposal was accepted", "Turns a saved proposal into a client: price, deposit, timeline and deliverables carry over. Writes the onboarding checklist with dates, a welcome message in your name, a short agreement outline (a starting point, not legal advice) and the deposit invoice as a print-ready page. Nothing is sent: you send the welcome message, the agreement and the invoice yourself.",
                           [{"lit": "client"}, {"lit": "won"}, {"field": "engine"}, {"opt": "--proposal", "field": "proposal"}, {"opt": "--email", "field": "email"}, {"opt": "--address", "field": "address"}],
                           [ENG, {"name": "proposal", "label": "Proposal", "type": "file", "required": True, "glob": "engines/*/proposals/*.json"},
                            {"name": "email", "label": "Their email (for the invoice, optional)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"},
                            {"name": "address", "label": "Their billing address (optional)", "type": "text", "required": False, "max": 200}],
                           ["engines/*/clients/*/onboarding.md", "engines/*/clients/*/invoices/*.html"])
T["dse.client_list"] = tool("Client Desk: my clients", "Every client with status, price, paid, what is owed now and the next deliverable.", [{"lit": "client"}, {"lit": "list"}, {"field": "engine"}], [ENG])
T["dse.client_show"] = tool("Client Desk: one client in full", "Onboarding tasks, deliverables with dates (late ones marked), and every invoice with what is outstanding.", [{"lit": "client"}, {"lit": "show"}, {"field": "client"}], [CLIENT])
T["dse.client_done"] = tool("Client Desk: tick off a deliverable or task", "Marks a deliverable or an onboarding task as done (type a few words of its name). When the last deliverable is done it tells you to issue the final invoice.",
                            [{"lit": "client"}, {"lit": "done"}, {"field": "client"}, {"opt": "--item", "field": "item"}, {"opt": "--date", "field": "date"}],
                            [CLIENT, {"name": "item", "label": "A few words of its name", "type": "text", "required": True, "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,.'&/()-]{2,79}$"}, DATE])
T["dse.client_invoice"] = tool("Client Desk: issue the final or an extra invoice", "The final invoice is the balance of the price and follows delivery. An extra invoice is for something added (an amount and what it is for). Print-ready page; you send it yourself.",
                               [{"lit": "client"}, {"lit": "invoice"}, {"field": "client"}, {"opt": "--kind", "field": "kind"}, {"opt": "--amount", "field": "amount"}, {"opt": "--note", "field": "note"}, {"opt": "--terms", "field": "terms"}],
                               [CLIENT, {"name": "kind", "label": "Which", "type": "choice", "required": True, "choices": [{"value": "final", "label": "Final invoice (the balance)"}, {"value": "extra", "label": "Extra invoice (something added)"}], "default": "final"},
                                {"name": "amount", "label": "Amount (extra invoices only)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0},
                                {"name": "note", "label": "What it is for (extra invoices only)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,.'&/()-]{2,119}$"},
                                {"name": "terms", "label": "Days to pay", "type": "int", "min": 0, "max": 90, "default": 7}], ["engines/*/clients/*/invoices/*.html"])
T["dse.client_paid"] = tool("Client Desk: money received for an invoice", "Records a payment against an invoice (leave the amount empty for what is left) and adds it to the Cash Desk, so what you received stays true without typing it twice.",
                            [{"lit": "client"}, {"lit": "paid"}, {"field": "client"}, {"opt": "--invoice", "field": "invoice"}, {"opt": "--amount", "field": "amount"}, {"opt": "--date", "field": "date"}],
                            [CLIENT, {"name": "invoice", "label": "Invoice number (like INV-2026-001)", "type": "text", "required": True, "max": 20, "pattern": r"^INV-\d{4}-\d{3,4}$"},
                             {"name": "amount", "label": "Amount received (empty = the whole outstanding amount)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0}, {**DATE, "label": "Date received (empty = today)"}])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.client")]), "client tools,", len(T), "in all")
