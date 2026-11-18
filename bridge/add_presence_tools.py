"""One-off generator: adds the Presence tools (research for content, graphics, video) to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.presence_insights", "dse.presence_graphic", "dse.presence_video"):
    T.pop(k, None)

T["dse.presence_insights"] = {
    "label": "Presence: what to talk about, from a checked list", "group": "Grow",
    "help": ("Reads a list your HQ tools built (Foursquare Open Source Places, then the website problem check and the enrichment) and works out what that whole market is like: how many have no online "
             "booking, no text or chat, an old website, and which social platforms they link to. Then it writes content ideas, each with the real numbers behind it and where they came from, so you "
             "can say '6 of 6 dentists I checked in Orlando cannot be texted from their website' and mean it. The result is counts only: no business name, address, phone or email is in it. A list "
             "of fewer than 10 is called a small sample. The file appears in Presence > Research. Nothing is posted or sent."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "insights"}, {"field": "csv"}],
    "fields": [{"name": "csv", "label": "List", "type": "file", "required": True, "glob": "my-lists/*.csv"}],
    "timeout_min": 3, "outputs": [{"glob": "my-lists/*-insights.json", "upload": True}, {"glob": "my-lists/*-insights.md", "upload": True}]}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("presence tools:", sum(1 for k in T if k.startswith("dse.presence")), "tools:", len(T))
