"""One-off generator: adds the Engine context folder tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.context_add", "dse.context_scan", "dse.context_show", "dse.context_remove", "dse.context_suggest", "dse.context_adopt"):
    T.pop(k, None)

ENGINE = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
FOLDER = {"name": "folder", "label": "Folder (the full path, or a path inside the HQ folder)", "type": "text", "required": True, "max": 260}


def tool(label, help_, args, fields):
    return {"label": label, "group": "My engines", "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 3, "outputs": []}


NEVER = ("It never reads _private-keys, the encrypted memory vault, .env files, key files or files named like passwords. It never opens an encrypted file or an archive "
         "and never asks for a password: those are only listed as 'not read'. It hides anything that looks like a key, token or password. It never changes your folder. "
         "The summary stays on this PC.")
T["dse.context_add"] = tool(
    "Engine context: attach a folder of earlier work",
    "Tell an engine to read a folder (one you copied over, or one inside the HQ folder) so DBI-AI and your tools can pick the work up with you. It reads markdown, text, JSON, CSV and spreadsheets, "
    "story files first (README, CONTEXT, AGENTS, CLAUDE, HANDOVER), and saves a short summary. Only the folder's path is stored in the engine. A CONTEXT.md that says who the work is for, "
    "what the offer is, what is done and what comes next helps most. Lead-list files are noticed but never imported. " + NEVER,
    [{"lit": "context"}, {"field": "engine"}, {"opt": "--add", "field": "folder"}, {"opt": "--label", "field": "label"}],
    [ENGINE, FOLDER, {"name": "label", "label": "A short name for it (optional)", "type": "text", "required": False, "max": 60}])
T["dse.context_scan"] = tool(
    "Engine context: read the folders again",
    "Reads the engine's attached folders again, after you added or changed files, and refreshes the summary. " + NEVER,
    [{"lit": "context"}, {"field": "engine"}, {"flag": "--scan", "field": "scan"}],
    [ENGINE, {"name": "scan", "label": "Read them again now", "type": "bool", "default": True}])
T["dse.context_show"] = tool(
    "Engine context: show what it understood",
    "Shows the folders attached to an engine and the summary the tools use: the story files, the other files, which CSVs look like lead lists, the prices, niche, offer and goal lines it found, and what it did not read and why.",
    [{"lit": "context"}, {"field": "engine"}, {"flag": "--show", "field": "show"}],
    [ENGINE, {"name": "show", "label": "Show it", "type": "bool", "default": True}])
T["dse.context_remove"] = tool(
    "Engine context: detach a folder",
    "Stops the engine reading a folder. Your folder itself is never touched or deleted. Say the folder's path or the short name you gave it.",
    [{"lit": "context"}, {"field": "engine"}, {"opt": "--remove", "field": "folder"}],
    [ENGINE, {**FOLDER, "label": "The folder's path or short name"}])
T["dse.context_suggest"] = tool(
    "Engine context: what the folders suggest",
    "Reads the engine's summary and suggests settings: the cities found in your lead lists, the niche, offer, goal and price lines, and which lead lists you could bring in. It changes nothing: you decide, and edit the engine in My engines. The summary stays on this PC.",
    [{"lit": "context"}, {"field": "engine"}, {"flag": "--suggest", "field": "suggest"}],
    [ENGINE, {"name": "suggest", "label": "Suggest", "type": "bool", "default": True}])
T["dse.context_adopt"] = tool(
    "Engine context: bring a lead list in from the folder",
    "Brings a CSV lead list from an attached folder into the engine, the way that engine takes its leads: a Go-to-Market engine gets it in its imports, an Authority engine in its pasted experts, a Revenue or Ascent engine gets the websites added to its seed list (new ones only, up to 500), and an engine that finds its own leads keeps a copy for reference without changing its settings. Leave the box off to preview exactly what would happen. Your original file is only ever copied from, never changed or moved.",
    [{"lit": "context"}, {"field": "engine"}, {"opt": "--adopt", "field": "file"}, {"flag": "--apply", "field": "apply"}],
    [ENGINE, {"name": "file", "label": "The lead list, as shown by 'what the folders suggest' (for example Studio work:leads.csv)", "type": "text", "required": True, "max": 260},
     {"name": "apply", "label": "Do it now (leave off to preview)", "type": "bool", "default": False}])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
