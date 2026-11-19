"""One-off generator: adds the Presence tools (research for content, graphics, video) to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.presence_insights", "dse.presence_graphic", "dse.presence_video", "dse.presence_carousel", "dse.presence_voice_setup", "dse.presence_blender_setup", "dse.presence_connect", "dse.presence_accounts", "dse.presence_post", "dse.presence_trends", "dse.presence_context", "dse.presence_brand"):
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
    "help": ("Makes one finished picture in one of eight looks (ink, cream, gold, midnight, sage, blush, terracotta, mono) from your words: a quote, a big number or phrase (stat), a tip or a carousel cover, in post, square, story, landscape or "
             "thumbnail size. You can put your own picture behind the words (it is darkened so the words stay readable) and your logo top left: put them in the my-pictures folder first. The words are "
             "fitted so nothing runs off the edge. The PNG appears in Presence > Studio under 'Made by your PC', and in the my-graphics folder. Nothing is posted: you post it yourself."),
    "script": "dse.py",
    "args": [{"lit": "presence"}, {"lit": "graphic"}, {"opt": "--layout", "field": "layout"}, {"opt": "--headline", "field": "headline"}, {"opt": "--body", "field": "body"}, {"opt": "--kicker", "field": "kicker"},
             {"opt": "--footer", "field": "footer"}, {"opt": "--size", "field": "size"}, {"opt": "--theme", "field": "theme"}, {"opt": "--picture", "field": "picture"}, {"opt": "--logo", "field": "logo"}],
    "fields": [
        {"name": "layout", "label": "Layout", "type": "choice", "required": True, "default": "quote", "choices": [
            {"value": "quote", "label": "Quote or statement"}, {"value": "stat", "label": "Big number or phrase (stat)"}, {"value": "tip", "label": "Tip"}, {"value": "cover", "label": "Carousel cover"},
            {"value": "question", "label": "Question"}, {"value": "myth", "label": "Myth and fact (headline = the myth, smaller words = the fact)"}]},
        {"name": "headline", "label": "The main words (a number for a stat)", "type": "text", "required": True, "max": 200, "pattern": LINE},
        {"name": "body", "label": "Smaller words under it (optional)", "type": "text", "required": False, "max": 300, "pattern": LINE},
        {"name": "kicker", "label": "Small label above (optional, for example: What I found)", "type": "text", "required": False, "max": 40, "pattern": LINE},
        {"name": "footer", "label": "Your name or handle (optional)", "type": "text", "required": False, "max": 60, "pattern": LINE},
        {"name": "size", "label": "Size", "type": "choice", "required": True, "default": "post", "choices": [
            {"value": "post", "label": "Post or carousel slide, portrait 1080x1350"}, {"value": "square", "label": "Square 1080x1080"}, {"value": "story", "label": "Story or reel cover 1080x1920"},
            {"value": "landscape", "label": "Landscape 1920x1080"}, {"value": "thumb", "label": "Video thumbnail 1280x720"}]},
        {"name": "theme", "label": "Colours", "type": "choice", "required": True, "default": "ink", "choices": [
            {"value": "ink", "label": "Ink (dark with gold)"}, {"value": "cream", "label": "Cream (light)"}, {"value": "gold", "label": "Gold"}, {"value": "midnight", "label": "Midnight (deep blue)"}, {"value": "sage", "label": "Sage (soft green)"},
            {"value": "blush", "label": "Blush (soft pink)"}, {"value": "terracotta", "label": "Terracotta (warm clay)"}, {"value": "mono", "label": "Mono (black on white)"}]},
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

T["dse.presence_blender_setup"] = {
    "label": "Presence: install Blender for solid 3D videos", "group": "Grow",
    "help": ("One-time setup of Blender, the free open-source 3D program, for Presence's faceless videos. It downloads the official portable Blender zip (about 400 MB) from download.blender.org, "
             "checks it against the checksum Blender publishes next to it, and unpacks it into the toolkit's blender folder. Then, in a Studio video project, choose 'Draw the scenes in 3D with Blender': "
             "each scene becomes real 3D text in your colours with a slowly moving camera, joined with your voice and captions. A 3D video takes a few minutes longer to make than a normal one. If Blender is "
             "missing or a scene fails, that scene uses the normal card, so a video is never lost. Safe to run again. Nothing is sent anywhere."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "blender-setup"}], "fields": [], "timeout_min": 30, "outputs": []}

T["dse.presence_voice_setup"] = {
    "label": "Presence: install the free Kokoro voice", "group": "Grow",
    "help": ("One-time setup of Kokoro, a free, natural-sounding AI voice that runs on your own PC (no account, no per-use cost, and nothing is sent anywhere once it is installed). It installs two small packages "
             "and downloads the voice model (about 330 MB) from the project's official release page, so it takes a few minutes. Then choose 'Kokoro' as the voice in a Studio video project. Safe to run again: "
             "it skips what is already there."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "voice-setup"}], "fields": [], "timeout_min": 30, "outputs": []}

ACC = r"[a-z0-9][a-z0-9-]{1,30}"
T["dse.presence_connect"] = {
    "label": "Presence: connect an account to post from", "group": "Grow",
    "help": ("Connects ONE of your own accounts so Presence can post your finished content to it, only when you approve each post. A small window on this PC asks for the secret (hidden as you type): for LinkedIn, an access token "
             "with the w_member_social permission from your own LinkedIn developer app (add the 'Share on LinkedIn' product; the token also needs openid and profile so your member id can be read); for Discord, the webhook "
             "address of a channel in a server you manage (channel settings, Integrations, Webhooks). The secret stays on this PC: it is never typed into Citadel, never sent to Citadel, never shown or logged, and sent only to "
             "LinkedIn or Discord. Name each account (for example orlando-linkedin) so each business (Function) can post to its own. Nothing is posted by connecting."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "publish"}, {"lit": "connect"}, {"field": "platform"}, {"field": "account"}],
    "fields": [{"name": "platform", "label": "Platform", "type": "choice", "required": True, "choices": [{"value": "linkedin", "label": "LinkedIn (your own profile)"}, {"value": "discord", "label": "Discord (a channel webhook)"}]},
               {"name": "account", "label": "A short name for this account (letters, digits, dashes)", "type": "text", "required": True, "max": 31, "pattern": ACC}],
    "timeout_min": 10, "outputs": []}

T["dse.presence_accounts"] = {
    "label": "Presence: which accounts are connected", "group": "Grow",
    "help": "Lists the accounts connected on this PC for posting (the platform and the name you gave each, never a token or a webhook address).",
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "publish"}, {"lit": "accounts"}], "fields": [], "timeout_min": 1, "outputs": []}

T["dse.presence_post"] = {
    "label": "Presence: preview or post a finished piece to your account", "group": "Grow",
    "help": ("Takes a post file from Presence > Studio ('Post file (for your PC)', saved in the my-posts folder) and shows you EXACTLY what would be posted, to which account. Leave the approve box empty to preview. "
             "To post it, type the word POST in the approve box and run it again: only then is ONE new post made on the account you connected, through LinkedIn's or Discord's official programme. At most 3 posts a day "
             "per account, at least 30 minutes apart, never the same text twice, and never a piece with a [bracket] left in it. There is no code anywhere for messages, comments, follows or likes. A record "
             "(no secrets) appears in Presence > Studio so you can mark the piece posted."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "publish"}, {"lit": "post"}, {"field": "project"}, {"opt": "--approve", "field": "approve"}],
    "fields": [{"name": "project", "label": "Post file", "type": "file", "required": True, "glob": "my-posts/*.json", "exclude": r"\.posted\.json$"},
               {"name": "approve", "label": "Type POST here to really post it (empty = preview only)", "type": "text", "required": False, "max": 4, "pattern": "POST"}],
    "timeout_min": 3, "outputs": [{"glob": "my-posts/*.posted.json", "upload": True}]}

T["dse.presence_trends"] = {
    "label": "Presence: what is in the news for your market", "group": "Grow",
    "help": ("Reads ONE public news feed (Google News search) for the words you give and keeps the newest headlines of the last 7 days, with their publisher and date, as trend prompts for your content: react with your own "
             "useful view and say where the news came from. Only headlines, publishers and dates are kept: no article, website or social account is opened. The result appears in Presence > Research. Nothing is posted."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "trends"}, {"field": "query"}, {"field": "region"}],
    "fields": [{"name": "query", "label": "Your market in a few words (for example: dentists marketing)", "type": "text", "required": True, "max": 80, "pattern": r"[A-Za-z0-9 ,.'&/-]{3,80}"},
               {"name": "region", "label": "News region", "type": "choice", "required": True, "default": "us", "choices": [{"value": "us", "label": "United States"}, {"value": "uk", "label": "United Kingdom"}, {"value": "ca", "label": "Canada"}, {"value": "au", "label": "Australia"}]}],
    "timeout_min": 2, "outputs": [{"glob": "my-lists/*-trends.json", "upload": True}]}

T["dse.presence_context"] = {
    "label": "Presence: find the social media plan already in an engine's folder", "group": "Grow",
    "help": ("A Presence Function linked to an engine inherits that engine's folders. This reads them (read-only, with the same safety rules as the engine context folders: never keys, the vault, .env or password files, "
             "never archives or encrypted files; anything that looks like a secret is hidden) and looks for what you may already have for social media: a content plan or calendar, posting schedule, brand voice notes, "
             "hashtags, post ideas and drafts, notes from an AI chat. It keeps short findings only (platforms, account handles, the rhythm, themes, voice, hashtags, goals, ideas with the file they came from) and writes "
             "questions for you in Presence > Earlier plan: how to bring each finding in. Rules cannot understand every kind of plan, so with the AI switch on (the default) this PC's own AI also reads the start of the strongest files and adds a short summary and up to three questions of its own; if Ollama is off you still get the reading by rules. It changes nothing and decides nothing."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "context"}, {"field": "engine"}, {"flag": "--ai", "field": "ai"}],
    "fields": [{"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []},
               {"name": "ai", "label": "Also let my PC's own AI (Ollama, free, nothing leaves the PC) read it and ask its own questions", "type": "bool", "required": False, "default": True}],
    "timeout_min": 5, "outputs": [{"glob": "my-lists/*-presence-context.json", "upload": True}]}

T["dse.presence_brand"] = {
    "label": "Presence: find my brand art (logos, icons, fonts, colours)", "group": "Grow",
    "help": ("Looks, read-only, in the my-brand folder of this toolkit (put your logo files there) and, if you choose an engine, in that engine's folders (files in a folder called brand, logo or identity, and pictures "
             "or fonts named like a logo, icon, avatar, profile or wordmark) with the same safety rules as the engine context folders: never keys, the vault, .env or password files, never archives or encrypted files. "
             "It keeps SVG files as text, pictures shrunk to 640 px, font names (and small font files), the brand colours and fonts named in brand notes, and lines about where the logo goes. "
             "Presence > Brand kit then adds what is new, updates what changed, and never changes what you set by hand. Nothing is changed, moved, deleted or posted."),
    "script": "dse.py", "args": [{"lit": "presence"}, {"lit": "brand"}, {"field": "engine"}],
    "fields": [{"name": "engine", "label": "Engine (leave empty to look only in the my-brand folder)", "type": "choice", "required": False, "choices_from": "engines", "choices": []}],
    "timeout_min": 5, "outputs": [{"glob": "my-lists/*-presence-brand.json", "upload": True}]}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("presence tools:", sum(1 for k in T if k.startswith("dse.presence")), "tools:", len(T))
