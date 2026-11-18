"""Tests for Presence's Blender 3D scenes (dse/presence_blender.py, dse/blender_scene.py) and their place in the video tool. Run: python tests/test_presence_blender.py
The pure parts always run. The parts that need Blender or ffmpeg on this PC say SKIP when they are not there."""
import hashlib, io, json, os, subprocess, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import presence_blender as B
from dse import presence_make as M

fails = 0
def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond: fails += 1
def skip(name):
    print("SKIP  " + name)

td = Path(tempfile.mkdtemp())
kit = M.parse_kit(None, "midnight")

# ---- the scene as Blender needs it (pure)
sp = B.scene_spec("Do you answer texts in a minute?", kit, (540, 960), 36)
ok("a scene becomes one block of text in the kit's text colour and a small bar in its accent, on the kit's page colour, at the asked size and frame count", len(sp["blocks"]) == 1 and sp["blocks"][0]["color"] == kit["fg"] and sp["bar"]["color"] == kit["accent"] and sp["bg"] == kit["bg"] and sp["width"] == 540 and sp["height"] == 960 and sp["frames"] == 36 and sp["fps"] == 24 and sp["engine"] == "CYCLES")
st = B.scene_spec("4 of 6 dentists cannot be texted", kit, (540, 960), 24, stat=("4 of 6", "dentists cannot be texted"))
ok("a scene that leads with a figure draws the figure large in the accent colour with the rest under it", len(st["blocks"]) == 2 and st["blocks"][0]["text"] == "4 of 6" and st["blocks"][0]["color"] == kit["accent"] and st["blocks"][0]["size"] > st["blocks"][1]["size"] * 2 and st["blocks"][1]["color"] == kit["fg"])
long_ = B.scene_spec("word " * 60, kit, (540, 960), 12)
ok("long text is cut to 160 characters, wrapped to lines that fit the frame, and drawn smaller", len(long_["blocks"][0]["text"].replace("\n", " ")) <= 160 and "\n" in long_["blocks"][0]["text"] and long_["blocks"][0]["size"] < sp["blocks"][0]["size"] and max(len(l) for l in long_["blocks"][0]["text"].split("\n")) <= 40)
ok("odd input is harmless: empty text, a huge figure, an unknown move, zero frames", B.scene_spec("", kit, (540, 960), 0)["frames"] == 1 and B.scene_spec("x", kit, (540, 960), 5, move="spin")["move"] == "dolly" and len(B.scene_spec("x", kit, (540, 960), 5, stat=("1" * 40, "y"))["blocks"][0]["text"]) <= 14 and B.scene_spec(None, kit, (540, 960), 5)["blocks"][0]["text"].strip() == "")
ok("the headline font follows the kit (serif is Georgia when this PC has it) and the body is always sans", all(b["font"].endswith(".ttf") or b["font"] == "" for b in sp["blocks"]))

ok("a scene of 8 or more frames builds itself: the pieces arrive over about 0.7 s, a figure leans a little and settles, and a still or a very short scene has no intro", st["intro"] > 0 and st["intro"] <= st["frames"] // 2 and st["blocks"][0].get("tilt") and B.scene_spec("x", kit, (540, 960), 4)["intro"] == 0 and B.scene_spec("x", kit, (540, 960), 30, move="still")["intro"] == 0)

alone = B.scene_spec("4 of 6", kit, (540, 960), 24, stat=("4 of 6", ""))
ok("a figure with no words under it sits in the middle of the frame (not the top third) with its bar just under it", len(alone["blocks"]) == 1 and abs(alone["blocks"][0]["y"]) < 0.06 * (9 * 960 / 540) and alone["bar"]["y"] < alone["blocks"][0]["y"] and alone["bar"]["y"] > -2.5)

ok("draft quality uses 8 samples and high 24 (the draft was measured to look the same once compressed, a third faster)", B.SAMPLES == {"draft": 8, "high": 24})
seen = {}
_orig = B.scene_spec
def _spy(*a, **k):
    seen["samples"] = a[5] if len(a) > 5 else k.get("samples")
    return _orig(*a, **k)

# ---- finding Blender
old = os.environ.get("BLENDER")
fake = td / "myblender.exe"; fake.write_text("x")
os.environ["BLENDER"] = str(fake)
ok("the BLENDER environment variable wins when it points at a real file, and is ignored when it does not", B.find_blender() == fake and (os.environ.__setitem__("BLENDER", str(td / "nope.exe")) or B.find_blender() != td / "nope.exe"))
if old is None: os.environ.pop("BLENDER", None)
else: os.environ["BLENDER"] = old
ok("an unpacked Blender folder is found by its blender.exe", B._exe_in(td) is None and (lambda p: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text("x"), B._exe_in(td))[2] == p)(td / "blender-9.9.9-windows-x64" / "blender.exe"))

# ---- installing: checked against the published checksum, nothing outside its folder
def fake_zip(extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(f"blender-{B.VERSION}-windows-x64/blender.exe", "MZ")
        for k, v in (extra or {}).items(): z.writestr(k, v)
    return b.getvalue()
class Resp:
    def __init__(s, data, text=""): s.data, s.text = data, text
    def raise_for_status(s): pass
    def iter_content(s, n): yield s.data
    def __enter__(s): return s
    def __exit__(s, *a): return False
def getter(blob, sha):
    def g(url, **k):
        if url.endswith(".sha256"): return Resp(b"", f"{sha}  {B.ZIP}\n")
        return Resp(blob)
    return g
msgs = []
blob = fake_zip()
d1 = td / "inst1"
rc = B.install_blender(d1, say=msgs.append, get=getter(blob, hashlib.sha256(blob).hexdigest()))
ok("with a matching checksum the zip is unpacked, blender.exe is found, and the zip is removed", rc == 0 and B._exe_in(d1) is not None and not (d1 / "_download" / B.ZIP).exists())
msgs.clear(); rc = B.install_blender(d1, say=msgs.append, get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not download again")))
ok("running it again does not download anything", rc == 0 and any("already here" in m for m in msgs))
d2 = td / "inst2"; msgs.clear()
rc = B.install_blender(d2, say=msgs.append, get=getter(blob, "0" * 64))
ok("a download that does not match the published checksum is deleted and nothing is installed", rc == 1 and B._exe_in(d2) is None and not (d2 / "_download" / B.ZIP).exists() and any("does not match" in m for m in msgs))
d3 = td / "inst3"; evil = fake_zip({"../escape.txt": "x"}); msgs.clear()
rc = B.install_blender(d3, say=msgs.append, get=getter(evil, hashlib.sha256(evil).hexdigest()))
ok("a zip with a path outside its folder is refused whole", rc == 1 and not (td / "escape.txt").exists() and not (d3.parent / "escape.txt").exists())
d4 = td / "inst4"; msgs.clear()
rc = B.install_blender(d4, say=msgs.append, get=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
ok("with no network it says so in plain words and installs nothing", rc == 1 and any("Could not download" in m for m in msgs))
ok("no checksum line for the file means no install", (lambda m: (B.install_blender(td / "inst5", say=m.append, get=lambda url, **k: Resp(b"", "abc  other.zip\n")), any("will not install" in x for x in m))[1])([]))

# ---- the project and the video tool
P = M.parse_project({"scenes": [{"text": "x scene text"}], "engine": "blender", "quality": "high", "move": "drift"})
ok("a video project can ask for Blender, high quality and a camera move; anything else is the normal cards, draft quality and the dolly", P["engine"] == "blender" and P["quality"] == "high" and P["move"] == "drift" and (lambda q: q["engine"] == "cards" and q["quality"] == "draft" and q["move"] == "dolly")(M.parse_project({"scenes": [{"text": "x scene text"}], "engine": "evil", "quality": "x", "move": "spin"})))
ff = M.find_ffmpeg()
if ff:
    os.environ["BLENDER"] = str(td / "missing.exe")
    saved_find = B.find_blender; B.find_blender = lambda: None
    M.VIDEOS = td / "v"; lines = []
    out = M.make_video({"title": "fallback", "engine": "blender", "scenes": [{"text": "Do you answer texts in a minute?", "seconds": 1.5}]}, out_path=td / "fb.mp4", say=lines.append)
    B.find_blender = saved_find
    ok("with no Blender the video is still made, from the normal cards, and the student is told why", out.exists() and out.stat().st_size > 1000 and any("Blender was not used" in l and "not installed" in l for l in lines))
    if old is None: os.environ.pop("BLENDER", None)
    else: os.environ["BLENDER"] = old
else:
    skip("fallback to cards when Blender is missing (ffmpeg is not installed here)")

# ---- the real thing, when this PC has Blender
exe = B.find_blender()
if exe:
    from PIL import Image
    spec = B.scene_spec("Reply in a minute", kit, (270, 480), 2, samples=8)
    frames = B.render_scene(spec, td / "real")
    im = Image.open(frames[0]).convert("RGB")
    bgc = tuple(int(kit["bg"][i:i + 2], 16) for i in (1, 3, 5))
    ok("Blender draws the frames: two PNGs of the right size, the corners are the kit's page colour and the middle holds text pixels", len(frames) == 2 and im.size == (270, 480) and all(max(abs(a - b) for a, b in zip(im.getpixel(c), bgc)) <= 6 for c in ((2, 2), (267, 2), (2, 477), (267, 477))) and sum(1 for y in range(120, 400) if any(sum(abs(a - b) for a, b in zip(im.getpixel((x, y)), bgc)) > 40 for x in range(270))) >= 20)
    if ff:
        clip = B.frames_to_clip(ff, frames, 1.0, (270, 480), td / "c.mp4", 12)
        ok("the frames become a one-second clip", clip.exists() and clip.stat().st_size > 500)
        M.VIDEOS = td / "v2"; lines = []; B.scene_spec = _spy
        out = M.make_video({"title": "real3d", "engine": "blender", "quality": "draft", "theme": "midnight", "captions": True, "scenes": [{"text": "4 of 6 dentists cannot be texted", "voice": "Four of six.", "seconds": 1.5}]}, out_path=td / "r3.mp4", say=lines.append)
        B.scene_spec = _orig
        ok("the video tool asked for the draft sample count", seen.get("samples") == 8)
        ok("a whole video is made with a Blender scene, a caption band and a silent track, and the student is told the scene was drawn in 3D", out.exists() and out.stat().st_size > 1000 and any("drawn in 3D with Blender" in l for l in lines))
else:
    skip("Blender is not installed on this PC: the real render was not run (python dse.py presence blender-setup)")

# ---- the catalog and the code
cat = json.loads((Path(__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
t = cat.get("dse.presence_blender_setup")
ok("the setup tool is in the catalog, in the Grow group, and runs 'presence blender-setup' with no fields", t and t["group"] == "Grow" and [a.get("lit") for a in t["args"]] == ["presence", "blender-setup"] and t["fields"] == [] and "download.blender.org" in t["help"])
src = Path(B.__file__).read_text(encoding="utf-8") + Path(M.__file__).read_text(encoding="utf-8")
sc = (Path(B.__file__).parent / "blender_scene.py").read_text(encoding="utf-8")
ok("Blender only ever downloads from download.blender.org and only runs the toolkit's own scene file; the scene file opens only the spec and a font", B.BASE.startswith("https://download.blender.org/") and src.count("requests.get(") == 1 and "eval(" not in sc and "exec(" not in sc and "urllib" not in sc and "socket" not in sc and sc.count("open(") == 1)
ok("no em dash in the new files", chr(0x2014) not in Path(B.__file__).read_text(encoding="utf-8") + sc)
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
