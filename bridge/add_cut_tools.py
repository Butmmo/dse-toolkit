"""One-off generator: adds the Cut Desk tools to catalog.json. Safe to re-run (replaces the dse.cut* entries)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dse.cut")]:
    del T[k]

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
STUDENT = {"name": "student", "label": "Student", "type": "file", "required": True, "glob": "engines/*/cuts/*/student.json"}
MONTH = {"name": "month", "label": "Month they are reporting (YYYY-MM)", "type": "text", "required": True, "max": 7, "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"}
DATE = {"name": "date", "label": "Date received (empty = today)", "type": "date", "required": False}
NOTE = "Nothing is sent. The agreement text is a starting point, not legal advice."


def tool(label, help_, args, fields, outputs=None):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 1, "outputs": outputs or []}


T["dse.cut_add"] = tool("Cut Desk: add a student's agreement", "Sets up the percentage cut a student owes you: your percent, whether it is of their gross earnings or net of the platform's fees, the currency and how they pay you (Grey or Payoneer). Writes an agreement starter to have checked. " + NOTE,
                        [{"lit": "cut"}, {"lit": "add"}, {"field": "engine"}, {"opt": "--name", "field": "name"}, {"opt": "--percent", "field": "percent"}, {"opt": "--basis", "field": "basis"}, {"opt": "--currency", "field": "currency"},
                         {"opt": "--method", "field": "method"}, {"opt": "--email", "field": "email"}, {"opt": "--due-days", "field": "due_days"}, {"opt": "--start", "field": "start"}],
                        [ENG, {"name": "name", "label": "Student's name", "type": "text", "required": True, "max": 60, "pattern": r"^[A-Za-z][A-Za-z .'-]{1,59}$"},
                         {"name": "percent", "label": "Your cut (% of their earnings, 1 to 60)", "type": "int", "min": 1, "max": 60, "default": 10},
                         {"name": "basis", "label": "Percent of", "type": "choice", "required": True, "choices": [{"value": "gross", "label": "Their gross earnings"}, {"value": "net", "label": "Earnings after the platform's own fees"}], "default": "gross"},
                         {"name": "currency", "label": "Currency", "type": "choice", "required": True, "choices": [{"value": "USD", "label": "US dollars"}, {"value": "GBP", "label": "British pounds"}, {"value": "EUR", "label": "Euros"}], "default": "USD"},
                         {"name": "method", "label": "How they pay you", "type": "choice", "required": True, "choices": [{"value": "grey", "label": "Grey"}, {"value": "payoneer", "label": "Payoneer"}, {"value": "other", "label": "Other"}], "default": "grey"},
                         {"name": "email", "label": "Their email (optional)", "type": "text", "required": False, "max": 120, "pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"},
                         {"name": "due_days", "label": "Days to pay after the invoice", "type": "int", "min": 0, "max": 60, "default": 7},
                         {"name": "start", "label": "Agreement starts (empty = this month)", "type": "date", "required": False}], ["engines/*/cuts/*/agreement.md"])
T["dse.cut_report"] = tool("Cut Desk: a student's monthly earnings report", "Enter what a student earned in a month (0 is a valid report), the platform fees if their agreement is net, and where the proof is kept. It works out your cut and makes the invoice in the company name as a print-ready page. A big drop against their own recent average gets a friendly prompt, never an accusation. " + NOTE,
                           [{"lit": "cut"}, {"lit": "report"}, {"field": "student"}, {"opt": "--month", "field": "month"}, {"opt": "--earned", "field": "earned"}, {"opt": "--fees", "field": "fees"}, {"opt": "--proof", "field": "proof"}, {"flag": "--replace", "field": "replace"}],
                           [STUDENT, MONTH, {"name": "earned", "label": "What they earned that month", "type": "int", "required": True, "min": 0, "max": 10000000, "default": 0},
                            {"name": "fees", "label": "Platform fees they paid (net agreements only)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0},
                            {"name": "proof", "label": "Where the proof is (for example: Nov statement in the proofs folder)", "type": "text", "required": False, "max": 200},
                            {"name": "replace", "label": "Correct a month already reported (only before anything is paid on it)", "type": "bool", "default": False}], ["engines/*/cuts/*/invoices/*.html"])
T["dse.cut_paid"] = tool("Cut Desk: a student's cut arrived", "Records what actually arrived for a cut invoice (leave the amount empty for the whole amount) and adds it to the Cash Desk. If it came in short, usually a transfer fee, it says so; tick Write off the shortfall to accept it.",
                         [{"lit": "cut"}, {"lit": "paid"}, {"field": "student"}, {"opt": "--invoice", "field": "invoice"}, {"opt": "--amount", "field": "amount"}, {"opt": "--date", "field": "date"}, {"flag": "--writeoff", "field": "writeoff"}],
                         [STUDENT, {"name": "invoice", "label": "Invoice number (like CUT-2026-001)", "type": "text", "required": True, "max": 20, "pattern": r"^CUT-\d{4}-\d{3,4}$"},
                          {"name": "amount", "label": "Amount that arrived (empty = the whole amount owed)", "type": "int", "required": False, "min": 0, "max": 10000000, "default": 0}, DATE,
                          {"name": "writeoff", "label": "Write off any shortfall (my choice)", "type": "bool", "default": False}])
T["dse.cut_list"] = tool("Cut Desk: who owes what", "Every student with the cut invoiced, received and owed, and what each one needs (a missing report, an overdue invoice).", [{"lit": "cut"}, {"lit": "list"}, {"field": "engine"}], [ENG])
T["dse.cut_show"] = tool("Cut Desk: one student in full", "Every month reported, the cut, the invoice and whether it is settled, with any month that has no proof noted.", [{"lit": "cut"}, {"lit": "show"}, {"field": "student"}], [STUDENT])
T["dse.cut_status"] = tool("Cut Desk: pause or end an agreement", "Paused or ended students are no longer chased for reports. Unpaid invoices stay payable.", [{"lit": "cut"}, {"lit": "status"}, {"field": "student"}, {"opt": "--to", "field": "to"}],
                           [STUDENT, {"name": "to", "label": "Set to", "type": "choice", "required": True, "choices": [{"value": "active", "label": "Active"}, {"value": "paused", "label": "Paused"}, {"value": "ended", "label": "Ended"}], "default": "paused"}])

T["dse.cut_sync"] = tool("Cut Desk: pull students' DFY months from Citadel", "Students already file their monthly net income in Citadel. This brings every filed month into the Cut Desk as a statement and an invoice (DFY: 20% of net income, capped at $18,000, ending at 12 qualified months), recorded as paid when Citadel already shows it paid. Choose Turn on to let the runner do it every ten minutes. Needs your runner to be an admin's and the DFY bridge SQL run in Supabase. Nothing is sent.",
                         [{"lit": "cut"}, {"lit": "sync"}, {"field": "engine"}, {"opt": "--auto", "field": "auto"}],
                         [ENG, {"name": "auto", "label": "Automatic sync", "type": "choice", "required": False, "choices": [{"value": "on", "label": "Turn on (every 10 minutes)"}, {"value": "off", "label": "Turn off"}]}])
T["dse.cut_accounts"] = tool("Cut Desk: where students pay (check or publish)", "Checks engines/<engine>/payout-accounts.json (Grey, Payoneer or bank accounts) and shows what students currently see on the payment page. Tick Publish to replace what students see. Placeholders in [brackets] are refused so an unfinished list never goes live. This changes what students see, so only publish when the details are right.",
                             [{"lit": "cut"}, {"lit": "accounts"}, {"field": "engine"}, {"flag": "--publish", "field": "publish"}, {"flag": "--example", "field": "example"}],
                             [ENG, {"name": "publish", "label": "Publish these accounts to students", "type": "bool", "default": False},
                              {"name": "example", "label": "Start from the example file (copies it if none exists)", "type": "bool", "default": False}])
per = [x for x in c["periodic"] if x.get("script") != "bridge/dfy_sync.py"]
per.append({"script": "bridge/dfy_sync.py", "every_s": 600, "what": "DFY: students' filed months from Citadel into the Cut Desk (only when you turned it on)"})
c["periodic"] = per

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.cut")]), "cut tools,", len(T), "in all")
