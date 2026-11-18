"""Presence make tools: a picture for a post (Pillow) and a video from scenes (ffmpeg). The HQ half of Citadel's Presence > Studio.

  python dse.py presence graphic --layout quote --headline "..." [--body ...] [--kicker ...] [--footer @handle] [--size post] [--theme ink] [--picture my-pictures/x.jpg] [--logo my-pictures/logo.png]
  python dse.py presence video my-video/project.json
  python dse.py presence carousel my-carousel/project.json

GRAPHIC. One finished PNG in my-graphics/: layouts quote, stat (a big number or phrase), tip, cover; sizes post (1080x1350), square, story (1080x1920), landscape (1920x1080), thumb (1280x720);
themes ink, cream, gold (the Citadel colours). Your own picture can sit behind the text (darkened so the words stay readable) and a logo can sit top left. Text is fitted to the box: it never runs off.
VIDEO. A project file (JSON, from the Studio's "video project" download or written by hand) lists scenes: each has on-screen text, optional picture, optional voiceover line and seconds. Each scene becomes
a card (your picture or a text card made by the graphic tool), moves slowly (a gentle zoom), and a voiceover is spoken with the Windows voice if voice is "windows", or your own recordings are used if voice is "own" (my-audio/<title>-scene-<n>.wav or mp3, m4a, aac, ogg). The spoken words are burned onto the card as captions unless captions is false. CAROUSEL. A carousel project (from the Studio) becomes every slide as a PNG in one go. The scenes are joined into an MP4 with an
.srt captions file next to it. Nothing is posted anywhere: you upload the finished file yourself.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import ROOT, slug

PICS = ROOT / "my-pictures"
GRAPHICS = ROOT / "my-graphics"
VIDEOS = ROOT / "my-video"
AUDIO = ROOT / "my-audio"
CAROUSELS = ROOT / "my-carousel"

SIZES = {"post": (1080, 1350), "square": (1080, 1080), "story": (1080, 1920), "landscape": (1920, 1080), "thumb": (1280, 720)}
THEMES = {  # background, text, accent
    "ink": ("#0f1115", "#f4efe6", "#d4a942"),
    "cream": ("#f6f0e4", "#1c1c1c", "#8a6a1f"),
    "gold": ("#d4a942", "#15130f", "#15130f"),
}
LAYOUTS = ("quote", "stat", "tip", "cover")
FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def _font(bold: bool, size: int):
    from PIL import ImageFont
    names = (["georgiab.ttf", "arialbd.ttf", "segoeuib.ttf"] if bold else ["georgia.ttf", "arial.ttf", "segoeui.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(str(FONT_DIR / n), size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _fit(draw, text: str, bold: bool, width: int, height: int, start: int, floor: int = 22):
    """Biggest font size (from start down to floor) whose wrapped text fits the box. Returns (font, lines, line_height)."""
    size = start
    while True:
        f = _font(bold, size)
        lines = _wrap(draw, text, f, width)
        lh = int(size * 1.22)
        if len(lines) * lh <= height or size <= floor:
            return f, lines, lh
        size -= 4


def _cover(img, w: int, h: int):
    from PIL import Image
    r = max(w / img.width, h / img.height)
    img = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def make_graphic(layout: str = "quote", headline: str = "", body: str = "", kicker: str = "", footer: str = "", size: str = "post", theme: str = "ink",
                 picture: str = "", logo: str = "", out_path: str | Path | None = None) -> Path:
    from PIL import Image, ImageDraw
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
    if size not in SIZES:
        raise ValueError(f"size must be one of {', '.join(SIZES)}")
    if theme not in THEMES:
        raise ValueError(f"theme must be one of {', '.join(THEMES)}")
    if not str(headline).strip():
        raise ValueError("The headline is empty: write the words that go on the picture.")
    W, H = SIZES[size]
    bg, fg, accent = THEMES[theme]
    img = Image.new("RGB", (W, H), bg)
    if picture:
        pp = _resolve(picture, PICS)
        photo = _cover(Image.open(pp).convert("RGB"), W, H)
        shade = Image.new("RGB", (W, H), "#0f1115")
        img = Image.blend(photo, shade, 0.62)
        fg, accent = "#f6f0e4", "#d4a942"
    d = ImageDraw.Draw(img)
    pad = int(W * 0.09)
    inner = W - 2 * pad
    top = pad
    if logo:
        lg = Image.open(_resolve(logo, PICS)).convert("RGBA")
        hgt = max(60, int(H * 0.06))
        lg = lg.resize((max(1, int(lg.width * hgt / lg.height)), hgt), Image.LANCZOS)
        img.paste(lg, (pad, pad), lg)
        top = pad + hgt + int(H * 0.02)
    # accent bar
    d.rectangle((pad, top, pad + int(W * 0.12), top + 8), fill=accent)
    y = top + 40
    if kicker.strip():
        kf = _font(True, max(26, int(W * 0.03)))
        d.text((pad, y), kicker.strip().upper()[:40], font=kf, fill=accent)
        y += int(W * 0.03) + 36
    foot_h = int(H * 0.08) if footer.strip() else 0
    avail = H - y - pad - foot_h
    body_h = int(avail * 0.30) if body.strip() else 0
    head_h = avail - body_h - (30 if body.strip() else 0)
    start = {"stat": int(W * 0.30), "cover": int(W * 0.12), "quote": int(W * 0.095), "tip": int(W * 0.085)}[layout]
    hf, hl, hlh = _fit(d, headline.strip(), True, inner, head_h, start)
    # a stat sits low in its box, a quote sits in the middle, others from the top
    used = len(hl) * hlh
    hy = y + (head_h - used) // 2 if layout in ("stat", "quote") else y
    for i, line in enumerate(hl):
        d.text((pad, hy + i * hlh), line, font=hf, fill=accent if layout == "stat" else fg)
    if body.strip():
        bf, bl, blh = _fit(d, body.strip(), False, inner, body_h, int(W * 0.045))
        by = y + head_h + 30
        for i, line in enumerate(bl):
            d.text((pad, by + i * blh), line, font=bf, fill=fg)
    if footer.strip():
        ff = _font(True, max(24, int(W * 0.028)))
        d.text((pad, H - pad - int(W * 0.03)), footer.strip()[:60], font=ff, fill=accent)
    GRAPHICS.mkdir(exist_ok=True)
    out = Path(out_path) if out_path else GRAPHICS / f"{slug(headline)[:40] or 'graphic'}-{layout}-{size}.png"
    img.save(out, "PNG")
    return out


def _resolve(name: str, folder: Path) -> Path:
    p = Path(name)
    for cand in (p, ROOT / p, folder / p.name):
        if cand.exists() and cand.is_file():
            return cand
    raise FileNotFoundError(f"I could not find the picture {name}. Put it in the my-pictures folder.")


# ---- video ----

def find_ffmpeg() -> str | None:
    f = shutil.which("ffmpeg")
    if f:
        return f
    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    return str(cand) if cand.exists() else None


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def make_srt(scenes: list[dict]) -> str:
    out, t, n = [], 0.0, 1
    for s in scenes:
        words = str(s.get("voice") or "").strip()
        if words:
            out.append(f"{n}\n{_srt_time(t)} --> {_srt_time(t + s['seconds'])}\n{words}\n")
            n += 1
        t += s["seconds"]
    return "\n".join(out)


def _burn_caption(card: Path, text: str, W: int, H: int) -> None:
    """Burns the spoken words onto the bottom of a scene card (a dark band so they stay readable), the way short videos show captions."""
    from PIL import Image, ImageDraw
    img = Image.open(card).convert("RGB")
    if img.size != (W, H):
        img = _cover(img, W, H)
    d = ImageDraw.Draw(img, "RGBA")
    pad = int(W * 0.06)
    f, lines, lh = _fit(d, text, True, W - 2 * pad, int(H * 0.2), int(W * 0.05), 26)
    top = H - int(H * 0.08) - len(lines) * lh - 24
    d.rectangle((0, top - 24, W, H), fill=(15, 17, 21, 190))
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        d.text(((W - tw) / 2, top + i * lh), line, font=f, fill="#f6f0e4")
    img.save(card, "PNG")


def _own_audio(title: str, n: int) -> Path | None:
    """The student's own recording for scene n: my-audio/<video title>-scene-<n>.wav (or mp3, m4a, aac, ogg)."""
    base = slug(title)
    for ext in ("wav", "mp3", "m4a", "aac", "ogg"):
        c = AUDIO / f"{base}-scene-{n}.{ext}"
        if c.exists():
            return c
    return None


def _duration(ff: str, path: Path) -> float | None:
    r = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def parse_project(raw: object) -> dict:
    """Reads a video project safely: a size, a voice choice and up to 30 scenes of 1 to 30 seconds."""
    if not isinstance(raw, dict) or not isinstance(raw.get("scenes"), list) or not raw["scenes"]:
        raise ValueError("The project needs a list of scenes.")
    size = raw.get("size") if raw.get("size") in SIZES else "story"
    scenes = []
    for s in raw["scenes"][:30]:
        if not isinstance(s, dict):
            continue
        text, voice = str(s.get("text") or "").strip()[:300], str(s.get("voice") or "").strip()[:600]
        if not text and not s.get("image"):
            continue
        try:
            sec = float(s.get("seconds") or 0)
        except (TypeError, ValueError):
            sec = 0
        sec = max(1.0, min(30.0, sec or max(3.0, len(voice.split()) / 2.5)))
        scenes.append({"text": text, "voice": voice, "image": str(s.get("image") or ""), "seconds": sec})
    if not scenes:
        raise ValueError("Every scene is empty.")
    return {"title": str(raw.get("title") or "video")[:80], "size": size, "theme": raw.get("theme") if raw.get("theme") in THEMES else "ink",
            "voice": raw.get("voice") if raw.get("voice") in ("windows", "own") else "none", "captions": raw.get("captions") is not False, "footer": str(raw.get("footer") or "")[:60], "scenes": scenes}


def _speak(text: str, wav: Path) -> float | None:
    """Windows' own voice to a WAV (no download, no account). Returns its length in seconds, or None when it cannot."""
    if os.name != "nt":
        return None
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.SetOutputToWaveFile($env:PRESENCE_WAV); $s.Speak($env:PRESENCE_TEXT); $s.Dispose()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env={**os.environ, "PRESENCE_WAV": str(wav), "PRESENCE_TEXT": text}, check=True, timeout=120, capture_output=True)
        import wave
        with wave.open(str(wav)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def make_video(project: dict, ffmpeg: str | None = None, out_path: str | Path | None = None, say=print) -> Path:
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg is not installed. Install it (winget install ffmpeg) and try again.")
    P = parse_project(project)
    W, H = SIZES[P["size"]]
    W, H = W - W % 2, H - H % 2
    VIDEOS.mkdir(exist_ok=True)
    out = Path(out_path) if out_path else VIDEOS / f"{slug(P['title'])[:40] or 'video'}.mp4"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clips: list[Path] = []
        for i, s in enumerate(P["scenes"], 1):
            card = td / f"card{i}.png"
            if s["image"]:
                from PIL import Image
                _cover(Image.open(_resolve(s["image"], GRAPHICS if (GRAPHICS / Path(s["image"]).name).exists() else PICS)).convert("RGB"), W, H).save(card)
            else:
                make_graphic("cover", s["text"] or P["title"], "", "", P["footer"], P["size"], P["theme"], out_path=card)
            wav = td / f"v{i}.wav"
            own = _own_audio(P["title"], i) if P["voice"] == "own" else None
            if P["voice"] == "own" and own is None:
                say(f"Scene {i}: no recording found (my-audio/{slug(P['title'])}-scene-{i}.wav), so it is silent.")
            if own is not None:
                wav = own
                length = _duration(ff, own)
                if length:
                    s["seconds"] = max(s["seconds"], round(min(length, 30) + 0.3, 2))
            elif P["voice"] == "windows" and s["voice"]:
                length = _speak(s["voice"], wav)
                if length:
                    s["seconds"] = max(s["seconds"], round(length + 0.4, 2))
                else:
                    say("The Windows voice did not work for this scene: it will be silent.")
            if P["captions"] and s["voice"]:
                _burn_caption(card, s["voice"], W, H)
            clip = td / f"clip{i}.mp4"
            frames = int(s["seconds"] * 30)
            zoom = f"zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
            cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-t", str(s["seconds"]), "-i", str(card)]
            if wav.exists():
                cmd += ["-i", str(wav)]
            else:
                cmd += ["-f", "lavfi", "-t", str(s["seconds"]), "-i", "anullsrc=r=44100:cl=mono"]
            cmd += ["-vf", f"scale={W * 2}:{H * 2},{zoom},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "44100", "-ac", "1", "-shortest", "-t", str(s["seconds"]), str(clip)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"ffmpeg stopped on scene {i}: {r.stderr.strip()[-300:]}")
            clips.append(clip)
            say(f"Scene {i} of {len(P['scenes'])}: {s['seconds']:.1f}s")
        lst = td / "list.txt"
        lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg could not join the scenes: {r.stderr.strip()[-300:]}")
    out.with_suffix(".srt").write_text(make_srt(P["scenes"]), encoding="utf-8")
    return out


def parse_carousel(raw: object) -> dict:
    """Reads a carousel project safely: up to 10 slides of a title and a body, a size, a theme and optional picture and logo."""
    if not isinstance(raw, dict) or not isinstance(raw.get("slides"), list) or not raw["slides"]:
        raise ValueError("The carousel needs a list of slides.")
    slides = []
    for sl in raw["slides"][:60]:
        if isinstance(sl, dict) and str(sl.get("title") or "").strip():
            slides.append({"title": str(sl["title"]).strip()[:200], "body": str(sl.get("body") or "").strip()[:300]})
        if len(slides) == 10:
            break
    if not slides:
        raise ValueError("Every slide is empty.")
    return {"title": str(raw.get("title") or "carousel")[:80], "size": raw.get("size") if raw.get("size") in SIZES else "post", "theme": raw.get("theme") if raw.get("theme") in THEMES else "ink",
            "footer": str(raw.get("footer") or "")[:60], "picture": str(raw.get("picture") or "")[:200], "logo": str(raw.get("logo") or "")[:200], "slides": slides}


def make_carousel(project: dict, out_dir: str | Path | None = None, say=print) -> list[Path]:
    """Every slide of a carousel as a finished PNG in my-graphics (cover, points, last slide with your name), in one go."""
    P = parse_carousel(project)
    out = Path(out_dir) if out_dir else GRAPHICS
    out.mkdir(parents=True, exist_ok=True)
    base, n, files = slug(P["title"])[:30] or "carousel", len(P["slides"]), []
    for i, sl in enumerate(P["slides"], 1):
        layout = "cover" if i == 1 else "tip"
        kicker = f"{i} / {n}"
        files.append(make_graphic(layout, sl["title"], sl["body"], kicker, P["footer"] if i == n else "", P["size"], P["theme"], P["picture"], P["logo"], out_path=out / f"{base}-{i:02}.png"))
        say(f"Slide {i} of {n}")
    return files


def cli(args: list[str]) -> int:
    kind = args[0] if args else ""
    rest = args[1:]
    try:
        if kind == "graphic":
            opts = {"layout": "quote", "headline": "", "body": "", "kicker": "", "footer": "", "size": "post", "theme": "ink", "picture": "", "logo": ""}
            i = 0
            while i < len(rest):
                k = rest[i].lstrip("-")
                if k in opts and i + 1 < len(rest):
                    opts[k] = rest[i + 1]
                    i += 2
                else:
                    print(f"I do not know {rest[i]}.")
                    return 2
            out = make_graphic(**opts)
            print(f"Saved {out.name} in my-graphics ({SIZES[opts['size']][0]}x{SIZES[opts['size']][1]}). Post it yourself.")
            return 0
        if kind == "video":
            if not rest:
                print("Give the project file, for example: python dse.py presence video my-video/project.json")
                return 2
            p = _resolve(rest[0], VIDEOS)
            out = make_video(json.loads(p.read_text(encoding="utf-8")))
            print(f"Saved {out.name} and {out.with_suffix('.srt').name} in my-video. Upload it yourself.")
            return 0
        if kind == "carousel":
            if not rest:
                print("Give the project file, for example: python dse.py presence carousel my-carousel/project.json")
                return 2
            p = _resolve(rest[0], CAROUSELS)
            files = make_carousel(json.loads(p.read_text(encoding="utf-8")))
            print(f"Saved {len(files)} slides in my-graphics ({files[0].name} to {files[-1].name}). Post them in order, yourself.")
            return 0
    except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e))
        return 1
    print(__doc__)
    return 2
