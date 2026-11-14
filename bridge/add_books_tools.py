"""One-off generator: adds the Books Desk and exchange-rate tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.books", "dse.fx_add", "dse.fx_list"):
    T.pop(k, None)

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
CUR = [{"value": v, "label": v} for v in ("USD", "GBP", "EUR", "NGN")]


def tool(label, help_, args, fields, outputs=None):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 2, "outputs": outputs or []}


T["dse.books"] = tool("Books Desk: the monthly pack for your accountant", "Writes a month's records in one place: what you received (cash basis), what you invoiced (accrual basis), what is still owed with ageing, what you wrote off, the exchange rates used, the year to date, and a list of things to check, plus CSV files your accountant can open. Every currency stays in its own currency; money in a currency you gave no exchange rate for is listed as NOT converted, never guessed. It does not work out tax and lists the questions for your accountant. Nothing is sent.",
                      [{"lit": "books"}, {"field": "engine"}, {"opt": "--month", "field": "month"}, {"opt": "--base", "field": "base"}],
                      [ENG, {"name": "month", "label": "Month (YYYY-MM, empty = the last complete month)", "type": "text", "required": False, "max": 7, "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
                       {"name": "base", "label": "Add everything up in", "type": "choice", "required": False, "choices": [{"value": v, "label": v} for v in ("USD", "GBP", "EUR")], "default": "USD"}],
                      ["engines/*/books/*/summary.md", "engines/*/books/*/*.csv"])
T["dse.fx_add"] = tool("Exchange rates: enter one", "Money in other currencies counts toward your dollar target and your books only at exchange rates YOU enter (the rate your bank, Grey or Payoneer gave you when the money landed, or the one your accountant tells you to use). Nothing is looked up. The most recent rate on or before a payment's date is used.",
                       [{"lit": "fx"}, {"lit": "add"}, {"field": "engine"}, {"opt": "--from", "field": "from_cur"}, {"opt": "--to", "field": "to_cur"}, {"opt": "--rate", "field": "rate"}, {"opt": "--date", "field": "date"}, {"opt": "--note", "field": "note"}],
                       [ENG, {"name": "from_cur", "label": "From (the money you received)", "type": "choice", "required": True, "choices": CUR, "default": "GBP"},
                        {"name": "to_cur", "label": "To", "type": "choice", "required": True, "choices": CUR, "default": "USD"},
                        {"name": "rate", "label": "How many of the TO currency 1 of the FROM currency buys (like 1.27)", "type": "text", "required": True, "max": 14, "pattern": r"^\d{1,7}(\.\d{1,6})?$"},
                        {"name": "date", "label": "Rate date (empty = today)", "type": "date", "required": False},
                        {"name": "note", "label": "Where the rate came from (optional)", "type": "text", "required": False, "max": 100, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 .,'/()-]{0,99}$"}])
T["dse.fx_list"] = tool("Exchange rates: the ones I entered", "Every exchange rate you entered for this engine, oldest first.", [{"lit": "fx"}, {"lit": "list"}, {"field": "engine"}], [ENG])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
