"""Presence captions: turns a voiceover (or any video or sound with speech) into a captions file (.srt) on this PC, for Presence > Edit.

  python dse.py presence captions my-audio/<voiceover>.mp3 [--model base.en]
  python dse.py presence captions --setup        (how to set the speech tool up, once)

The speech is read by faster-whisper, a free speech-to-text program that runs on this PC: nothing is uploaded. The first run downloads its model once (base.en is about 145 MB).
It lives in its own small Python environment because the speech libraries do not have builds for every Python yet.
The words are grouped into short captions the way Reels and TikTok show them (a few words at a time, breaking at full stops and pauses) and saved as <name>.srt next to the file,
ready for the editor: Presence > Edit > "Captions file (.srt)". The file is found by its name in my-audio, my-video, then my-graphics.
Always read the captions before posting: speech-to-text makes mistakes, especially with names, accents and noise.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import presence_make as PM
from .common import ROOT

WORKER = Path(__file__).with_name("whisper_worker.py")   # run by the speech environment
MODELS = ("tiny.en", "base.en", "small.en")
MAX_WORDS, MAX_SECONDS, PAUSE, MIN_SECONDS, MAX_CHARS = 6, 2.8, 0.6, 0.3, 120
END_MARK = re.compile(r"[.!?…]$")
SETUP = """One-time setup of the speech tool (about 400 MB of disk, internet needed once):
  1. winget install --id Python.Python.3.12 -e --scope user
  2. py -3.12 -m venv "<HQ folder>\\_tools\\whisper-venv"
  3. "<HQ folder>\\_tools\\whisper-venv\\Scripts\\python.exe" -m pip install faster-whisper
The first captions run then downloads the model (base.en, about 145 MB).
You can also point the DSE_WHISPER_PYTHON environment variable at any Python that has faster-whisper installed."""


def _t(s: float) -> str:
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms % 3600000 // 60000:02}:{ms % 60000 // 1000:02},{ms % 1000:03}"


def group_words(words: list[dict]) -> list[dict]:
    """Groups timed words into caption cues. A sentence (ended by . ! ? or by a pause of 0.6 s) is one cue if it fits: at most 6 words, 2.8 seconds and 120 characters.
    A longer one is cut into the fewest pieces that fit, with the words shared out evenly (so no cue is left holding one stray word).
    A cue starts with its first word and ends with its last (never into the next cue), and none is shorter than 0.3 s."""
    clean = []
    for w in words or []:
        try:
            a, b, t = float(w["start"]), float(w["end"]), str(w["w"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if t and a == a and b == b and b >= a >= 0:
            clean.append({"w": t, "start": a, "end": b})
    clean.sort(key=lambda x: x["start"])
    sentences: list[list[dict]] = []
    cur: list[dict] = []
    for w in clean:
        if cur and w["start"] - cur[-1]["end"] > PAUSE:
            sentences.append(cur)
            cur = []
        cur.append(w)
        if END_MARK.search(w["w"]):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    cues: list[dict] = []
    for sen in sentences:
        chars = len(" ".join(x["w"] for x in sen))
        secs = sen[-1]["end"] - sen[0]["start"]
        n = max(1, -(-len(sen) // MAX_WORDS), -(-int(secs * 1000) // int(MAX_SECONDS * 1000)), -(-chars // MAX_CHARS))
        n = min(n, len(sen))
        at = 0
        for k in range(n):
            size = len(sen) // n + (1 if k < len(sen) % n else 0)
            part = sen[at:at + size]
            at += size
            cues.append({"start": part[0]["start"], "end": part[-1]["end"], "text": " ".join(x["w"] for x in part)})
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else c["end"] + MIN_SECONDS
        c["end"] = min(max(c["end"], c["start"] + MIN_SECONDS), max(nxt, c["end"]))
    return [{"start": round(c["start"], 3), "end": round(c["end"], 3), "text": c["text"]} for c in cues]


def to_srt(cues: list[dict]) -> str:
    return "\n".join(f"{i}\n{_t(c['start'])} --> {_t(c['end'])}\n{c['text']}\n" for i, c in enumerate(cues, 1))


def find_python() -> Path | None:
    """The Python that has faster-whisper: DSE_WHISPER_PYTHON, the toolkit's own whisper-venv, then the HQ folder's _tools/whisper-venv."""
    env = os.environ.get("DSE_WHISPER_PYTHON", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    for folder in (ROOT / "whisper-venv", ROOT.parent / "_tools" / "whisper-venv"):
        for rel in ("Scripts/python.exe", "bin/python"):
            if (folder / rel).is_file():
                return folder / rel
    return None


def find_media(name: str) -> Path | None:
    """The file with that NAME (only the file name is used, never a path) in my-audio, my-video or my-graphics."""
    base = Path(str(name).replace("\\", "/")).name
    if not base:
        return None
    for folder in (PM.AUDIO, PM.VIDEOS, PM.GRAPHICS):
        p = folder / base
        if p.is_file():
            return p
    return None


def transcribe(media: Path, model: str = "base.en", say=print) -> list[dict]:
    py = find_python()
    if not py:
        raise RuntimeError("The speech tool is not set up on this PC yet.\n" + SETUP)
    ff = PM.find_ffmpeg()
    with tempfile.TemporaryDirectory() as td:
        wav, out = Path(td) / "speech.wav", Path(td) / "words.json"
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", str(wav)], capture_output=True, text=True)
        if r.returncode != 0 or not wav.is_file():
            raise RuntimeError(f"ffmpeg could not read the sound of {media.name}: {r.stderr.strip()[:200]}")
        say(f"Listening to {media.name} with {model} (the first time it downloads the model, about 145 MB)...")
        r = subprocess.run([str(py), str(WORKER), str(wav), model, str(out)], capture_output=True, text=True)
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError("The speech tool failed: " + (r.stderr.strip().splitlines() or ["no message"])[-1][:300])
        return json.loads(out.read_text(encoding="utf-8")).get("words", [])


def make_captions(name: str, model: str = "base.en", say=print) -> Path:
    media = find_media(name)
    if not media:
        raise RuntimeError(f"I could not find {Path(str(name).replace(chr(92), '/')).name}. Put it in the my-audio or my-video folder.")
    if model not in MODELS:
        raise RuntimeError(f"Model {model} is not one of {', '.join(MODELS)}.")
    cues = group_words(transcribe(media, model, say))
    if not cues:
        raise RuntimeError("No speech was found in that file (silent, music only or too noisy).")
    out = media.with_name(media.stem + ".srt")
    if out.exists() and out.stat().st_size > 0:
        out = media.with_name(media.stem + "-captions.srt")
    out.write_text(to_srt(cues), encoding="utf-8")
    say(f"Saved {out.name} in {out.parent.name}: {len(cues)} captions. Read it and fix any mistakes, then in Presence > Edit press 'Captions file (.srt)'.")
    return out


def cli(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if args[0] == "--setup":
        print(SETUP)
        return 0
    model, rest = "base.en", list(args)
    if "--model" in rest:
        i = rest.index("--model")
        model = rest[i + 1] if i + 1 < len(rest) else model
        del rest[i:i + 2]
    if not rest:
        print("Give the voiceover file, for example: python dse.py presence captions my-audio/voiceover.mp3")
        return 1
    try:
        make_captions(rest[0], model)
    except RuntimeError as e:
        print(e)
        return 1
    return 0
