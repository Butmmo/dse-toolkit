"""One-off generator: adds the Weekly Review and Monthly goal tools (and the goal background helper) to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.review", "dse.review_all", "dse.goal"):
    T.pop(k, None)

ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
MONTH = {"name": "month", "label": "Month (YYYY-MM, empty = the next one to plan)", "type": "text", "required": False, "max": 7, "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"}


def tool(label, help_, args, fields):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 2, "outputs": []}


T["dse.review"] = tool("Weekly Review: what to do first this week", "Reads your send log, lists, follow-ups, calls, money and offers, and gives the 3 to 5 moves for the week in a fixed order, closest to money first. Each move says the exact step and which file the number came from. It sends and changes nothing.",
                       [{"lit": "review"}, {"field": "engine"}, {"opt": "--top", "field": "top"}],
                       [ENG, {"name": "top", "label": "How many moves", "type": "int", "min": 1, "max": 30, "default": 5}])
T["dse.review_all"] = tool("Weekly Review: all engines together", "The same review across every engine, moves ranked together.",
                           [{"lit": "review"}, {"lit": "all"}, {"opt": "--top", "field": "top"}], [{"name": "top", "label": "How many moves", "type": "int", "min": 1, "max": 30, "default": 5}])
T["dse.goal"] = tool("Monthly goal: suggest, set or accept", "Suggests next month's income goal from the money you logged in your last 3 complete months (plus a stretch you choose), shows the working, and says what each week would need using your own rates. Nothing changes unless you tick Accept the suggestion or type a goal yourself. A month with no goal of its own carries your standing target.",
                     [{"lit": "goal"}, {"field": "engine"}, {"opt": "--month", "field": "month"}, {"opt": "--stretch", "field": "stretch"}, {"flag": "--apply", "field": "apply"}, {"opt": "--set", "field": "set_to"}],
                     [ENG, MONTH, {"name": "stretch", "label": "Stretch over your history (%)", "type": "int", "min": 0, "max": 200, "default": 20},
                      {"name": "apply", "label": "Accept the suggestion as that month's goal", "type": "bool", "default": False},
                      {"name": "set_to", "label": "Or set the goal yourself ($, empty = leave it)", "type": "int", "min": 0, "max": 1000000, "default": 0}])

per = [x for x in c["periodic"] if x.get("script") != "bridge/goal_sync.py"]
per.append({"script": "bridge/goal_sync.py", "every_s": 21600, "what": "Monthly goals: a suggested goal for the month ahead, written for you to accept (it never changes a goal)"})
c["periodic"] = per

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools,", len(per), "periodic helpers")
