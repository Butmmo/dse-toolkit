"""One-off generator: adds the "first name, last name and work email for a grid" tool to catalog.json (HQ Tools). Safe to re-run.  Run:  python bridge/add_gridpeople_tool.py"""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.grid_people", None)

T["dse.grid_people"] = {
    "label": "Grids: find first name, last name and work email for every row", "group": "Grow",
    "help": "For a grid of your Ledgers that has a website column: reads each business's own public website (free, polite, robots.txt respected) and fills First name, Last name, Work email and Email type. "
            "Columns the grid lacks are added; columns it has under similar names (First Name, Surname, Email) are used. A cell that already has a value is kept unless you pick every row. "
            "Email type says whether the address is the person's own (personal), the business's general one (role address), a gmail or similar (personal mailbox) or a guess. "
            "Nothing is guessed unless you tick the box, and a guess is only made when the domain receives mail: check guesses before sending. Tick Dry run first to see what would happen. "
            "It writes only into those cells of your own grid, through this PC's own connection to your account, in small batches, so Stop keeps what is done.",
    "script": "dse.py", "args": [{"lit": "grid"}, {"lit": "people"}, {"field": "grid"}, {"opt": "--from", "field": "website_column"}, {"opt": "--mode", "field": "mode"}, {"opt": "--limit", "field": "limit"},
                                 {"flag": "--guess", "field": "guess"}, {"flag": "--companies-house", "field": "companies_house"}, {"flag": "--dry", "field": "dry"}],
    "fields": [
        {"name": "grid", "label": "Grid (its id, its name, or Ledger/grid name)", "type": "text", "required": True, "max": 120},
        {"name": "website_column", "label": "Website column (empty = found automatically)", "type": "text", "required": False, "max": 60},
        {"name": "mode", "label": "Which rows", "type": "choice", "required": False, "default": "empty",
         "choices": [{"value": "empty", "label": "Rows with a website and an empty name or email"}, {"value": "all", "label": "Every row with a website (replaces what is there)"}]},
        {"name": "limit", "label": "Only the first N rows (empty = all of them)", "type": "int", "required": False, "min": 1, "max": 5000},
        {"name": "guess", "label": "Also guess a likely address when none is shown (marked guess: check before sending)", "type": "bool", "default": False},
        {"name": "companies_house", "label": "UK: where the website names nobody, ask Companies House for the director (needs your free key; adds a Name source column)", "type": "bool", "default": False},
        {"name": "dry", "label": "Dry run (show what would happen, change nothing)", "type": "bool", "default": False},
    ],
    "timeout_min": 240, "outputs": []}
T.pop("dse.directors", None)
T["dse.directors"] = {
    "label": "UK: find each business's director (first and last name) from Companies House", "group": "Find clients",
    "help": "For a list with a business name column: searches the official UK register (Companies House) for each business and adds the first and last name of its longest-serving active director, with the company and number it matched. "
            "It accepts only a match it is confident of (active company, same name apart from Ltd and Limited, not two equally good fits; the town breaks a tie) and leaves the rest empty: a wrong owner is worse than none. "
            "Sole traders and partnerships are not on the register. Needs your own free Companies House API key, set once on this PC (the run tells you how if it is missing); it is never sent to Citadel. "
            "About one request every 0.6 seconds, two per business at most.",
    "script": "dse.py", "args": [{"lit": "directors"}, {"field": "csv"}, {"opt": "--company-column", "field": "company_column"}, {"opt": "--city-column", "field": "city_column"}, {"opt": "--max", "field": "max"}],
    "fields": [{"name": "csv", "label": "List", "type": "file", "required": True, "glob": "my-lists/*.csv", "exclude": "directors"},
               {"name": "company_column", "label": "Business name column (empty = Company, Business or Name)", "type": "text", "required": False, "max": 60},
               {"name": "city_column", "label": "Town column (empty = City or Town)", "type": "text", "required": False, "max": 60},
               {"name": "max", "label": "Most businesses in this run", "type": "int", "min": 1, "max": 2000, "default": 200}],
    "timeout_min": 120, "outputs": [{"glob": "my-lists/*-directors-*.csv", "upload": True}]}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("grid_people tool added; tools:", len(T))
