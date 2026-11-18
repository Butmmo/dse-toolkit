"""Presence: solid 3D videos with Blender (18 Nov 2026).

Blender is a free, open-source 3D program. Presence uses it, on THIS PC, to draw each scene of a faceless video as real 3D text (extruded, lit, with a slowly moving camera) in the colours and fonts of the
student's design kit, instead of a flat card with a zoom. The result is a PNG sequence per scene that the normal video tool (dse/presence_make.py) joins with the voice and the captions. Nothing is sent
anywhere and nothing is posted.

  python dse.py presence blender-setup [--to FOLDER]   downloads Blender (the official portable zip from download.blender.org, about 400 MB), checks it against the published checksum and unpacks it
  python dse.py presence blender-check                 says where Blender is and whether it can draw a scene

Where Blender is looked for, in this order: the BLENDER environment variable, the toolkit's own `blender` folder, the HQ folder's `_tools/blender`, Program Files. If it is not found, or a scene fails, the
video tool falls back to its normal cards and says so: a video is never lost because Blender is missing.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "4.5.16"
SERIES = "4.5"
ZIP = f"blender-{VERSION}-windows-x64.zip"
BASE = f"https://download.blender.org/release/Blender{SERIES}/"
FRAME_W = 9.0                                                                  # the frame is 9 Blender units wide (see blender_scene.py)
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
HEAD_FONTS = {"serif": ("georgiab.ttf", "georgia.ttf"), "sans": ("segoeuib.ttf", "arialbd.ttf"), "display": ("ariblk.ttf", "arialbd.ttf")}
MOVES = ("dolly", "drift", "still")
SAMPLES = {"draft": 8, "high": 24}                                            # Cycles samples per pixel: 8 looks clean once the video is compressed (16 took a third longer for no visible gain)
FPS = 24


def _exe_in(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    for p in sorted(folder.glob("blender*/blender.exe")) + sorted(folder.glob("blender.exe")):
        if p.is_file():
            return p
    return None


def find_blender() -> Path | None:
    env = os.environ.get("BLENDER")
    if env and Path(env).is_file():
        return Path(env)
    for folder in (ROOT / "blender", ROOT.parent / "_tools" / "blender"):
        p = _exe_in(folder)
        if p:
            return p
    pf = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Blender Foundation"
    if pf.is_dir():
        for sub in sorted(pf.iterdir(), reverse=True):
            if (sub / "blender.exe").is_file():
                return sub / "blender.exe"
    w = shutil.which("blender")
    return Path(w) if w else None


def _font(head: str) -> str:
    for n in HEAD_FONTS.get(head, HEAD_FONTS["sans"]):
        if (FONT_DIR / n).is_file():
            return (FONT_DIR / n).as_posix()
    return ""


def _wrap(text: str, per_line: int) -> str:
    out, cur = [], ""
    for w in str(text).split():
        if cur and len(cur) + 1 + len(w) > per_line:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return "\n".join(out)


def scene_spec(text: str, kit: dict, size: tuple[int, int], frames: int, move: str = "dolly", samples: int = 24, stat=None, fps: int = FPS) -> dict:
    """The scene as Blender needs it: blocks of text with a size, a colour and a height, the page colour and a small bar. Pure: tested without Blender.
    `stat` is (big figure, rest) when the scene leads with a number: then the figure is drawn very large in the accent colour and the rest under it."""
    W, H = size
    aspect = H / W
    frame_h = FRAME_W * aspect
    head = _font(kit.get("head", "sans"))
    body_font = _font("sans")
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:160] or " "
    blocks = []
    if stat and stat[0]:
        big, rest = str(stat[0])[:14], str(stat[1] or "")[:110]
        bsize = 2.6 if len(big) <= 6 else 1.9 if len(big) <= 9 else 1.4
        fy = 0.18 * frame_h if rest else 0.03 * frame_h                       # a figure alone sits in the middle; with words under it the pair is centred
        blocks.append({"text": big, "color": kit["accent"], "size": bsize, "y": fy, "font": head, "depth": 0.12, "tilt": 14})
        if rest:
            per = 26
            blocks.append({"text": _wrap(rest, per), "color": kit["fg"], "size": 0.78, "y": -0.05 * frame_h - 0.2, "font": body_font, "depth": 0.05})
        bar_y = 0.07 * frame_h if rest else fy - bsize * 0.75 - 0.3
        bar = {"color": kit["accent"], "y": bar_y, "w": 1.6}
    else:
        n = len(text)
        sz = 1.25 if n <= 24 else 1.0 if n <= 48 else 0.82 if n <= 80 else 0.66
        per = max(8, int(FRAME_W * 0.86 / (sz * 0.56)))
        wrapped = _wrap(text, per)
        lines = wrapped.count("\n") + 1
        blocks.append({"text": wrapped, "color": kit["fg"], "size": sz, "y": 0.0, "font": head, "depth": 0.1})
        bar = {"color": kit["accent"], "y": -(lines * sz * 0.62) - 0.7, "w": 1.1}
    n_frames = max(1, int(frames))
    return {"width": W, "height": H, "frames": n_frames, "intro": 0 if n_frames < 8 or move == "still" else min(int(fps * 0.7), n_frames // 2), "fps": int(fps), "engine": "CYCLES", "samples": int(samples), "bg": kit["bg"], "blocks": blocks, "bar": bar,
            "move": move if move in MOVES else "dolly", "cam_z": 0}


def render_scene(spec: dict, out_dir: Path, blender: Path | None = None, timeout: int = 900) -> list[Path]:
    """Draws the scene with Blender and returns the frames in order. Raises RuntimeError with a plain message if Blender is missing or fails."""
    exe = blender or find_blender()
    if not exe:
        raise RuntimeError("Blender is not installed (run: python dse.py presence blender-setup).")
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = {**spec, "out": out_dir.as_posix()}
    sp = out_dir / "spec.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    r = subprocess.run([str(exe), "-b", "--factory-startup", "-P", str(ROOT / "dse" / "blender_scene.py"), "--", str(sp)], capture_output=True, text=True, timeout=timeout)
    frames = sorted(out_dir.glob("f_*.png"))
    if r.returncode != 0 or not frames:
        raise RuntimeError("Blender could not draw the scene: " + (r.stderr.strip() or r.stdout.strip())[-300:])
    return frames


def frames_to_clip(ff: str, frames: list[Path], seconds: float, size: tuple[int, int], out: Path, fps_in: int = FPS) -> Path:
    """The frames as a smooth clip of the scene's length (the last frame holds if the scene is longer than the animation), at 30 frames a second, scaled up to the video size."""
    W, H = size
    first = frames[0]
    pattern = str(first.parent / "f_%04d.png")
    vf = f"tpad=stop_mode=clone:stop_duration={max(0.0, seconds):.2f},fps=30,scale={W}:{H}:flags=lanczos,format=yuv420p"
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps_in), "-i", pattern, "-vf", vf, "-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-an", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg could not build the 3D clip: " + r.stderr.strip()[-300:])
    return out


# ---- installing Blender (the official portable zip, checked against the published checksum) ----

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install_blender(dest: str | Path | None = None, say=print, get=None) -> int:
    """Downloads Blender's portable zip from download.blender.org (about 400 MB), checks its SHA-256 against the checksum file published next to it, and unpacks it. `get` is for tests."""
    import requests
    dest = Path(dest) if dest else ROOT / "blender"
    exe = _exe_in(dest)
    if exe:
        say(f"Blender is already here: {exe}")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    work = dest / "_download"
    work.mkdir(exist_ok=True)
    zp = work / ZIP
    g = get or requests.get
    try:
        sums = g(BASE + f"blender-{VERSION}.sha256", timeout=30)
        sums.raise_for_status()
        want = next((ln.split()[0] for ln in sums.text.splitlines() if ln.strip().endswith(ZIP)), "")
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            say("I could not read the published checksum, so I will not install this file.")
            return 1
        if not (zp.exists() and _sha256(zp) == want):
            say(f"Downloading {ZIP} from download.blender.org (about 400 MB, this takes a few minutes)...")
            with g(BASE + ZIP, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(zp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        if _sha256(zp) != want:
            zp.unlink(missing_ok=True)
            say("The downloaded file does not match the published checksum, so it was deleted and nothing was installed. Try again.")
            return 1
    except Exception as e:                                                      # no network, a refused download, a full disk
        say(f"Could not download Blender: {e}")
        return 1
    with zipfile.ZipFile(zp) as z:
        root = dest.resolve()
        for n in z.namelist():
            if not (root / n).resolve().is_relative_to(root):                   # a zip may never write outside the folder
                say("The zip has a path outside its folder: not unpacked.")
                return 1
        z.extractall(dest)
    zp.unlink(missing_ok=True)
    exe = _exe_in(dest)
    say(f"Blender {VERSION} is installed: {exe}" if exe else "Unpacked, but blender.exe was not found.")
    return 0 if exe else 1


def check(say=print) -> int:
    exe = find_blender()
    if not exe:
        say("Blender was not found. Run: python dse.py presence blender-setup")
        return 1
    r = subprocess.run([str(exe), "--version"], capture_output=True, text=True)
    say(f"Blender found: {exe} ({(r.stdout.splitlines() or ['?'])[0]})")
    return 0
