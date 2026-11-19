"""Tests for Presence captions (dse/presence_captions.py): grouping timed words into captions, the captions file, finding the voiceover safely, the speech step (with a stand-in, and for real when DSE_TEST_REAL_SPEECH=1)."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import presence_captions as C
from dse import presence_make as PM

fails = 0
def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond: fails += 1

td = Path(tempfile.mkdtemp())
PM.VIDEOS = td / "v"; PM.PICS = td / "p"; PM.AUDIO = td / "a"; PM.GRAPHICS = td / "g"
for d in (PM.VIDEOS, PM.PICS, PM.AUDIO, PM.GRAPHICS): d.mkdir()

def words(text, start=0.0, per=0.3, gap=0.0):
    out, t = [], start
    for w in text.split():
        out.append({"w": w, "start": round(t, 3), "end": round(t + per, 3)}); t += per + gap
    return out

# ---- grouping
g = C.group_words(words("Hello there my friend."))
ok("a short sentence is one caption, from its first word to its last", len(g) == 1 and g[0]["text"] == "Hello there my friend." and g[0]["start"] == 0 and abs(g[0]["end"] - 1.2) < 1e-6)
g = C.group_words(words("one two three four five six seven eight nine ten"))
ok("ten words in one sentence become two captions of five (shared evenly, not six and four)", [c["text"].count(" ") + 1 for c in g] == [5, 5])
g = C.group_words(words("a b c d e f g h i j k l m"))
ok("thirteen words become three captions of 5, 4 and 4, never one stray word", [c["text"].count(" ") + 1 for c in g] == [5, 4, 4])
g = C.group_words(words("seven words in a row here ok"))
ok("seven words are split 4 and 3, not 6 and 1", [c["text"].count(" ") + 1 for c in g] == [4, 3])
g = C.group_words(words("First one. Second one! Third one? Fourth"))
ok("a full stop, an exclamation or a question mark ends a caption", [c["text"] for c in g] == ["First one.", "Second one!", "Third one?", "Fourth"])
g = C.group_words(words("go now", 0) + words("and then", 2.0))
ok("a pause of more than 0.6 s ends a caption even without a full stop", [c["text"] for c in g] == ["go now", "and then"])
g = C.group_words(words("go now", 0) + words("and then", 1.1))
ok("a pause of 0.6 s or less does not (the words still fit in one caption)", len(g) == 1 and g[0]["text"] == "go now and then")
g = C.group_words(words("slow words that take forever", per=1.5))
ok("a caption is at most 2.8 seconds: slow speech is split even when the words are few", len(g) >= 3 and all(c["end"] - c["start"] <= 3.0 for c in g))
g = C.group_words([{"w": "Ooooh.", "start": 0.0, "end": 8.0}, {"w": "yes", "start": 9.0, "end": 9.5}])
ok("one very long word (a held note) is one caption, not split into empty ones, and nothing crashes", [c["text"] for c in g] == ["Ooooh.", "yes"])
long_words = [{"w": "w" * 30, "start": i * 0.2, "end": i * 0.2 + 0.15} for i in range(6)]
g = C.group_words(long_words)
ok("a caption is at most 120 characters: very long words are split", len(g) >= 2 and all(len(c["text"]) <= 120 for c in g))
g = C.group_words(list(reversed(words("one two three. four five six."))))
ok("words given out of order are put in time order", [c["text"] for c in g] == ["one two three.", "four five six."])
g = C.group_words(words("One. Two. Three.", per=0.1, gap=0.0))
ok("a caption is held at least 0.3 s, but never into the next one", all(c["end"] - c["start"] >= 0.1 for c in g) and all(g[i]["end"] <= g[i + 1]["start"] + 1e-9 for i in range(len(g) - 1)) and g[0]["end"] - g[0]["start"] >= 0.1)
g = C.group_words([{"w": "Hi.", "start": 1.0, "end": 1.05}])
ok("a very quick last word is held for 0.3 s so it can be read", len(g) == 1 and abs((g[0]["end"] - g[0]["start"]) - 0.3) < 1e-6)
ok("no captions without words, and bad entries (no time, backwards time, empty or missing words, wrong types) are skipped without a crash",
   C.group_words([]) == [] and C.group_words(None) == [] and C.group_words([{"w": "", "start": 0, "end": 1}, {"w": "x"}, {"w": "y", "start": 2, "end": 1}, {"w": "z", "start": -1, "end": 1}, "junk", None, {"w": "ok", "start": "0", "end": "1"}])[0]["text"] == "ok")
many = C.group_words(words(" ".join(f"w{i}." for i in range(300))))
ok("a long recording gives one caption per sentence in order, with no overlap", len(many) == 300 and all(many[i]["end"] <= many[i + 1]["start"] + 1e-9 for i in range(299)))

g = C.group_words(words("one two three four five six seven eight nine ten"))
ok("every caption carries the real time of each of its words, in order, matching its text", all(" ".join(w["w"] for w in c["words"]) == c["text"] and c["words"][0]["start"] == c["start"] for c in g) and sum(len(c["words"]) for c in g) == 10 and all(c["words"][i]["start"] <= c["words"][i + 1]["start"] for c in g for i in range(len(c["words"]) - 1)))

# ---- the captions file
srt = C.to_srt([{"start": 0.0, "end": 1.5, "text": "Hello."}, {"start": 3725.25, "end": 3726.0, "text": "Late."}])
ok("the captions file numbers each caption and writes times as hours:minutes:seconds,milliseconds", srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHello.\n") and "2\n01:02:05,250 --> 01:02:06,000\nLate.\n" in srt)

# ---- finding the voiceover
(PM.AUDIO / "voice.mp3").write_bytes(b"x"); (PM.VIDEOS / "clip.mp4").write_bytes(b"x"); (PM.VIDEOS / "voice.mp3").write_bytes(b"y")
ok("the voiceover is found by its name, my-audio first, then my-video", C.find_media("voice.mp3") == PM.AUDIO / "voice.mp3" and C.find_media("clip.mp4") == PM.VIDEOS / "clip.mp4")
ok("only the file name is used: a path pointing elsewhere (..\\, folders, a full path) cannot reach any other file", C.find_media("../../etc/passwd") is None and C.find_media("C:\\Windows\\win.ini") is None and C.find_media("..\\voice.mp3") == PM.AUDIO / "voice.mp3" and C.find_media("") is None and C.find_media(None) is None)
ok("a file that is not there gives nothing", C.find_media("nope.mp3") is None)

# ---- the speech tool's place
keep = os.environ.pop("DSE_WHISPER_PYTHON", None)
fake_py = td / "py.exe"; fake_py.write_bytes(b"x")
os.environ["DSE_WHISPER_PYTHON"] = str(fake_py)
ok("DSE_WHISPER_PYTHON points at the speech Python when the file exists", C.find_python() == fake_py)
os.environ["DSE_WHISPER_PYTHON"] = str(td / "missing.exe")
ok("a DSE_WHISPER_PYTHON that does not exist is ignored", C.find_python() != td / "missing.exe")
os.environ.pop("DSE_WHISPER_PYTHON")
real_roots = C.ROOT
C.ROOT = td / "nowhere" / "toolkit"
ok("with no speech environment anywhere, nothing is found", C.find_python() is None)
C.ROOT = real_roots

# ---- the whole run with a stand-in for the speech step
ff = PM.find_ffmpeg()
if not ff:
    print("SKIP  ffmpeg is not on this machine: the runs that read sound were not done")
else:
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(PM.AUDIO / "tone.wav")], check=True)
    stand = td / "worker.py"
    stand.write_text("import json, sys\nwav, model, out = sys.argv[1:4]\nopen(out, 'w').write(json.dumps({'words': [{'w': 'Hello', 'start': 0.1, 'end': 0.4}, {'w': 'world.', 'start': 0.45, 'end': 0.9}], 'model': model}))\n", encoding="utf-8")
    os.environ["DSE_WHISPER_PYTHON"] = sys.executable
    C.WORKER = stand
    msgs = []
    out = C.make_captions("tone.wav", say=msgs.append)
    ok("a run saves the captions next to the voiceover and says what to do next", out == PM.AUDIO / "tone.srt" and "Hello world." in out.read_text(encoding="utf-8") and any("Captions file" in m and ".captions.json" in m for m in msgs))
    js = json.loads((PM.AUDIO / "tone.captions.json").read_text(encoding="utf-8"))
    ok("a run also saves <name>.captions.json: the same captions with the real start and end of every word", js["v"] == 1 and len(js["cues"]) == 1 and js["cues"][0]["text"] == "Hello world." and [w["w"] for w in js["cues"][0]["words"]] == ["Hello", "world."] and js["cues"][0]["words"][1]["start"] == 0.45 and js["cues"][0]["start"] == 0.1)
    out2 = C.make_captions("tone.wav", say=lambda *_: None)
    ok("a captions file that is already there is never overwritten (a new one is saved beside it), and the word times go with the new one", out2.name == "tone-captions.srt" and out.exists() and (PM.AUDIO / "tone-captions.captions.json").exists() and (PM.AUDIO / "tone.captions.json").exists())
    try: C.make_captions("tone.wav", model="huge"); wrong = False
    except RuntimeError as e: wrong = "huge" in str(e)
    ok("a model that is not offered is refused with a message", wrong)
    try: C.make_captions("ghost.wav"); wrong = False
    except RuntimeError as e: wrong = "ghost.wav" in str(e) and "my-audio" in str(e)
    ok("a missing file is refused with a message that names it", wrong)
    stand.write_text("import json, sys\nopen(sys.argv[3], 'w').write(json.dumps({'words': []}))\n", encoding="utf-8")
    try: C.make_captions("tone.wav", say=lambda *_: None); wrong = False
    except RuntimeError as e: wrong = "No speech" in str(e)
    ok("a recording with no speech is reported, and no empty file is saved", wrong and not (PM.AUDIO / "tone-captions-captions.srt").exists())
    stand.write_text("import sys\nsys.stderr.write('boom')\nsys.exit(3)\n", encoding="utf-8")
    try: C.make_captions("tone.wav", say=lambda *_: None); wrong = False
    except RuntimeError as e: wrong = "boom" in str(e)
    ok("when the speech tool fails its last message is shown", wrong)
    (PM.AUDIO / "bad.wav").write_bytes(b"not audio")
    try: C.make_captions("bad.wav", say=lambda *_: None); wrong = False
    except RuntimeError as e: wrong = "ffmpeg could not read" in str(e)
    ok("a file ffmpeg cannot read is reported", wrong)
    C.ROOT = td / "nowhere" / "toolkit"; os.environ.pop("DSE_WHISPER_PYTHON")
    try: C.make_captions("tone.wav", say=lambda *_: None); wrong = False
    except RuntimeError as e: wrong = "not set up" in str(e) and "faster-whisper" in str(e)
    ok("without the speech tool the message says how to set it up", wrong)
    C.ROOT = real_roots

# ---- the command
import io, contextlib
def cli(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = C.cli(list(a))
    return rc, buf.getvalue()
rc, o = cli("--setup"); ok("--setup prints the three steps", rc == 0 and "winget install" in o and "faster-whisper" in o)
rc, o = cli("--model", "base.en"); ok("asking with no file says what to give", rc == 1 and "voiceover" in o)
rc, o = cli("ghost.wav"); ok("a missing file gives a message and a failing exit, not a crash", rc == 1 and "ghost.wav" in o)
rc, o = cli(); ok("no arguments shows the help", rc == 0 and "presence captions" in o)

# ---- the HQ tool
cat = json.loads((Path(__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]
t = cat["dse.presence_captions"]; names = {f["name"] for f in t["fields"]}
ok("the HQ tool is in the catalog, in the Grow group, and every argument points at a real field", t["group"] == "Grow" and all(a.get("field") in names for a in t["args"] if "field" in a) and {"media", "model"} <= names)
ok("the tool offers three accuracy levels, the balanced one as the default", [c["value"] for c in t["fields"][1]["choices"]] == list(C.MODELS) and t["fields"][1]["default"] == "base.en")
ok("the tool picks the voiceover from my-audio and hands back the captions file and the word times", t["fields"][0]["glob"] == "my-audio/*" and [o["glob"] for o in t["outputs"]] == ["my-audio/*.srt", "my-audio/*.captions.json"])
src = (Path(__file__).resolve().parents[1] / "dse" / "presence_captions.py").read_text(encoding="utf-8") + (Path(__file__).resolve().parents[1] / "dse" / "whisper_worker.py").read_text(encoding="utf-8")
ok("no em dash in the module", "\u2014" not in src)
ok("the speech worker imports nothing from the toolkit (it runs in the separate environment)", not re.search(r"^\s*(from|import)\s+(dse|\.)", (Path(__file__).resolve().parents[1] / "dse" / "whisper_worker.py").read_text(encoding="utf-8"), re.M))

# ---- the real thing (only when asked: it needs the speech tool and its model on this PC)
if os.environ.get("DSE_TEST_REAL_SPEECH") == "1":
    if keep: os.environ["DSE_WHISPER_PYTHON"] = keep
    C.WORKER = Path(C.__file__).with_name("whisper_worker.py")
    wavf = PM.AUDIO / "real.wav"
    ps = "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile('%s'); $s.Speak('Answer every review. Ask happy customers for a photo.'); $s.Dispose()" % str(wavf).replace("'", "''")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    res = C.make_captions("real.wav", say=lambda *_: None)
    txt = res.read_text(encoding="utf-8").lower()
    ok("REAL speech: a spoken sentence is heard and written as captions with the right words", "review" in txt and "photo" in txt and "customers" in txt)
    stamps = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", txt)
    secs = [(int(a[2]) + int(a[3]) / 1000, int(a[6]) + int(a[7]) / 1000) for a in stamps]
    ok("REAL speech: the captions are in time order, inside the recording, and the second sentence starts after the first", len(secs) >= 2 and all(s < e for s, e in secs) and all(secs[i][1] <= secs[i + 1][0] + 1e-6 for i in range(len(secs) - 1)) and secs[-1][1] < 8)

print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
