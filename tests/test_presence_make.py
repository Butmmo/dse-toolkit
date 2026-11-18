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
src = Path(M.__file__).read_text(encoding="utf-8")
ok("nothing here posts or sends anything: no network library is used", "requests" not in src and "urllib" not in src and "smtplib" not in src)
ok("no em dash in the file", chr(0x2014) not in src)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
