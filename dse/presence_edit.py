"""Presence edit render: makes the finished MP4 of a video edited in Citadel's Presence > Edit, on this PC with ffmpeg. For long or full-size videos the browser is slow at.

  python dse.py presence edit-render my-video/<title>.edit.json [--draft]

The project file comes from Presence > Edit ("Make it on my PC"). It lists the clips (video, picture or plain colour), the text and caption layers and the sounds, with the NAMES of your files, not the files.
Put those files in the my-video folder (pictures may be in my-pictures, sounds in my-audio) and run this tool. It checks every file is there first and says which are missing.
Every clip is cut and made the size of the video (filling the frame, the overflow cropped), the clips are joined, text and captions are drawn on top (same look as the editor's preview), the sounds are mixed under it,
and the MP4 and a captions file (.srt) are saved in my-video. --draft makes half size, quicker. The rules (90 seconds, 12 clips, sizes) are the editor's: src/lib/presence-edit.ts in Citadel; keep the two in step.
Nothing is posted anywhere: you upload the finished file yourself.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from .common import slug
from . import presence_make as PM

PRESETS = {"reels": (1080, 1920), "tiktok": (1080, 1920), "shorts": (1080, 1920), "square": (1080, 1080), "landscape": (1920, 1080)}
MAX_SECONDS, MAX_CLIPS, MAX_TEXTS, MAX_AUDIO = 90.0, 12, 60, 4
MIN_CLIP, MIN_TEXT, MAX_PICTURE = 0.2, 0.3, 30.0
SPEEDS = (0.5, 0.75, 1, 1.25, 1.5, 2)   # a video clip plays at one of these (1 = normal); the same list as the editor
MAX_FADE = 1.0
LOOK_RANGE = {"bright": (0.5, 1.5), "contrast": (0.5, 1.5), "sat": (0.0, 2.0)}   # a clip's colours: brightness and contrast 0.5 to 1.5, colour strength 0 to 2; 1 = unchanged (the editor's ranges)
MAX_MIX = 1.0   # seconds a clip may blend (a crossfade) with the one before it, at most half of either clip
FPS = 30
FONTS = ("sans", "serif", "mono")
MOTIONS = ("none", "rise", "drop", "slide")
MOTION_S = 0.4      # seconds a text takes to move into place (at most half of its time on screen)
MOVE_Y, MOVE_SLIDE = 0.06, 0.3   # how far it travels: share of the picture height (rise, drop) or width (slide)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# folders searched for the named files, in this order
def _folders() -> list[Path]:
    return [PM.VIDEOS, PM.PICS, PM.AUDIO, PM.GRAPHICS]


def _num(v, lo: float, hi: float, d: float) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return d
    if n != n or n in (float("inf"), float("-inf")):
        return d
    return min(hi, max(lo, n))


def _look(c: dict, key: str) -> float:
    """A clip's brightness, contrast or colour strength inside its range; missing, empty or null means 1, so an empty colour strength is never read as 0 (black and white)."""
    v = c.get(key)
    lo, hi = LOOK_RANGE[key]
    return 1.0 if v is None or v == "" or isinstance(v, bool) else _r3(_num(v, lo, hi, 1.0))


def _r3(n: float) -> float:
    return round(n * 1000) / 1000


def _clean(v, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v)[:n] if isinstance(v, str) else ""


def _hex(v, d: str) -> str:
    return v.lower() if isinstance(v, str) and HEX.match(v) else d


def parse_edit(raw: object) -> dict:
    """Reads an editor project safely (the same limits as the editor): at most 12 clips and 90 seconds in all, 60 text layers, 4 sounds. Raises ValueError with a plain sentence when it is not a project."""
    if not isinstance(raw, dict) or raw.get("v") != 1 or not isinstance(raw.get("clips"), list):
        raise ValueError("That is not a project saved by Presence > Edit.")
    preset = raw.get("preset") if raw.get("preset") in PRESETS else "reels"
    clips, total = [], 0.0
    for c in raw["clips"][:MAX_CLIPS]:
        if not isinstance(c, dict) or c.get("kind") not in ("video", "picture", "color"):
            continue
        kind = c["kind"]
        src_seconds = _num(c.get("srcSeconds"), 0, 36000, 0) if kind == "video" else 0.0
        inn = _num(c.get("in"), 0, max(0.0, src_seconds - MIN_CLIP), 0) if kind == "video" else 0.0
        hard = src_seconds if kind == "video" else MAX_PICTURE
        out = _num(c.get("out"), inn + MIN_CLIP, max(inn + MIN_CLIP, hard), inn + 3)
        room = _r3(MAX_SECONDS - total)
        if room < MIN_CLIP:
            break
        speed = c.get("speed") if kind == "video" and c.get("speed") in SPEEDS else 1
        name = _clean(c.get("name"), 60) or kind
        length = _r3((_r3(out) - _r3(inn)) / speed)
        prev_len = clips[-1]["seconds"] if clips else 0.0
        # a blend (crossfade) with the clip before: at most 1 s and half of either clip, none for the first clip
        mix = _r3(min(MAX_MIX, _num(c.get("mix"), 0, MAX_MIX, 0), prev_len / 2, length / 2)) if clips else 0.0
        # the clip adds its length minus its blend to the video; shorten it when that would pass 90 seconds
        over = _r3(length - mix - room)
        if over > 0:
            if length - over < MIN_CLIP:
                break
            out = _r3(_r3(out) - over * speed)
            length = _r3((_r3(out) - _r3(inn)) / speed)
            mix = _r3(min(mix, length / 2))
            if length - mix > room + 1e-6:
                break
        fi = _r3(min(MAX_FADE, _num(c.get("fadeIn"), 0, MAX_FADE, 0), length))
        fo = _r3(min(MAX_FADE, _num(c.get("fadeOut"), 0, MAX_FADE, 0), length - fi))
        start = _r3(max(0.0, total - mix)) if clips else 0.0
        clips.append({"kind": kind, "name": name, "in": _r3(inn), "out": _r3(out), "muted": c.get("muted") is True, "color": _hex(c.get("color"), "#14110f"), "speed": speed, "fadeIn": fi, "fadeOut": fo, "mix": mix, "start": start, "seconds": length,
                      "bright": _look(c, "bright"), "contrast": _look(c, "contrast"), "sat": _look(c, "sat")})
        total = _r3(start + length)
    if not clips:
        raise ValueError("The project has no clips.")
    texts = []
    for t in (raw.get("texts") if isinstance(raw.get("texts"), list) else [])[:MAX_TEXTS]:
        if not isinstance(t, dict):
            continue
        role = "caption" if t.get("role") == "caption" else "text"
        start = _r3(_num(t.get("start"), 0, total, 0))
        end = _r3(max(start + MIN_TEXT, _num(t.get("end"), 0, max(MIN_TEXT, total), start + 2)))
        end = min(end, max(total, start + MIN_TEXT))
        texts.append({"role": role, "text": _clean(t.get("text"), 120), "start": start, "end": end, "x": _r3(_num(t.get("x"), 0, 1, 0.5)), "y": _r3(_num(t.get("y"), 0, 1, 0.74 if role == "caption" else 0.45)),
                      "size": _r3(_num(t.get("size"), 0.02, 0.12, 0.045 if role == "caption" else 0.07)), "color": _hex(t.get("color"), "#ffffff"), "bold": t.get("bold") is not False,
                      "font": t.get("font") if t.get("font") in FONTS else "sans", "fade": t.get("fade") is not False,
                      "motion": t.get("motion") if t.get("motion") in MOTIONS else "none"})
    audio = []
    for a in (raw.get("audio") if isinstance(raw.get("audio"), list) else [])[:MAX_AUDIO]:
        if not isinstance(a, dict):
            continue
        src_seconds = _num(a.get("srcSeconds"), 0, 36000, 0)
        name = _clean(a.get("name"), 60)
        if not name or src_seconds < MIN_CLIP:
            continue
        inn = _num(a.get("in"), 0, src_seconds - MIN_CLIP, 0)
        out = _num(a.get("out"), inn + MIN_CLIP, src_seconds, src_seconds)
        audio.append({"name": name, "in": _r3(inn), "out": _r3(out), "start": _r3(_num(a.get("start"), 0, MAX_SECONDS, 0)), "volume": _r3(_num(a.get("volume"), 0, 1, 1)),
                      "fadeOut": _r3(_num(a.get("fadeOut"), 0, min(5.0, out - inn), 0))})
    return {"title": _clean(raw.get("title"), 80) or "video", "preset": preset, "clips": clips, "texts": texts, "audio": audio, "seconds": total}


def needed_files(P: dict) -> list[str]:
    """The names of the files the project uses (colour clips need none), each once, in order."""
    seen: list[str] = []
    for n in [c["name"] for c in P["clips"] if c["kind"] != "color"] + [a["name"] for a in P["audio"]]:
        if n not in seen:
            seen.append(n)
    return seen


def find_file(name: str, extra: Path | None = None) -> Path | None:
    """A file by its name, in my-video, my-pictures, my-audio or my-graphics (or next to the project). Only the file name counts: a path in the name is ignored, so a project cannot reach other folders."""
    base = Path(str(name).replace("\\", "/")).name
    if not base:
        return None
    for d in ([extra] if extra else []) + _folders():
        p = Path(d) / base
        if p.is_file():
            return p
    return None


def missing_files(P: dict, extra: Path | None = None) -> list[str]:
    return [n for n in needed_files(P) if find_file(n, extra) is None]


def make_srt(P: dict) -> str:
    def t(s: float) -> str:
        ms = round(s * 1000)
        return f"{ms // 3600000:02}:{ms % 3600000 // 60000:02}:{ms % 60000 // 1000:02},{ms % 1000:03}"
    caps = sorted((x for x in P["texts"] if x["role"] == "caption" and x["text"].strip()), key=lambda x: x["start"])
    return "\n".join(f"{i}\n{t(x['start'])} --> {t(x['end'])}\n{x['text'].strip()}\n" for i, x in enumerate(caps, 1))


# ---------------------------------------------------------------- text layers as pictures (the same look as the editor's preview)

_FONT_FILES = {
    ("sans", True): ["segoeuib.ttf", "arialbd.ttf"], ("sans", False): ["segoeui.ttf", "arial.ttf"],
    ("serif", True): ["georgiab.ttf", "timesbd.ttf"], ("serif", False): ["georgia.ttf", "times.ttf"],
    ("mono", True): ["consolab.ttf", "courbd.ttf"], ("mono", False): ["consola.ttf", "cour.ttf"],
}


def _edit_font(key: str, bold: bool, px: int):
    from PIL import ImageFont
    for n in _FONT_FILES[(key, bold)]:
        try:
            return ImageFont.truetype(str(PM.FONT_DIR / n), px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(px)
    except TypeError:
        return ImageFont.load_default()


def text_layer_png(layer: dict, W: int, H: int, path: Path) -> Path:
    """One text or caption layer as a transparent W x H picture: wrapped to 86% of the width, centred on its place, white (or its colour) with a dark outline so it reads on any picture."""
    from PIL import Image, ImageDraw
    px = max(8, round(layer["size"] * H))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = _edit_font(layer["font"], layer["bold"], px)
    lines = PM._wrap(d, layer["text"].strip(), f, int(W * 0.86))
    lh = px * 1.22
    top = layer["y"] * H - ((len(lines) - 1) * lh) / 2
    outline = max(1, round(max(2, px * 0.14) / 2))
    for i, line in enumerate(lines):
        d.text((layer["x"] * W, top + i * lh), line, font=f, fill=layer["color"], anchor="mm", stroke_width=outline, stroke_fill=(0, 0, 0, 199))
    img.save(path, "PNG")
    return path


# ---------------------------------------------------------------- the render

def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg stopped on {what}: {r.stderr.strip()[-400:]}")


def _has_audio(ff: str, path: Path) -> bool:
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return "Audio:" in r.stderr


def _segment(ff: str, c: dict, path_of: dict, W: int, H: int, out: Path, crf: str, preset: str) -> None:
    length = c["seconds"]                      # how long it plays on the timeline (the file's stretch divided by the speed)
    taken = _r3(c["out"] - c["in"])            # how much of the file it uses
    speed = c["speed"]
    vf = (f"setpts=PTS/{speed}," if speed != 1 else "") + f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    # the clip's look comes before its fades (so a fade to black stays black): brightness, then contrast, then colour strength, as in the editor
    if c["bright"] != 1:
        vf += f",colorchannelmixer=rr={c['bright']}:gg={c['bright']}:bb={c['bright']}"
    if c["contrast"] != 1 or c["sat"] != 1:
        vf += f",eq=contrast={c['contrast']}:saturation={c['sat']}"
    if c["fadeIn"] > 0:
        vf += f",fade=t=in:st=0:d={c['fadeIn']}"
    if c["fadeOut"] > 0:
        vf += f",fade=t=out:st={_r3(length - c['fadeOut'])}:d={c['fadeOut']}"
    vf += ",format=yuv420p"
    cmd = [ff, "-y", "-loglevel", "error"]
    audio_from = None
    if c["kind"] == "video":
        src = path_of[c["name"]]
        cmd += ["-ss", str(c["in"]), "-t", str(taken), "-i", str(src)]
        if not c["muted"] and _has_audio(ff, src):
            audio_from = "0:a:0"
    elif c["kind"] == "picture":
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", str(length), "-i", str(path_of[c["name"]])]
    else:
        cmd += ["-f", "lavfi", "-t", str(length), "-i", f"color=c={c['color']}:s={W}x{H}:r={FPS}"]
    if audio_from is None:
        cmd += ["-f", "lavfi", "-t", str(length), "-i", "anullsrc=r=48000:cl=stereo"]
        amap, af = "1:a:0", "aformat=sample_fmts=fltp:channel_layouts=stereo"
    else:
        amap, af = audio_from, "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo" + (f",atempo={speed}" if speed != 1 else "")
        if c["fadeIn"] > 0:
            af += f",afade=t=in:st=0:d={c['fadeIn']}"
        if c["fadeOut"] > 0:
            af += f",afade=t=out:st={_r3(length - c['fadeOut'])}:d={c['fadeOut']}"
        af += f",apad=whole_dur={length}"
    cmd += ["-map", "0:v:0", "-map", amap, "-vf", vf, "-af", af, "-c:v", "libx264", "-preset", preset, "-crf", crf, "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", str(length), str(out)]
    _run(cmd, f"the clip {c['name']}")


def render_edit(project: dict, ffmpeg: str | None = None, out_path: str | Path | None = None, draft: bool = False, extra: Path | None = None, say=print) -> Path:
    ff = ffmpeg or PM.find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg is not installed. Install it (winget install ffmpeg) and try again.")
    P = parse_edit(project)
    gone = missing_files(P, extra)
    if gone:
        raise FileNotFoundError("These files are not in my-video yet (or my-pictures, my-audio): " + ", ".join(gone) + ". Put them there with exactly these names and run it again.")
    path_of = {n: find_file(n, extra) for n in needed_files(P)}
    W, H = PRESETS[P["preset"]]
    if draft:
        W, H = W // 2, H // 2
    W, H = W - W % 2, H - H % 2
    crf, preset = ("26", "veryfast") if draft else ("20", "medium")
    total = P["seconds"]
    PM.VIDEOS.mkdir(exist_ok=True)
    out = Path(out_path) if out_path else PM.VIDEOS / f"{slug(P['title'])[:40] or 'video'}{'-draft' if draft else ''}.mp4"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        segs = []
        for i, c in enumerate(P["clips"], 1):
            seg = td / f"clip{i}.mp4"
            _segment(ff, c, path_of, W, H, seg, crf, preset)
            segs.append(seg)
            say(f"Clip {i} of {len(P['clips'])}: {c['name']}")
        base = td / "base.mp4"
        if any(c["mix"] > 0 for c in P["clips"]):
            # the clips are joined in one pass: a blend overlaps the two (xfade for the picture, acrossfade for the sound), a plain junction just follows on
            cmd = [ff, "-y", "-loglevel", "error"]
            for sg in segs:
                cmd += ["-i", str(sg)]
            chains, v, a, acc = [], "[0:v]", "[0:a]", P["clips"][0]["seconds"]
            for i in range(1, len(segs)):
                c = P["clips"][i]
                if c["mix"] > 0:
                    chains.append(f"{v}[{i}:v]xfade=transition=fade:duration={c['mix']}:offset={_r3(acc - c['mix'])}[v{i}]")
                    chains.append(f"{a}[{i}:a]acrossfade=d={c['mix']}[a{i}]")
                    acc = _r3(acc + c["seconds"] - c["mix"])
                else:
                    chains.append(f"{v}[{i}:v]concat=n=2:v=1:a=0[v{i}]")
                    chains.append(f"{a}[{i}:a]concat=n=2:v=0:a=1[a{i}]")
                    acc = _r3(acc + c["seconds"])
                v, a = f"[v{i}]", f"[a{i}]"
            cmd += ["-filter_complex", ";".join(chains), "-map", v, "-map", a, "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(base)]
            _run(cmd, "blending the clips")
        else:
            lst = td / "list.txt"
            lst.write_text("".join("file '" + s.as_posix().replace("'", "'\\''") + "'\n" for s in segs), encoding="utf-8")
            _run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)], "joining the clips")
        texts = [t for t in P["texts"] if t["text"].strip() and t["start"] < total - 0.05]
        sounds = [(a, path_of[a["name"]]) for a in P["audio"] if a["start"] < total]
        if not texts and not sounds:
            _run([ff, "-y", "-loglevel", "error", "-i", str(base), "-c", "copy", "-movflags", "+faststart", str(out)], "saving the video")
        else:
            cmd = [ff, "-y", "-loglevel", "error", "-i", str(base)]
            chains, vlast = [], "[0:v]"
            for k, t in enumerate(texts, 1):
                png = text_layer_png(t, W, H, td / f"t{k}.png")
                cmd += ["-loop", "1", "-framerate", str(FPS), "-t", str(total), "-i", str(png)]
                edge = min(0.25, (t["end"] - t["start"]) / 2)
                fade = f",fade=t=in:st={t['start']}:d={edge}:alpha=1,fade=t=out:st={_r3(t['end'] - edge)}:d={edge}:alpha=1" if t["fade"] and edge > 0 else ""
                chains.append(f"[{k}:v]format=rgba{fade}[t{k}]")
                move = ""
                d = _r3(min(MOTION_S, (t["end"] - t["start"]) / 2))
                if t["motion"] != "none" and d > 0:
                    rest = f"pow(1-min(1,max(0,(t-{t['start']})/{d})),3)"   # 1 at the start, 0 in place (ease out)
                    if t["motion"] == "slide":
                        move = f":x='-{MOVE_SLIDE}*W*{rest}'"
                    else:
                        move = f":y='{'' if t['motion'] == 'rise' else '-'}{MOVE_Y}*H*{rest}'"
                chains.append(f"{vlast}[t{k}]overlay=enable='between(t,{t['start']},{t['end']})'{move}:eof_action=pass[v{k}]")
                vlast = f"[v{k}]"
            n_in = 1 + len(texts)
            alast = "[0:a]"
            labels = []
            for j, (a, src) in enumerate(sounds, 1):
                cmd += ["-i", str(src)]
                length = _r3(min(a["out"] - a["in"], total - a["start"]))
                fade = min(a["fadeOut"], length)
                ms = round(a["start"] * 1000)
                f = f"[{n_in}:a]atrim=start={a['in']}:end={_r3(a['in'] + length)},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume={a['volume']}"
                if fade > 0:
                    f += f",afade=t=out:st={_r3(length - fade)}:d={fade}"
                chains.append(f"{f},adelay={ms}|{ms}[s{j}]")
                labels.append(f"[s{j}]")
                n_in += 1
            if labels:
                chains.append(f"{alast}{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first:dropout_transition=0[aout]")
                amap = "[aout]"
            else:
                amap = "0:a"
            vmap = vlast if texts else "0:v"
            cmd += ["-filter_complex", ";".join(chains)] if chains else []
            cmd += ["-map", vmap, "-map", amap, "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", str(total), "-movflags", "+faststart", str(out)]
            _run(cmd, "drawing the text and mixing the sound")
    srt = make_srt(P)
    if srt:
        out.with_suffix(".srt").write_text(srt, encoding="utf-8")
    return out


def cli(args: list[str]) -> int:
    if not args:
        print("Give the project file, for example: python dse.py presence edit-render my-video/my-video.edit.json [--draft]")
        return 2
    draft = "--draft" in args
    name = next((a for a in args if not a.startswith("--")), "")
    try:
        p = PM._resolve(name, PM.VIDEOS)
        out = render_edit(json.loads(p.read_text(encoding="utf-8")), draft=draft, extra=p.parent)
        more = f" and {out.with_suffix('.srt').name}" if out.with_suffix(".srt").exists() else ""
        print(f"Saved {out.name}{more} in my-video. Check it, then upload it yourself.")
        return 0
    except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e))
        return 1
