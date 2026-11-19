"""One-off generator: adds the Presence captions tool (captions from a voiceover, for Presence > Edit) to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
T.pop("dse.presence_captions", None)

T["dse.presence_captions"] = {
    "label": "Presence: captions from a voiceover", "group": "Grow",
    "help": ("Listens to a voiceover (or the sound of a video) on this PC and writes a captions file (.srt) and the same captions as a .captions.json with the real time of every word, ready for Presence > Edit: press 'Captions file' there and the words appear on the video at the right moments (choose the .json to let 'Light each word as it is spoken' follow the voice exactly). "
             "Put the voiceover in the my-audio folder. It uses faster-whisper, a free speech-to-text program that runs on this PC, so nothing is uploaded; the first run downloads its model (about 145 MB) once. "
             "It needs a one-time setup: run 'python dse.py presence captions --setup' to see the three steps. The words are grouped into short captions (a few words at a time, breaking at full stops and pauses). "
             "Always read the captions and fix mistakes before posting: speech-to-text gets names, accents and noisy recordings wrong. English only for now."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "captions"}, {"field": "media"}, {"flag": "--model", "field": "model"}],
    "fields": [{"name": "media", "label": "Voiceover (a sound or video file)", "type": "file", "required": True, "glob": "my-audio/*"},
               {"name": "model", "label": "Accuracy", "type": "choice", "required": False, "default": "base.en",
                "choices": [{"value": "tiny.en", "label": "Fastest (tiny, less accurate)"}, {"value": "base.en", "label": "Balanced (base, recommended)"}, {"value": "small.en", "label": "Most accurate (small, slower, 480 MB model)"}]}],
    "timeout_min": 30, "outputs": [{"glob": "my-audio/*.srt", "upload": True}, {"glob": "my-audio/*.captions.json", "upload": True}]}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("presence tools:", sum(1 for k in T if k.startswith("dse.presence")), "tools:", len(T))
