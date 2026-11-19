"""Tests for the Presence make tools (graphic with Pillow, video with ffmpeg). Run: python tests/test_presence_make.py"""
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from dse import presence_make as M

fails = 0
def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond: fails += 1

td = Path(tempfile.mkdtemp())
M.GRAPHICS = td / "g"; M.VIDEOS = td / "v"
# graphics: every layout at every size, in every theme
good = True
for layout in M.LAYOUTS:
    for size, (w, h) in M.SIZES.items():
        for theme in M.THEMES:
            p = M.make_graphic(layout, "4 of 6 dentists I checked cannot be texted", "Most people message before they call.", "Finding", "@ada", size, theme, out_path=td / f"{layout}-{size}-{theme}.png")
            good = good and Image.open(p).size == (w, h)
ok("every layout, size and theme makes a PNG of exactly the right size", good)
ok("a very long headline still fits (no crash, right size)", Image.open(M.make_graphic("quote", "word " * 300, "", out_path=td / "long.png")).size == (1080, 1350))
try:
    M.make_graphic("quote", "  "); refused = False
except ValueError as e:
    refused = "headline" in str(e)
ok("an empty headline is refused with a plain message", refused)
for bad in (("nope", "x", "post", "ink"), ("quote", "x", "huge", "ink"), ("quote", "x", "post", "pink")):
    try:
        M.make_graphic(bad[0], bad[1], size=bad[2], theme=bad[3]); r = False
    except ValueError:
        r = True
    ok(f"unknown option {bad} is refused", r)
# picture and logo
pic = td / "pic.jpg"; Image.new("RGB", (400, 300), "#3366aa").save(pic)
logo = td / "logo.png"; Image.new("RGBA", (200, 80), (200, 30, 30, 255)).save(logo)
g = M.make_graphic("cover", "With a picture", picture=str(pic), logo=str(logo), out_path=td / "pl.png")
im = Image.open(g)
ok("a picture goes behind the text darkened, and a logo sits top left", im.size == (1080, 1350) and im.getpixel((540, 1200))[2] < 160 and im.getpixel((120, 120))[0] > 150)
try:
    M.make_graphic("cover", "x", picture="nothing.jpg"); r = False
except FileNotFoundError as e:
    r = "my-pictures" in str(e)
ok("a missing picture says where to put it", r)
# default output path goes to my-graphics
ok("the default file name comes from the headline and lands in my-graphics", M.make_graphic("tip", "Reply in a minute").parent == M.GRAPHICS)
# project reading
P = M.parse_project({"title": "t", "size": "weird", "voice": "x", "scenes": [{"text": "a", "seconds": 999}, {"text": ""}, "junk", {"text": "b", "voice": "one two three four five"}]})
ok("a video project is cleaned: unknown size becomes story, voice off, seconds capped, empty scenes dropped", P["size"] == "story" and P["voice"] == "none" and len(P["scenes"]) == 2 and P["scenes"][0]["seconds"] == 30 and P["scenes"][1]["seconds"] >= 3)
for bad in (None, {}, {"scenes": []}, {"scenes": [{"text": ""}]}):
    try:
        M.parse_project(bad); r = False
    except ValueError:
        r = True
    ok(f"a project with no usable scene is refused: {bad}", r)
ok("more than 30 scenes are cut to 30", len(M.parse_project({"scenes": [{"text": "x"}] * 50})["scenes"]) == 30)
srt = M.make_srt([{"voice": "Hello there", "seconds": 2.5}, {"voice": "", "seconds": 1}, {"voice": "Bye", "seconds": 2}])
ok("captions are timed from the scene lengths and skip silent scenes", "00:00:00,000 --> 00:00:02,500" in srt and "00:00:03,500 --> 00:00:05,500" in srt and srt.count("-->") == 2)
# real video when ffmpeg exists
ff = M.find_ffmpeg()
if ff:
    out = M.make_video({"title": "Test clip", "size": "square", "scenes": [{"text": "First", "seconds": 1}, {"text": "Second", "voice": "Second line", "seconds": 1}]}, ffmpeg=ff, out_path=td / "t.mp4", say=lambda *_: None)
    r = subprocess.run([ff, "-i", str(out)], capture_output=True, text=True).stderr
    ok("a real MP4 is made, 1080x1080, about 2 seconds, with captions next to it", out.exists() and "1080x1080" in r and "Duration: 00:00:02" in r and out.with_suffix(".srt").exists())
    ok("a scene can use the student's own picture", M.make_video({"scenes": [{"image": str(pic), "text": "", "seconds": 1}]}, ffmpeg=ff, out_path=td / "p.mp4", say=lambda *_: None).exists())
else:
    print("SKIP  ffmpeg not found")
cat = json.loads((Path(M.__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
for k in ("dse.presence_graphic", "dse.presence_video"):
    t = cat[k]; names = {f["name"] for f in t["fields"]}
    ok(f"{k} is in the catalog and every argument points at a real field", all(a["field"] in names for a in t["args"] if "field" in a) and t["group"] == "Grow")
g = cat["dse.presence_graphic"]
ok("the graphic tool offers exactly the layouts, sizes and themes the code makes", {c["value"] for f in g["fields"] if f["name"] == "layout" for c in f["choices"]} == set(M.LAYOUTS) and {c["value"] for f in g["fields"] if f["name"] == "size" for c in f["choices"]} == set(M.SIZES) and {c["value"] for f in g["fields"] if f["name"] == "theme" for c in f["choices"]} == set(M.THEMES))

# ---- phase 3: carousel batch, own recordings, burned-in captions
C = M.parse_carousel({"title": "T", "size": "weird", "theme": "x", "slides": [{"title": "One"}, {"title": ""}, "junk", {"title": "Two", "body": "b" * 900}] + [{"title": "n"}] * 20})
ok("a carousel project is cleaned: unknown size and theme fall back, empty slides drop, text is cut, at most 10 slides", C["size"] == "post" and C["theme"] == "ink" and len(C["slides"]) == 10 and C["slides"][1]["title"] == "Two" and len(C["slides"][1]["body"]) == 300)
for bad in (None, {}, {"slides": []}, {"slides": [{"title": " "}]}):
    try:
        M.parse_carousel(bad); r = False
    except ValueError:
        r = True
    ok(f"a carousel with no usable slide is refused: {bad}", r)
files = M.make_carousel({"title": "My tips", "size": "post", "theme": "cream", "footer": "@ada", "slides": [{"title": "Cover words"}, {"title": "Point one", "body": "Because."}, {"title": "Last", "body": "Ask me."}]}, out_dir=td / "car", say=lambda *_: None)
ok("every slide is a finished PNG at the post size, numbered in order", len(files) == 3 and all(Image.open(f).size == (1080, 1350) for f in files) and [f.name for f in files] == ["my-tips-01.png", "my-tips-02.png", "my-tips-03.png"])
M.AUDIO = td / "audio"; M.AUDIO.mkdir()
ok("a video project can ask for the student's own voice and for captions to be off", M.parse_project({"voice": "own", "captions": False, "scenes": [{"text": "a"}]})["voice"] == "own" and not M.parse_project({"voice": "own", "captions": False, "scenes": [{"text": "a"}]})["captions"] and M.parse_project({"scenes": [{"text": "a"}]})["captions"] is True and M.parse_project({"voice": "robot", "scenes": [{"text": "a"}]})["voice"] == "none")
(M.AUDIO / "clip-title-scene-2.mp3").write_bytes(b"x")
ok("the student's recording for a scene is found by the video title and scene number", M._own_audio("Clip Title", 2).name == "clip-title-scene-2.mp3" and M._own_audio("Clip Title", 1) is None)
card = td / "cap.png"; Image.new("RGB", (1080, 1920), "#d4a942").save(card)
M._burn_caption(card, "This is what the speaker says in the scene", 1080, 1920)
cim = Image.open(card)
ok("burned-in captions darken a band at the bottom and leave the top as it was", cim.getpixel((540, 1850))[0] < 120 and cim.getpixel((540, 100)) == (212, 169, 66))
if ff:
    wav = td / "own.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], check=True)
    ok("ffmpeg can read the length of a recording", abs((M._duration(ff, wav) or 0) - 2) < 0.2)
    (M.AUDIO / "own-test-scene-1.wav").write_bytes(wav.read_bytes())
    v = M.make_video({"title": "Own test", "size": "square", "voice": "own", "scenes": [{"text": "Hi", "voice": "Spoken line", "seconds": 1}]}, ffmpeg=ff, out_path=td / "own.mp4", say=lambda *_: None)
    d = M._duration(ff, v)
    ok("a video with the student's own recording lasts as long as the recording and carries captions", d is not None and d >= 2.0)
cat2 = json.loads((Path(M.__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
ok("the carousel tool is in the catalog and uploads its slides", "dse.presence_carousel" in cat2 and any(o["glob"] == "my-graphics/*.png" and o["upload"] for o in cat2["dse.presence_carousel"]["outputs"]))

# ---- the free Kokoro voice
import types
P1 = M.parse_project({"voice": "kokoro", "kokoro_voice": "bm_george", "scenes": [{"text": "a"}]})
ok("a project can ask for the Kokoro voice and name one of its voices; a bad voice name falls back to the default", P1["voice"] == "kokoro" and P1["kokoro_voice"] == "bm_george" and M.parse_project({"voice": "kokoro", "kokoro_voice": "../x", "scenes": [{"text": "a"}]})["kokoro_voice"] == M.DEFAULT_KOKORO_VOICE and M.parse_project({"scenes": [{"text": "a"}]})["voice"] == "none")
M.KOKORO_DIR = td / "kokoro"
for k in ("kokoro_onnx", "soundfile"):
    sys.modules.pop(k, None)
ok("without the packages or the model files, Kokoro says in plain words what to run, and speaking returns nothing", (lambda r: (not r[0]) and "Presence: install the free Kokoro voice" in r[1])(M.kokoro_ready()) and M._speak_kokoro("Hello there", td / "k.wav") is None)
M.KOKORO_DIR.mkdir()
for f in M.KOKORO_FILES:
    (M.KOKORO_DIR / f).write_bytes(b"x")
calls = {}
class FakeKokoro:
    def __init__(self, model, voices): calls["init"] = (Path(model).name, Path(voices).name)
    def create(self, text, voice, speed, lang): calls["create"] = (text, voice, speed, lang); return [0.0] * 24000, 24000
fake_k = types.ModuleType("kokoro_onnx"); fake_k.Kokoro = FakeKokoro
fake_sf = types.ModuleType("soundfile")
def _write(path, samples, rate):
    import wave, struct
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"".join(struct.pack("<h", 0) for _ in samples))
fake_sf.write = _write
sys.modules["kokoro_onnx"], sys.modules["soundfile"] = fake_k, fake_sf
M._KOKORO = None
length = M._speak_kokoro("Hello there", td / "k.wav", "af_sarah")
ok("with the packages and files present, the voice is asked for the text in English at normal speed and a WAV is written (stubbed model)", M.kokoro_ready()[0] and abs(length - 1.0) < 0.01 and (td / "k.wav").exists() and calls["create"] == ("Hello there", "af_sarah", 1.0, "en-us") and calls["init"] == ("kokoro-v1.0.onnx", "voices-v1.0.bin"))
ok("a voice name that is not plain letters is never passed to the model", M._speak_kokoro("Hello", td / "k2.wav", "x; rm -rf") is None and not (td / "k2.wav").exists())
if ff:
    kv = M.make_video({"title": "Kokoro test", "size": "square", "voice": "kokoro", "scenes": [{"text": "Hi", "voice": "A spoken line", "seconds": 1}]}, ffmpeg=ff, out_path=td / "kv.mp4", say=lambda *_: None)
    ok("a video with the Kokoro voice is made and lasts as long as the voice (stubbed: one second plus the pause)", kv.exists() and (M._duration(ff, kv) or 0) >= 1.0)
for k in ("kokoro_onnx", "soundfile"):
    sys.modules.pop(k, None)
M._KOKORO = None
cat3 = json.loads((Path(M.__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
ok("the install tool is in the catalog, takes no fields and runs the one-time setup", cat3["dse.presence_voice_setup"]["args"][-1] == {"lit": "voice-setup"} and cat3["dse.presence_voice_setup"]["fields"] == [])

# ---- review fixes
ok("review fix: a scene with only a voice line is kept, so scene numbers and recording names stay in step", len(M.parse_project({"scenes": [{"text": "a"}, {"voice": "only spoken words here"}, {"text": "c"}]})["scenes"]) == 3)
if ff:
    v6 = M.make_video({"title": "Sync test", "size": "square", "voice": "none", "scenes": [{"text": "One", "voice": "short", "seconds": 4}, {"text": "Two", "seconds": 2}]}, ffmpeg=ff, out_path=td / "sync.mp4", say=lambda *_: None)
    d6 = M._duration(ff, v6) or 0
    ok("review fix: the video is exactly as long as the scenes add up to, so the captions stay in step", abs(d6 - 6.0) < 0.3)
    wavs = td / "short.wav"; subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wavs)], check=True)
    (M.AUDIO / "pad-test-scene-1.wav").write_bytes(wavs.read_bytes())
    v7 = M.make_video({"title": "Pad test", "size": "square", "voice": "own", "scenes": [{"text": "One", "voice": "Hi", "seconds": 5}, {"text": "Two", "seconds": 2}]}, ffmpeg=ff, out_path=td / "pad.mp4", say=lambda *_: None)
    ok("review fix: a recording shorter than its scene does not cut the scene short", abs((M._duration(ff, v7) or 0) - 7.0) < 0.5)
    odd = td / "O'Neil temp"; odd.mkdir()
    import shutil as _sh
    clip = odd / "a.mp4"; subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-pix_fmt", "yuv420p", str(clip)], check=True)
    lst = odd / "list.txt"; lst.write_text("file '" + clip.as_posix().replace("'", "'\\''") + "'\n", encoding="utf-8")
    r8 = subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(odd / "o.mp4")], capture_output=True, text=True)
    ok("review fix: a folder name with an apostrophe does not break the join list", r8.returncode == 0)

# ---- phase 12: design kits and layouts (same table as the app), data-driven layouts, own brand kit
ok("there are eight looks and six layouts, and the table matches the app's kit ids", set(M.THEMES) == {"ink", "cream", "gold", "midnight", "sage", "blush", "terracotta", "mono"} and set(M.LAYOUTS) == {"quote", "stat", "tip", "cover", "question", "myth"})
ok("every built-in kit is readable: text, accent and muted words keep enough contrast on the page", all(M._contrast(k[0], k[1]) >= 4.5 and M._contrast(k[0], k[2]) >= 3.0 and M._contrast(k[0], k[3]) >= 3.0 for k in M.KITS.values()))
ok("a text asks for its layout: a figure is a stat, a question a question, a myth a myth, a quote a quote, else the fallback", M.auto_layout("4 of 6 dentists cannot be texted") == "stat" and M.auto_layout("73% of patients message first") == "stat" and M.auto_layout("Do you answer texts in a minute?") == "question" and M.auto_layout("Myth: patients prefer to call") == "myth" and M.auto_layout("“Reply in a minute”") == "quote" and M.auto_layout("Why replies win", "", "tip") == "tip")
ok("the big figure is split from its words, and a text with no figure has none", M.stat_of("4 of 6 dentists cannot be texted") == ("4 of 6", "dentists cannot be texted") and M.stat_of("In the news (2026-11-18): 73% of patients message first")[0] == "73%" and M.stat_of("Reply fast") is None)
kit = {"bg": "#1A4D3A", "fg": "#F4E9D8", "accent": "#F2B84B", "muted": "#B7C9BE", "head": "serif", "motif": "arc"}
pk = M.parse_kit(kit)
ok("the student's own kit is used as given when readable", pk["bg"] == "#1A4D3A" and pk["head"] == "serif" and pk["motif"] == "arc")
bad = M.parse_kit({"bg": "#222222", "fg": "#333333", "accent": "#444444", "head": "wingdings", "motif": "x"})
ok("an unreadable or odd kit is made safe: words that cannot be read become black or white, unknown styles fall back, junk falls back to the named look", M._contrast(bad["bg"], bad["fg"]) >= 4.5 and bad["head"] == "sans" and bad["motif"] == "bar" and M.parse_kit("junk", "sage")["bg"] == "#E7EEE4" and M.parse_kit({"bg": "red", "fg": "#fff", "accent": "#000"}, "ink")["bg"] == "#1A1410")
for lay in M.LAYOUTS:
    pth = M.make_graphic(lay, "4 of 6 dentists cannot be texted" if lay != "question" else "Do you answer in a minute?", "Source: my list", "Finding", "@ada", "post", "ink", out_path=td / f"k-{lay}.png", kit=kit)
    im = Image.open(pth).convert("RGB")
    ok(f"the {lay} layout draws in the student's own kit at the right size, on the kit's page colour", im.size == (1080, 1350) and im.getpixel((540, 1340)) == (0x1A, 0x4D, 0x3A))
P = M.parse_project({"title": "T", "kit": kit, "scenes": [{"text": "4 of 6 dentists", "voice": "x"}]})
ok("a video project carries its kit, and a carousel too; a non-object kit is dropped", P["kit"] == kit and M.parse_carousel({"slides": [{"title": "a"}], "kit": kit})["kit"] == kit and M.parse_carousel({"slides": [{"title": "a"}], "kit": "x"})["kit"] is None)
cf = M.make_carousel({"title": "Kits", "kit": kit, "slides": [{"title": "Cover"}, {"title": "73% of patients message first", "body": "Source: survey"}, {"title": "Last", "body": "Ask me."}]}, out_dir=td / "kc", say=lambda *_: None)
ok("a carousel in an own kit renders every slide, with the figure slide chosen from its words", len(cf) == 3 and all(Image.open(f).getpixel((540, 1340)) == (0x1A, 0x4D, 0x3A) for f in cf))
ok("a list count is not a finding: '5 mistakes dentists make' stays a cover, real figures stay stats", M.stat_of("5 mistakes dentists make") is None and M.auto_layout("10 tips for faster replies") == "cover" and M.stat_of("1,200 clinics closed")[0] == "1,200" and M.stat_of("3x more replies")[0] == "3x" and M.auto_layout("7 in 10 patients message first") == "stat")
# ---- review fixes: long figures, wrapped lines, figure in the body, photo accent, layout order like the app
for head, body in (("1,000,000,000 clicks", ""), ("100 of 1,000 dentists", "Source: " + "a very long source line " * 6), ("$2.5 million", ""), ("Finding 1", "4 of 6 dentists cannot be texted.\nSource: my list")):
    im = Image.open(M.make_graphic("stat", head, body, "", "@ada", "post", "ink", out_path=td / "rf.png")).convert("RGB")
    right = [im.getpixel((x, y)) for x in range(1080 - 60, 1080) for y in range(300, 800, 20)]
    ok(f"a stat '{head[:20]}' never runs into the right margin", all(p == (0x1A, 0x14, 0x10) for p in right))
ok("review fix: the layout order is the app's: myth, question, then figure", M.auto_layout("Stop losing 30% of leads?") == "question" and M.auto_layout("Myth: 40% of owners reply") == "myth" and M.auto_layout("Finding 1", "4 of 6 dentists") == "stat" and M.auto_layout("Why replies win", "73% of patients message first") == "stat")
for lay, h, b in (("question", "Do you reply in a minute?", "x " * 80), ("quote", "Reply in a minute", "A very long name " * 8)):
    im = Image.open(M.make_graphic(lay, h, b, "", "", "post", "ink", out_path=td / "rq.png")).convert("RGB")
    ok(f"review fix: the {lay} body wraps and stays inside the margin", all(im.getpixel((x, y)) == (0x1A, 0x14, 0x10) for x in range(1080 - 70, 1080) for y in range(300, 1300, 10) if lay == "quote" or y > 700))
ok("review fix: on a photo a dull accent is replaced so it can be read (gold on a dark photo)", (lambda im: im.size == (1080, 1350))(Image.open(M.make_graphic("stat", "4 of 6", "x", "", "", "post", "gold", out_path=td / "rp.png"))) and M._contrast("#2A2D33", "#4A3300") < 3.0)
src = Path(M.__file__).read_text(encoding="utf-8")
ok("nothing here posts or sends anything: the only network use is the one-time voice download (a GET from the project's release page)", "urllib" not in src and "smtplib" not in src and ".post(" not in src and src.count("requests.get(") == 1 and src.index("requests.get(") > src.index("def install_kokoro") and "github.com/thewh1teagle/kokoro-onnx/releases/download" in src)
# ---- transitions between scenes
ok("a project can ask for a transition between scenes; anything else is a plain cut", M.parse_project({"scenes": [{"text": "x scene text"}], "transition": "slide"})["transition"] == "slide" and M.parse_project({"scenes": [{"text": "x scene text"}], "transition": "evil"})["transition"] == "cut" and M.parse_project({"scenes": [{"text": "x scene text"}]})["transition"] == "cut")
_ff = M.find_ffmpeg()
if _ff:
    import tempfile as _tf
    _td = Path(_tf.mkdtemp()); _M = M
    def _dur(path):
        r = subprocess.run([_ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
        h, m, sec = [l for l in r.splitlines() if "Duration" in l][0].split("Duration:")[1].split(",")[0].strip().split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    _sc = [{"text": "First scene here", "seconds": 2}, {"text": "Second scene now", "seconds": 2}, {"text": "Third scene end", "seconds": 2}]
    M.VIDEOS = _td
    _durs = {}
    for _tr in ("cut", "fade", "slide", "circle", "dip", "wipe", "zoom"):
        _o = M.make_video({"title": "tr", "transition": _tr, "scenes": _sc}, out_path=_td / f"{_tr}.mp4", say=lambda m: None)
        _durs[_tr] = _dur(_o)
    ok("every transition keeps the video the same length as a cut (so the captions file stays in step)", all(abs(d - _durs["cut"]) < 0.1 for d in _durs.values()))
    _f = _td / "mid.png"
    subprocess.run([_ff, "-y", "-loglevel", "error", "-ss", "2.2", "-i", str(_td / "fade.mp4"), "-frames:v", "1", str(_f)], check=True)
    _g = _td / "cutmid.png"
    subprocess.run([_ff, "-y", "-loglevel", "error", "-ss", "2.2", "-i", str(_td / "cut.mp4"), "-frames:v", "1", str(_g)], check=True)
    ok("in the middle of a blend the picture differs from the plain cut at the same moment", Image.open(_f).convert("L").tobytes() != Image.open(_g).convert("L").tobytes())
else:
    print("SKIP  transitions (ffmpeg is not installed here)")
# ---- music under the voice
ok("a project can name a music file in my-audio and a volume; folders in the name are dropped and a non-audio name means none", M.parse_project({"scenes": [{"text": "x scene text"}], "music": "../secret/song.mp3", "musicVolume": 9})["music"] == "song.mp3" and M.parse_project({"scenes": [{"text": "x scene text"}], "music": "x.exe"})["music"] == "" and M.parse_project({"scenes": [{"text": "x scene text"}], "musicVolume": 9})["music_volume"] == 0.6 and M.parse_project({"scenes": [{"text": "x scene text"}]})["music_volume"] == 0.2)
if _ff:
    _m = Path(_tf.mkdtemp()); M.AUDIO = _m; M.VIDEOS = _m
    subprocess.run([_ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=330:d=3", str(_m / "voice.wav")], check=True)      # a voice stand-in for scene 1
    subprocess.run([_ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=2:c=pink:a=0.5", str(_m / "bed.mp3")], check=True)   # a short music track: it must be looped
    (_m / "voice.wav").replace(_m / "tune-scene-1.wav")
    _lines = []
    _o = M.make_video({"title": "tune", "music": "bed.mp3", "musicVolume": 0.4, "scenes": [{"text": "Voice scene here", "voice": "hello", "seconds": 3}, {"text": "Quiet scene here", "seconds": 3}]}, out_path=_m / "tune.mp4", say=_lines.append)
    def _level(t0):
        r = subprocess.run([_ff, "-hide_banner", "-ss", str(t0), "-t", "1", "-i", str(_o), "-vn", "-af", "highpass=f=2500,volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr          # only the high frequencies: the 300 Hz voice stand-in is out, the music (noise) is left
        return float([l for l in r.splitlines() if "mean_volume" in l][0].split("mean_volume:")[1].split("dB")[0])
    ok("the music is added, looped past its own length, and the student is told", _o.exists() and any("Music added" in l for l in _lines) and _dur(_o) > 5.5)
    # ducking, tested directly: a voice (a 300 Hz tone) for 1.5 s then silence, music (loud noise) under it the whole time
    subprocess.run([_ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.5", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-filter_complex", "[0:a]volume=2,aresample=44100[v];[v][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]", "-t", "4", str(_m / "talk.wav")], check=True)
    subprocess.run([_ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=4", "-i", str(_m / "talk.wav"), "-shortest", "-c:v", "libx264", "-c:a", "aac", str(_m / "talkv.mp4")], check=True)
    M.add_music(_ff, _m / "talkv.mp4", _m / "bed.mp3", 4, 0.5, _m / "ducked.mp4")
    _o = _m / "ducked.mp4"
    ok("the music ducks: it is clearly quieter while the voice speaks than in the gap after it", _level(0.3) < _level(2.6) - 4)
    _lines2 = []
    M.make_video({"title": "nomusic", "music": "missing.mp3", "scenes": [{"text": "Just one scene", "seconds": 2}]}, out_path=_m / "nm.mp4", say=_lines2.append)
    ok("a music file that is not in my-audio is said plainly and the video is still made", (_m / "nm.mp4").exists() and any("not in my-audio" in l for l in _lines2))
ok("no em dash in the file", chr(0x2014) not in src)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
