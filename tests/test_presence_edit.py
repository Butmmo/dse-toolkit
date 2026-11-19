"""Tests for the Presence edit render (dse/presence_edit.py): reading an editor project safely, finding the named files, text layers as pictures, and a real render with ffmpeg. Run: python tests/test_presence_edit.py"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from dse import presence_edit as E
from dse import presence_make as PM

fails = 0
def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond: fails += 1

td = Path(tempfile.mkdtemp())
PM.VIDEOS = td / "v"; PM.PICS = td / "p"; PM.AUDIO = td / "a"; PM.GRAPHICS = td / "g"
for d in (PM.VIDEOS, PM.PICS, PM.AUDIO, PM.GRAPHICS): d.mkdir()

# ---- reading a project
def bad(raw):
    try: E.parse_edit(raw); return False
    except ValueError: return True
ok("things that are not editor projects are refused with a plain message", all(bad(x) for x in (None, [], "x", {"v": 2, "clips": []}, {"v": 1}, {"v": 1, "clips": []}, {"v": 1, "clips": ["x", None, {"kind": "weird"}]})))
P = E.parse_edit({"v": 1, "title": "T" * 500, "preset": "hacker", "clips": [{"kind": "color", "out": 500, "color": "red"}] + [{"kind": "color", "out": 30}] * 20,
                  "texts": [{"text": "x" * 900, "start": -5, "end": 1e9, "x": 7, "y": -2, "size": 0, "color": "url(x)", "font": "zz"}] + [{"text": "q", "start": 0, "end": 1}] * 80,
                  "audio": [{"name": "a", "srcSeconds": 5, "volume": 50, "fadeOut": 50, "start": 500, "in": 9, "out": 1}, {"name": "", "srcSeconds": 5}, {"name": "b", "srcSeconds": 0}] + [{"name": f"s{i}", "srcSeconds": 5} for i in range(9)]})
ok("a hostile project is brought inside every limit (90 seconds, 12 clips, 60 texts, 4 sounds, valid colours and fonts)", P["seconds"] <= 90.0001 and len(P["clips"]) <= 12 and len(P["texts"]) <= 60 and len(P["audio"]) <= 4 and P["preset"] == "reels" and len(P["title"]) == 80
   and all(re.match(r"^#[0-9a-f]{6}$", c["color"]) for c in P["clips"]) and all(t["font"] in E.FONTS and 0 <= t["x"] <= 1 and 0 <= t["y"] <= 1 and 0.02 <= t["size"] <= 0.12 and len(t["text"]) <= 120 and t["end"] > t["start"] for t in P["texts"]))
pics = lambda n, sec: [{"kind": "picture", "name": f"p{i}.png", "out": sec} for i in range(n)]
L1 = E.parse_edit({"v": 1, "clips": pics(5, 30)})
L2 = E.parse_edit({"v": 1, "clips": pics(2, 30) + [{"kind": "video", "name": "v.mp4", "srcSeconds": 100, "out": 100}]})
ok("the video is never longer than 90 seconds: five 30 second pictures give three clips", L1["seconds"] == 90 and len(L1["clips"]) == 3)
ok("a last clip that would run over is shortened, not dropped", L2["seconds"] == 90 and len(L2["clips"]) == 3 and L2["clips"][2]["out"] - L2["clips"][2]["in"] == 30)
MV = E.parse_edit({"v": 1, "clips": [{"kind": "color", "out": 3}], "texts": [{"text": "a", "motion": "rise"}, {"text": "b", "motion": "spin"}, {"text": "c"}, {"text": "d", "motion": "slide"}]})
ok("a text's move is read (rise, drop, slide); anything else, or none given, stays still", [t["motion"] for t in MV["texts"]] == ["rise", "none", "none", "slide"])
ok("at most 12 clips and 60 texts and 4 sounds are read, however many there are", len(E.parse_edit({"v": 1, "clips": pics(20, 1)})["clips"]) == 12
   and len(E.parse_edit({"v": 1, "clips": pics(1, 5), "texts": [{"text": "q", "start": 0, "end": 1}] * 80})["texts"]) == 60
   and len(E.parse_edit({"v": 1, "clips": pics(1, 5), "audio": [{"name": f"s{i}", "srcSeconds": 5} for i in range(9)]})["audio"]) == 4)
ok("a project of another version is refused even when it looks fine", bad({"v": 2, "clips": [{"kind": "color", "out": 3}]}) and bad({"clips": [{"kind": "color", "out": 3}]}))
ok("a sound is clamped: volume 0 to 1, in before out, fade at most 5 s", all(0 <= a["volume"] <= 1 and a["out"] > a["in"] and a["fadeOut"] <= 5 and 0 <= a["start"] <= 90 for a in P["audio"]))
Q = E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "a.mp4", "srcSeconds": 10, "in": 2, "out": 6}, {"kind": "picture", "name": "b.png", "out": 3}, {"kind": "color", "out": 2}]})
ok("clip times and the total come out exactly: 4 + 3 + 2 = 9 seconds", Q["seconds"] == 9.0 and Q["clips"][0]["in"] == 2 and Q["clips"][0]["out"] == 6)
ok("a video cannot run past its own file", E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "a", "srcSeconds": 5, "out": 99}]})["clips"][0]["out"] == 5)
ok("only the files that are really used are needed, each once (colours need none)", E.needed_files(E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "a.mp4", "srcSeconds": 5, "out": 3}, {"kind": "video", "name": "a.mp4", "srcSeconds": 5, "out": 3}, {"kind": "color", "out": 1}],
        "audio": [{"name": "m.mp3", "srcSeconds": 20}]})) == ["a.mp4", "m.mp3"])

# ---- finding the named files
(PM.VIDEOS / "clip.mp4").write_bytes(b"x"); (PM.PICS / "pic.png").write_bytes(b"x"); (PM.AUDIO / "song.wav").write_bytes(b"x")
ok("files are found by name in my-video, my-pictures and my-audio", E.find_file("clip.mp4").parent == PM.VIDEOS and E.find_file("pic.png").parent == PM.PICS and E.find_file("song.wav").parent == PM.AUDIO and E.find_file("nope.mp4") is None)
(td / "secret.txt").write_text("s")
ok("a path in a name cannot reach another folder: only the file name counts", E.find_file("../secret.txt") is None and E.find_file("..\\..\\secret.txt") is None and E.find_file(str(td / "secret.txt")) is None and E.find_file("") is None)
ok("missing files are listed by name", E.missing_files(E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "clip.mp4", "srcSeconds": 5, "out": 3}, {"kind": "video", "name": "gone.mp4", "srcSeconds": 5, "out": 3}], "audio": [{"name": "lost.mp3", "srcSeconds": 5}]})) == ["gone.mp4", "lost.mp3"])

# ---- captions file
S = E.parse_edit({"v": 1, "clips": [{"kind": "color", "out": 10}], "texts": [{"role": "caption", "text": "second", "start": 4, "end": 6}, {"role": "text", "text": "title", "start": 0, "end": 3}, {"role": "caption", "text": "first", "start": 1.5, "end": 3.25}]})
srt = E.make_srt(S)
ok("the captions file lists only captions, in time order, numbered, with times in the .srt form", srt.startswith("1\n00:00:01,500 --> 00:00:03,250\nfirst\n\n2\n00:00:04,000 --> 00:00:06,000\nsecond") and "title" not in srt)

# ---- a text layer as a picture
png = E.text_layer_png({"text": "Hello there", "x": 0.5, "y": 0.5, "size": 0.07, "color": "#ffffff", "bold": True, "font": "sans", "fade": False, "role": "text", "start": 0, "end": 1}, 540, 960, td / "t.png")
im = Image.open(png)
a = im.getchannel("A")
ok("a text layer is a transparent picture of the video's size with words in the middle and nothing at the top", im.size == (540, 960) and im.mode == "RGBA" and a.crop((0, 0, 540, 200)).getextrema()[1] == 0 and a.crop((0, 400, 540, 560)).getextrema()[1] > 0)
long_ = E.text_layer_png({"text": "word " * 120, "x": 0.5, "y": 0.5, "size": 0.07, "color": "#ffffff", "bold": True, "font": "serif", "fade": False, "role": "text", "start": 0, "end": 1}, 540, 960, td / "l.png")
ok("a very long text still makes a picture of the right size (no crash)", Image.open(long_).size == (540, 960))
bb = Image.open(long_).getchannel("A").getbbox()
ok("long text is wrapped inside the frame: ink stays at least 5 percent in from each side", bb is not None and bb[0] >= 0.05 * 540 and bb[2] <= 0.95 * 540)

# ---- speed and fades (slice 3): reading
Z = E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "a", "srcSeconds": 10, "out": 10, "speed": 2, "fadeIn": 0.5, "fadeOut": 9},
                                   {"kind": "video", "name": "b", "srcSeconds": 10, "out": 10, "speed": 7, "fadeIn": -3},
                                   {"kind": "picture", "name": "c", "out": 3, "speed": 2}]})
ok("speed is one of the listed values for a video (an unknown one or a picture's is normal)", [c["speed"] for c in Z["clips"]] == [2, 1, 1] and E.SPEEDS == (0.5, 0.75, 1, 1.25, 1.5, 2))
ok("a clip's time on the timeline is its stretch of the file divided by its speed, and the total adds them up (5 + 10 + 3)", [c["seconds"] for c in Z["clips"]] == [5.0, 10.0, 3.0] and Z["seconds"] == 18.0)
ok("fades are 0 to 1 second and never pass the clip's length together (the fade in first)", Z["clips"][0]["fadeIn"] == 0.5 and Z["clips"][0]["fadeOut"] == 1.0 and Z["clips"][1]["fadeIn"] == 0)
F = E.parse_edit({"v": 1, "clips": [{"kind": "color", "out": 1.5, "fadeIn": 1, "fadeOut": 1}]})
ok("two fades that would pass the clip are cut: the fade in keeps 1 s, the fade out gets what is left", F["clips"][0]["fadeIn"] == 1.0 and F["clips"][0]["fadeOut"] == 0.5)
W = E.parse_edit({"v": 1, "clips": [{"kind": "video", "name": "c", "srcSeconds": 100, "out": 100, "speed": 0.5}]})
ok("a slowed clip that would run past 90 seconds is cut to fit (45 s of the file at half speed)", W["seconds"] == 90.0 and W["clips"][0]["out"] == 45.0)

# ---- crossfade (slice 4): reading
def pic(name, out, **kw):
    d = {"kind": "picture", "name": name, "out": out}; d.update(kw); return d
X1 = E.parse_edit({"v": 1, "clips": [pic("a", 3, mix=1), pic("b", 3, mix=1), pic("c", 0.4, mix=1)]})
ok("the first clip has no blend; a blend is at most 1 s and half of either clip (0.4 s clip: 0.2 s)", [c["mix"] for c in X1["clips"]] == [0.0, 1.0, 0.2])
ok("a blend overlaps the two clips: each starts where the one before ends minus the blend, and the video is shorter by the blends (3 + 3 + 0.4 - 1 - 0.2 = 5.2)", [c["start"] for c in X1["clips"]] == [0.0, 2.0, 4.8] and X1["seconds"] == 5.2)
X4 = E.parse_edit({"v": 1, "clips": [pic("a", 10), pic("b", 10, mix=5), pic("c", 0.4), pic("d", 3, mix=1)]})
ok("a blend asked for at 5 seconds is cut to 1 second; a blend is at most half of the clip before it (0.4 s before: 0.2 s)", X4["clips"][1]["mix"] == 1.0 and X4["clips"][3]["mix"] == 0.2)
X2 = E.parse_edit({"v": 1, "clips": [pic("a", 30), pic("b", 30, mix=1), pic("c", 30, mix=1), pic("d", 30, mix=1)]})
ok("blends are counted against the 90 second limit: the last clip is shortened to what is left (30 + 29 + 29 + 3 = 90)", len(X2["clips"]) == 4 and X2["seconds"] == 90.0 and X2["clips"][3]["seconds"] == 3.0 and X2["clips"][3]["start"] == 87.0)
X3 = E.parse_edit({"v": 1, "clips": [pic("a", 29), pic("b", 29), pic("c", 29), pic("d", 30, mix=1)]})
ok("a clip that blends in when the video is nearly full is shortened to fit, not dropped (3 s room, 1 s blend: 4 s long)", len(X3["clips"]) == 4 and X3["seconds"] == 90.0 and X3["clips"][3]["seconds"] == 4.0 and X3["clips"][3]["mix"] == 1.0)

# ---- a real render
ff = PM.find_ffmpeg()
if not ff:
    print("SKIP  ffmpeg is not installed: the real render was not run")
else:
    def run(*a): subprocess.run([ff, "-y", "-loglevel", "error", *a], check=True)
    def probe(path): return subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    run("-f", "lavfi", "-i", "color=c=0x101030:s=320x180:r=30:d=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4:sample_rate=44100", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(PM.VIDEOS / "clip.mp4"))
    run("-f", "lavfi", "-i", "color=c=0x301010:s=200x300", "-frames:v", "1", str(PM.PICS / "pic.png"))
    run("-f", "lavfi", "-i", "sine=frequency=880:duration=6:sample_rate=44100", str(PM.AUDIO / "song.wav"))
    proj = {"v": 1, "title": "Render test", "preset": "reels", "clips": [
        {"kind": "video", "name": "clip.mp4", "srcSeconds": 4, "in": 0.5, "out": 2.5, "muted": False}, {"kind": "picture", "name": "pic.png", "out": 2}, {"kind": "color", "out": 2, "color": "#102010"}],
        "texts": [{"role": "text", "text": "HELLO", "start": 0.5, "end": 1.5, "y": 0.5, "size": 0.09, "fade": False}, {"role": "caption", "text": "a caption", "start": 3, "end": 5, "fade": False}],
        "audio": [{"name": "song.wav", "srcSeconds": 6, "start": 3, "in": 0, "out": 6, "volume": 0.5, "fadeOut": 1}]}
    out = E.render_edit(proj, draft=True, say=lambda *_: None)
    info = probe(out)
    ok("the render saves an MP4 in my-video and a captions file next to it", out.parent == PM.VIDEOS and out.suffix == ".mp4" and out.name == "render-test-draft.mp4" and out.with_suffix(".srt").exists())
    ok("a quick draft is half size: 540 x 960, H.264 and AAC, 30 fps", bool(re.search(r"Video: h264.*540x960.*30 fps", info)) and bool(re.search(r"Audio: aac.*48000 Hz, stereo", info)))
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info); secs = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    ok("the video is as long as the clips added up (2 + 2 + 2 = 6 seconds)", abs(secs - 6.0) < 0.15)
    r = subprocess.run([ff, "-v", "error", "-i", str(out), "-f", "null", "-"], capture_output=True, text=True)
    ok("ffmpeg decodes the whole file with no error", r.returncode == 0 and r.stderr.strip() == "")
    def bright(t, band=(0.3, 0.7)):
        f = td / f"f{t}.png"
        run("-ss", str(t), "-i", str(out), "-frames:v", "1", str(f))
        im = Image.open(f).convert("L"); w, h = im.size
        crop = im.crop((0, int(h * band[0]), w, int(h * band[1])))
        return sum(1 for p in crop.getdata() if p > 200)
    inside, before, after, cap_in, cap_out = bright(1.0), bright(0.2), bright(1.9), bright(3.5, (0.6, 0.85)), bright(5.5, (0.6, 0.85))
    ok("text shows only while it is on: words at 1.0 s, none at 0.2 s or 1.9 s", inside > 300 and before == 0 and after == 0)
    ok("a caption shows lower down in its own time (3.5 s) and not after it ends", cap_in > 100 and cap_out == 0)
    def level(a, b):
        r = subprocess.run([ff, "-hide_banner", "-ss", str(a), "-t", str(b), "-i", str(out), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r)
        return -200.0 if not m or m.group(1) == "-inf" else float(m.group(1))
    ok("the video clip's own sound is heard at the start (0 to 1.5 s)", level(0.1, 1.4) > -40)
    ok("the added sound starts where it was put (silent gap 2.5 to 3 s, music after 3 s)", level(2.6, 0.3) < -60 and level(3.2, 1.5) > -40)
    ok("the added sound fades out over its last second (5 to 6 s is much quieter than 3.2 to 4.2 s)", level(5.5, 0.4) < level(3.2, 1.0) - 6)
    fadeproj = {"v": 1, "title": "fade", "preset": "reels", "clips": [{"kind": "color", "out": 2, "color": "#101030"}], "texts": [{"role": "text", "text": "FADE", "start": 0.5, "end": 1.5, "y": 0.5, "size": 0.09, "fade": True}]}
    fout = E.render_edit(fadeproj, draft=True, say=lambda *_: None)
    out_keep, out = out, fout
    early, mid = bright(0.55), bright(1.0)
    ok("a fading text is faint at the start of its time and full in the middle", mid > 300 and early < mid * 0.6)
    out = out_keep
    def ink_box(path, t):
        f = td / f"m{path.stem}{t}.png"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", str(f)], check=True)
        g = Image.open(f).convert("L").point(lambda v: 255 if v > 200 else 0)
        return g.getbbox()
    def moving(motion):
        pr = {"v": 1, "title": "move-" + motion, "preset": "reels", "clips": [{"kind": "color", "out": 3, "color": "#101030"}], "texts": [{"role": "text", "text": "MOVE", "start": 0.5, "end": 2.5, "y": 0.5, "size": 0.09, "fade": False, "motion": motion}]}
        return E.render_edit(pr, draft=True, say=lambda *_: None)
    rise, drop, slide, still = moving("rise"), moving("drop"), moving("slide"), moving("none")
    r0, r1 = ink_box(rise, 0.55), ink_box(rise, 1.6)
    d0, d1 = ink_box(drop, 0.55), ink_box(drop, 1.6)
    s0, s1 = ink_box(slide, 0.55), ink_box(slide, 1.6)
    n0, n1 = ink_box(still, 0.55), ink_box(still, 1.6)
    ok("a rising text starts lower and ends in place (0.06 of the height is 58 px of 960; 0.15 s in, the ink is about 39 px lower than at rest)", r0 and r1 and 33 < r0[1] - r1[1] < 45 and abs(r0[0] - r1[0]) < 3)
    rm = ink_box(rise, 0.7)
    ok("the move eases out: half way through its 0.4 s it has covered most of the way (about 7 px left, a straight line would leave 29)", rm and r1 and 2 <= rm[1] - r1[1] <= 14)
    ok("a dropping text starts higher and ends in place", d0 and d1 and 33 < d1[1] - d0[1] < 45)
    ok("a sliding text starts to the left of where it ends and stays on the same line (0.3 of the width is 162 px of 540; 0.15 s in, about 108 px to the left)", s0 and s1 and 95 < s1[0] - s0[0] < 122 and abs(s0[1] - s1[1]) < 3)
    ok("a still text does not move at all", n0 and n1 and n0 == n1)
    def project_with_volume(v): return {"v": 1, "title": f"vol{int(v * 100)}", "preset": "square", "clips": [{"kind": "color", "out": 2}], "audio": [{"name": "song.wav", "srcSeconds": 6, "start": 0, "volume": v}]}
    loud = E.render_edit(project_with_volume(1.0), draft=True, say=lambda *_: None); quiet = E.render_edit(project_with_volume(0.25), draft=True, say=lambda *_: None)
    out_keep, out = out, loud; lv_loud = level(0.2, 1.5); out = quiet; lv_quiet = level(0.2, 1.5); out = out_keep
    ok("a sound's volume changes how loud it is (a quarter volume is about 12 dB quieter)", 9 < lv_loud - lv_quiet < 15)
    run("-f", "lavfi", "-i", "color=c=0xe0e0e0:s=320x180:r=30:d=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4:sample_rate=44100", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(PM.VIDEOS / "bright.mp4"))
    def length_of(path):
        d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe(path)); return int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    def luma(path, t):
        f = td / f"l{abs(hash((str(path), t)))}.png"
        run("-ss", str(t), "-i", str(path), "-frames:v", "1", str(f))
        im = Image.open(f).convert("L"); return sum(im.getdata()) / (im.size[0] * im.size[1])
    def level_of(path, a, b):
        r = subprocess.run([ff, "-hide_banner", "-ss", str(a), "-t", str(b), "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r); return -200.0 if not m or m.group(1) == "-inf" else float(m.group(1))
    def one(**kw):
        c = {"kind": "video", "name": "bright.mp4", "srcSeconds": 4, "in": 0, "out": 4}; c.update(kw)
        return E.render_edit({"v": 1, "title": f"sp{abs(hash(str(kw)))}", "preset": "square", "clips": [c]}, draft=True, say=lambda *_: None)
    run("-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=2", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=30:d=2", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=44100",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a]atrim=0:2[s];[s][3:a]concat=n=2:v=0:a=1[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(PM.VIDEOS / "half.mp4"))
    def half(**kw):
        c = {"kind": "video", "name": "half.mp4", "srcSeconds": 4, "in": 0, "out": 4}; c.update(kw)
        return E.render_edit({"v": 1, "title": f"half{abs(hash(str(kw)))}", "preset": "square", "clips": [c]}, draft=True, say=lambda *_: None)
    hf = half(speed=2)
    ok("at double speed the dark first half of the file is shown in the first second and the bright second half in the next (the speed changes WHAT is shown, not just how long)", luma(hf, 0.5) < 40 and luma(hf, 1.5) > 150)
    hn = half()
    ok("at normal speed the same file is dark for 2 seconds then bright", luma(hn, 1.5) < 40 and luma(hn, 2.5) > 150)
    ok("at double speed the sound is sped up too: silence for the first second, the tone from 1 s to 2 s (pitch stays the same)", level_of(hf, 0.1, 0.6) < -60 and level_of(hf, 1.2, 0.6) > -40)
    fast = one(speed=2); slow = one(speed=0.5)
    ok("a clip at double speed makes a video half as long (4 s of the file in 2 s)", abs(length_of(fast) - 2.0) < 0.2)
    ok("a clip at half speed makes a video twice as long (4 s of the file in 8 s)", abs(length_of(slow) - 8.0) < 0.2)
    ok("a sped-up clip still has its sound, the same length as the picture", "Audio: aac" in probe(fast))
    plain = one()
    faded = one(fadeIn=1, fadeOut=1)
    ok("a clip with no fades is bright from its very first frame", luma(plain, 0.0) > 150)
    ok("a fade in starts black and is clear a moment after it ends", luma(faded, 0.0) < 40 and luma(faded, 1.6) > 150)
    ok("a fade out ends black and the clip is clear before it starts", luma(faded, 3.95) < 60 and luma(faded, 2.0) > 150)
    def level_of(path, a, b):
        r = subprocess.run([ff, "-hide_banner", "-ss", str(a), "-t", str(b), "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r); return -200.0 if not m or m.group(1) == "-inf" else float(m.group(1))
    ok("the sound fades with the picture: much quieter in the first and last half second than in the middle", level_of(faded, 0.0, 0.3) < level_of(faded, 1.5, 1.0) - 6 and level_of(faded, 3.7, 0.3) < level_of(faded, 1.5, 1.0) - 6)
    mixed = E.render_edit({"v": 1, "title": "speedmix", "preset": "square", "clips": [{"kind": "video", "name": "bright.mp4", "srcSeconds": 4, "in": 1, "out": 3, "speed": 2}, {"kind": "color", "out": 1}]}, draft=True, say=lambda *_: None)
    ok("speed works together with a trimmed clip and the next clip (2 s of file at double speed is 1 s, then 1 s more)", abs(length_of(mixed) - 2.0) < 0.2)
    def solid(name, out, color):
        return {"kind": "color", "name": name, "out": out, "color": color}
    def blend(clips, title):
        return E.render_edit({"v": 1, "title": title, "preset": "square", "clips": clips}, draft=True, say=lambda *_: None)
    bl = blend([solid("w", 2, "#ffffff"), dict(solid("k", 2, "#000000"), mix=1)], "xfade1")
    ok("two clips blended by 1 second make a video 3 seconds long (2 + 2 - 1)", abs(length_of(bl) - 3.0) < 0.2)
    ok("before the blend the first clip is pure white, in the middle of it the picture is about half way, after it pure black", luma(bl, 0.5) > 240 and 90 < luma(bl, 1.5) < 170 and luma(bl, 2.6) < 15)
    ok("a blended video decodes with no error and has sound (silence under colours)", subprocess.run([ff, "-v", "error", "-i", str(bl), "-f", "null", "-"], capture_output=True, text=True).stderr.strip() == "" and "Audio: aac" in probe(bl))
    mixed3 = blend([solid("w", 2, "#ffffff"), dict(solid("k", 2, "#000000"), mix=1), solid("w2", 2, "#ffffff")], "xfade3")
    ok("a blend and a plain junction in one video: white, blended to black, then straight to white (2 + 2 - 1 + 2 = 5 seconds)", abs(length_of(mixed3) - 5.0) < 0.2 and luma(mixed3, 0.4) > 240 and 90 < luma(mixed3, 1.5) < 170 and luma(mixed3, 2.5) < 15 and luma(mixed3, 3.5) > 240)
    chain = blend([solid("w", 2, "#ffffff"), dict(solid("k", 2, "#000000"), mix=1), dict(solid("w2", 2, "#ffffff"), mix=1)], "xfade-chain")
    ok("two blends in a row: white into black into white (2 + 2 - 1 + 2 - 1 = 4 seconds), the second blend starting where the first ends", abs(length_of(chain) - 4.0) < 0.2 and luma(chain, 0.4) > 240 and 90 < luma(chain, 1.5) < 170 and luma(chain, 2.0) < 40 and 90 < luma(chain, 2.5) < 170 and luma(chain, 3.6) > 240)
    vv = blend([{"kind": "video", "name": "bright.mp4", "srcSeconds": 4, "in": 0, "out": 3}, {"kind": "video", "name": "clip.mp4", "srcSeconds": 4, "in": 0, "out": 3, "mix": 1}], "xfade-video")
    ok("two real video clips blended: 3 + 3 - 1 = 5 seconds with sound all the way through", abs(length_of(vv) - 5.0) < 0.2 and level_of(vv, 0.2, 0.6) > -40 and level_of(vv, 4.2, 0.6) > -40)
    ok("the sound crosses over in the blend: it never drops out in the middle of it", level_of(vv, 1.8, 0.4) > -45)
    muted = dict(proj, clips=[dict(proj["clips"][0], muted=True)] + proj["clips"][1:])
    out2 = E.render_edit(muted, draft=True, out_path=td / "muted.mp4", say=lambda *_: None)
    out_keep, out = out, out2
    ok("a muted clip is silent", level(0.1, 1.4) < -60)
    out = out_keep
    nofx = E.render_edit({"v": 1, "title": "plain", "preset": "square", "clips": [{"kind": "color", "out": 1}]}, draft=True, say=lambda *_: None)
    ok("a project with no text and no sound still renders (square, half size 540 x 540)", bool(re.search(r"540x540", probe(nofx))) and not nofx.with_suffix(".srt").exists())
    full = E.render_edit({"v": 1, "title": "full", "preset": "landscape", "clips": [{"kind": "picture", "name": "pic.png", "out": 1}]}, say=lambda *_: None)
    ok("full size is the preset's size (1920 x 1080)", bool(re.search(r"1920x1080", probe(full))))
    try:
        E.render_edit({"v": 1, "clips": [{"kind": "video", "name": "gone.mp4", "srcSeconds": 5, "out": 3}], "audio": [{"name": "lost.mp3", "srcSeconds": 5}]}, say=lambda *_: None); named = False
    except FileNotFoundError as e:
        named = "gone.mp4" in str(e) and "lost.mp3" in str(e)
    ok("a missing file stops the render before anything is made and names the files", named)
    pf = td / "p.edit.json"; pf.write_text(json.dumps(proj), encoding="utf-8")
    ok("the command works from a project file and reports what it saved", E.cli([str(pf), "--draft"]) == 0)
    ok("the command refuses junk with a message, not a crash", E.cli([]) == 2 and E.cli([str(td / "nope.json")]) == 1)

# ---- the HQ tool entry
cat = json.loads((Path(E.__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
t = cat["dse.presence_edit_render"]; names = {f["name"] for f in t["fields"]}
ok("the HQ tool is in the catalog, in the Grow group, and every argument points at a real field", t["group"] == "Grow" and all(a["field"] in names for a in t["args"] if "field" in a) and t["script"] == "dse.py")
ok("the tool asks for the edit file from my-video and offers a quick draft", any(f["name"] == "project" and f["glob"] == "my-video/*.edit.json" and f["required"] for f in t["fields"]) and any(f["name"] == "draft" and f["type"] == "bool" for f in t["fields"]) and {"flag": "--draft", "field": "draft"} in t["args"])

src = (Path(__file__).resolve().parents[1] / "dse" / "presence_edit.py").read_text(encoding="utf-8")
ok("no em dash in the module", chr(0x2014) not in src)
sys.exit(1 if fails else 0)
