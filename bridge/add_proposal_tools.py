"""One-off generator: adds the Proposal Builder tool to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.proposal", None)
ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}


def txt(name, label, mx, req=True, pat=None):
    f = {"name": name, "label": label, "type": "text", "required": req, "max": mx}
    if pat:
        f["pattern"] = pat
    return f


T["dse.proposal"] = {
    "label": "Proposal Builder: a one-page proposal after a good call", "group": "My engines",
    "help": "Turns what you heard on the call into a clear one-page proposal, a cover email and a follow-up, in your name. Everything comes from what you type: their problem in their own words, what you will do, your price and deliverables. If you give what the problem costs them each month, it shows the yearly cost and the payback as plain arithmetic (never a promise of results). Optionally shows three options with the middle one recommended. It saves a text file and a print-ready page (open it in a browser and save as PDF), and marks [brackets] for anything only you know. It never sends anything.",
    "script": "dse.py",
    "args": [{"lit": "proposal"}, {"field": "engine"}, {"opt": "--client", "field": "client"}, {"opt": "--contact", "field": "contact"}, {"opt": "--problem", "field": "problem"}, {"opt": "--offer", "field": "offer"},
             {"opt": "--price", "field": "price"}, {"opt": "--deliverables", "field": "deliverables"}, {"opt": "--weeks", "field": "weeks"}, {"opt": "--cost-month", "field": "cost_month"},
             {"opt": "--options", "field": "options"}, {"opt": "--deposit", "field": "deposit"}, {"opt": "--currency", "field": "currency"}, {"opt": "--excludes", "field": "excludes"}, {"opt": "--start", "field": "start"}],
    "fields": [ENG, txt("client", "Client or company", 80), txt("contact", "Contact's first name (optional)", 40, False, r"^[A-Za-z][A-Za-z .'-]{0,39}$"),
               txt("problem", "Their problem, in their own words", 300), txt("offer", "What you will do for them (one sentence)", 120),
               {"name": "price", "label": "Your price (a whole number; leave 0 if you use options)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0},
               txt("deliverables", "What they get, separated by semicolons (for example Booking page; Reminder emails)", 300),
               {"name": "weeks", "label": "Weeks to deliver", "type": "int", "min": 1, "max": 26, "default": 3},
               {"name": "cost_month", "label": "What the problem costs them each month (from the call, 0 if unknown)", "type": "int", "required": False, "min": 0, "max": 100000000, "default": 0},
               txt("options", "Optional three-way choice: Basic:800:2 pages; Standard:1500:5 pages; Premium:2800:10 pages", 200, False, r"^[A-Za-z0-9 ,.:;/&()'+-]{3,200}$"),
               {"name": "deposit", "label": "Deposit to start (%)", "type": "int", "min": 0, "max": 100, "default": 50},
               {"name": "currency", "label": "Currency", "type": "choice", "required": False, "choices": [{"value": "USD", "label": "US dollars"}, {"value": "GBP", "label": "British pounds"}, {"value": "EUR", "label": "Euros"}], "default": "USD"},
               txt("excludes", "What is NOT included (optional, but it prevents surprises)", 200, False),
               {"name": "start", "label": "Start date (empty = next Monday)", "type": "date", "required": False}],
    "timeout_min": 1, "outputs": ["engines/*/proposals/*.md", "engines/*/proposals/*.html"],
}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
