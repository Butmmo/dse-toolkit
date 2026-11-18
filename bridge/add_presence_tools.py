"""One-off generator: adds the Presence tools (research for content, graphics, video) to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.presence_insights", "dse.presence_graphic", "dse.presence_video", "dse.presence_carousel", "dse.presence_voice_setup"):
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

LINE = r"[^\x00-\x1f-][^\x00-\x1f]*"
T["dse.presence_graphic"] = {
    "label": "Presence: make a picture for a post", "group": "Grow",
    "help": ("Makes one finished picture in the Citadel colours (ink, cream or gold) from your words: a quote, a big number or phrase (stat), a tip or a carousel cover, in post, square, story, landscape or "
             "thumbnail size. You can put your own picture behind the words (it is darkened so the words stay readable) and your logo top left: put them in the my-pictures folder first. The words are "
             "fitted so nothing runs off the edge. The PNG appears in Presence > Studio under 'Made by your PC', and in the my-graphics folder. Nothing is posted: you post it yourself."),
    "script": "dse.py",
    "args": [{"lit": "presence"}, {"lit": "graphic"}, {"opt": "--layout", "field": "layout"}, {"opt": "--headline", "field": "headline"}, {"opt": "--body", "field": "body"}, {"opt": "--kicker", "field": "kicker"},
             {"opt": "--footer", "field": "footer"}, {"opt": "--size", "field": "size"}, {"opt": "--theme", "field": "theme"}, {"opt": "--picture", "field": "picture"}, {"opt": "--logo", "field": "logo"}],
    "fields": [
        {"name": "layout", "label": "Layout", "type": "choice", "required": True, "default": "quote", "choices": [
            {"value": "quote", "label": "Quote or statement"}, {"value": "stat", "label": "Big number or phrase (stat)"}, {"value": "tip", "label": "Tip"}, {"value": "cover", "label": "Carousel cover"}]},
        {"name": "headline", "label": "The main words (a number for a stat)", "type": "text", "required": True, "max": 200, "pattern": LINE},
        {"name": "body", "label": "Smaller words under it (optional)", "type": "text", "required": False, "max": 300, "pattern": LINE},
        {"name": "kicker", "label": "Small label above (optional, for example: What I found)", "type": "text", "required": False, "max": 40, "pattern": LINE},
        {"name": "footer", "label": "Your name or handle (optional)", "type": "text", "required": False, "max": 60, "pattern": LINE},
        {"name": "size", "label": "Size", "type": "choice", "required": True, "default": "post", "choices": [
            {"value": "post", "label": "Post or carousel slide, portrait 1080x1350"}, {"value": "square", "label": "Square 1080x1080"}, {"value": "story", "label": "Story or reel cover 1080x1920"},
            {"value": "landscape", "label": "Landscape 1920x1080"}, {"value": "thumb", "label": "Video thumbnail 1280x720"}]},
        {"name": "theme", "label": "Colours", "type": "choice", "required": True, "default": "ink", "choices": [
            {"value": "ink", "label": "Ink (dark with gold)"}, {"value": "cream", "label": "Cream (light)"}, {"value": "gold", "label": "Gold"}]},
        {"name": "picture", "label": "Your picture behind the words (optional)", "type": "file", "required": False, "glob": "my-pictures/*"},
        {"name": "logo", "label": "Your logo (optional)", "type": "file", "required": False, "glob": "my-pictures/*"}],
    "timeout_min": 2, "outputs": [{"glob": "my-graphics/*.png", "upload": True}]}

T["dse.presence_video"] = {
    "label": "Presence: make a video from a project file", "group": "Grow",
    "help": ("Turns a video project file into an MP4 with ffmpeg. The project (made in Presence > Studio, 'Download video project', then put in the my-video folder) lists scenes: the words on screen, your "
             "own picture if you have one, a voiceover line and the seconds. Each scene becomes a card that moves slowly, the voiceover is spoken with the Windows voice if the project asks for it, and "
             "the scenes are joined into one video with a captions file (.srt) next to it. Find both in the my-video folder, check them, and upload them yourself. Nothing is posted."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "video"}, {"field": "project"}],
    "fields": [{"name": "project", "label": "Video project", "type": "file", "required": True, "glob": "my-video/*.json"}],
    "timeout_min": 20, "outputs": [{"glob": "my-video/*.srt", "upload": True}]}

T["dse.presence_carousel"] = {
    "label": "Presence: make every carousel slide at once", "group": "Grow",
    "help": ("Turns a carousel project into every slide as a finished PNG in one go: a cover, one slide per point and a last slide with your name, in the Citadel colours, with your picture and logo if the project names them. "
             "The project comes from Presence > Studio ('Carousel project (for your PC)'): put the file in the my-carousel folder of the toolkit first. The slides appear in Presence > Studio under 'Made by your PC' "
             "and in the my-graphics folder. Nothing is posted: you post them in order yourself."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "carousel"}, {"field": "project"}],
    "fields": [{"name": "project", "label": "Carousel project", "type": "file", "required": True, "glob": "my-carousel/*.json"}],
    "timeout_min": 3, "outputs": [{"glob": "my-graphics/*.png", "upload": True}]}

T["dse.presence_voice_setup"] = {
    "label": "Presence: install the free Kokoro voice", "group": "Grow",
    "help": ("One-time setup of Kokoro, a free, natural-sounding AI voice that runs on your own PC (no account, no per-use cost, and nothing is sent anywhere once it is installed). It installs two small packages "
             "and downloads the voice model (about 330 MB) from the project's official release page, so it takes a few minutes. Then choose 'Kokoro' as the voice in a Studio video project. Safe to run again: "
             "it skips what is already there."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "voice-setup"}], "fields": [], "timeout_min": 30, "outputs": []}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("presence tools:", sum(1 for k in T if k.startswith("dse.presence")), "tools:", len(T))
