"""One-off generator: adds the Presence edit render tool (Presence > Edit, "Make it on my PC") to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.presence_edit_render", None)

T["dse.presence_edit_render"] = {
    "label": "Presence: finish a video edited in Citadel", "group": "Grow",
    "help": ("Makes the finished MP4 of a video you edited in Presence > Edit, on this PC with ffmpeg: best for long or full-size videos. In the editor press 'Make it on my PC' and download the edit file. Put it in the my-video folder, "
             "and put the videos, pictures and sounds it uses in my-video too (pictures may be in my-pictures, sounds in my-audio) with exactly the names the editor shows. The tool checks every file is there first and tells you which are missing. "
             "It cuts and sizes every clip for the platform you chose, joins them, draws your text and captions on top, mixes your sounds under it, and saves the MP4 and a captions file (.srt) in my-video. "
             "'Quick draft' makes half size, which is faster, for checking. Nothing is posted: you upload the finished file yourself."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "edit-render"}, {"field": "project"}, {"flag": "--draft", "field": "draft"}],
    "fields": [{"name": "project", "label": "Edit file from Presence > Edit", "type": "file", "required": True, "glob": "my-video/*.edit.json"},
               {"name": "draft", "label": "Quick draft (half size, faster)", "type": "bool", "required": False, "default": False}],
    "timeout_min": 40, "outputs": [{"glob": "my-video/*.srt", "upload": True}]}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("presence tools:", sum(1 for k in T if k.startswith("dse.presence")), "tools:", len(T))
