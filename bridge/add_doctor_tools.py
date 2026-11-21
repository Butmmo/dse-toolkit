"""One-off generator: the System check tool in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
c["tools"]["dse.doctor"] = {
    "label": "System check: what is on, what is missing, and the fix", "group": "Setup",
    "help": "Checks this PC and your Citadel database and tells you, in plain words, what is working, what needs a fix and exactly what to do: is the runner running and up to date with GitHub, how to safely update the toolkit, which database updates (SQL files) have not been run, which background helpers have stalled or failed, and whether the Voices library, the business-data token, Ollama and the Python packages are in place. It changes nothing and sends nothing.",
    "script": "dse.py", "args": [{"lit": "doctor"}], "fields": [], "timeout_min": 3, "outputs": []}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(c["tools"]), "tools")
