"""Presence make tools: a picture for a post (Pillow) and a video from scenes (ffmpeg). The HQ half of Citadel's Presence > Studio.

  python dse.py presence graphic --layout quote --headline "..." [--body ...] [--kicker ...] [--footer @handle] [--size post] [--theme ink] [--picture my-pictures/x.jpg] [--logo my-pictures/logo.png]
  python dse.py presence video my-video/project.json
  python dse.py presence carousel my-carousel/project.json
  python dse.py presence voice-setup               one-time: installs the free Kokoro voice (about 330 MB, runs on this PC)

GRAPHIC. One finished PNG in my-graphics/: layouts quote, stat (a big number or phrase), tip, cover; sizes post (1080x1350), square, story (1080x1920), landscape (1920x1080), thumb (1280x720);
themes ink, cream, gold (the Citadel colours). Your own picture can sit behind the text (darkened so the words stay readable) and a logo can sit top left. Text is fitted to the box: it never runs off.
VIDEO. A project file (JSON, from the Studio's "video project" download or written by hand) lists scenes: each has on-screen text, optional picture, optional voiceover line and seconds. Each scene becomes
a card (your picture or a text card made by the graphic tool), moves slowly (a gentle zoom), and a voiceover is spoken with the Windows voice if voice is "windows", the free Kokoro voice (a natural-sounding AI voice that runs on this PC) if voice is "kokoro", or your own recordings are used if voice is "own" (my-audio/<title>-scene-<n>.wav or mp3, m4a, aac, ogg). The spoken words are burned onto the card as captions unless captions is false. CAROUSEL. A carousel project (from the Studio) becomes every slide as a PNG in one go. The scenes are joined into an MP4 with an
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
KOKORO_DIR = ROOT / "data" / "kokoro"
KOKORO_FILES = {  # file -> official release (kokoro-onnx, MIT; the Kokoro model is Apache 2.0)
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
}
KOKORO_VOICE = re.compile(r"^[a-z]{2}_[a-z]{2,12}$")
DEFAULT_KOKORO_VOICE = "af_sarah"

SIZES = {"post": (1080, 1350), "square": (1080, 1080), "story": (1080, 1920), "landscape": (1920, 1080), "thumb": (1280, 720)}
# Design kits: background, text, accent, muted, headline style, motif. The same table as the app's src/lib/presence-design.ts, so a picture made here looks like the slide drawn in Citadel.
KITS = {
    "ink": ("#1A1410", "#FBF6E9", "#C99A3B", "#B9AD91", "serif", "bar"),
    "cream": ("#FBF6E9", "#1A1410", "#7A5A00", "#6B5D3F", "serif", "bar"),
    "gold": ("#C99A3B", "#1A1410", "#4A3300", "#3D2E10", "sans", "corner"),
    "midnight": ("#0E1B2C", "#EEF3F8", "#5AB0FF", "#9FB2C8", "sans", "arc"),
    "sage": ("#E7EEE4", "#1D2B22", "#3F7D58", "#566B5C", "serif", "dots"),
    "blush": ("#FBE9E6", "#3A1F22", "#C0485A", "#7B5459", "serif", "arc"),
    "terracotta": ("#A94A2A", "#FFF3EA", "#FFD9B0", "#F2C9AE", "display", "corner"),
    "mono": ("#FFFFFF", "#111111", "#111111", "#555555", "display", "none"),
}
THEMES = tuple(KITS)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
HEADS = ("serif", "sans", "display")
MOTIFS = ("bar", "arc", "corner", "dots", "none")
LAYOUTS = ("quote", "stat", "tip", "cover", "question", "myth")


def _lum(hexv: str) -> float:
    def c(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _readable(bg: str, want: str, floor: float = 4.5) -> str:
    if HEX.match(want) and _contrast(bg, want) >= floor:
        return want.upper()
    return "#111111" if _contrast(bg, "#111111") >= _contrast(bg, "#FFFFFF") else "#FFFFFF"


def parse_kit(raw: object = None, theme: str = "ink") -> dict:
    """A design kit as a plain dict: the student's own kit (colours that must be real hex values, words made readable) or a built-in one by name."""
    base = KITS.get(theme if theme in KITS else "ink")
    d = dict(zip(("bg", "fg", "accent", "muted", "head", "motif"), base))
    if isinstance(raw, dict) and all(HEX.match(str(raw.get(k, ""))) for k in ("bg", "fg", "accent")):
        bg = str(raw["bg"]).upper()
        d.update(bg=bg, fg=_readable(bg, str(raw["fg"])), accent=_readable(bg, str(raw["accent"]), 3.0),
                 muted=str(raw["muted"]).upper() if HEX.match(str(raw.get("muted", ""))) and _contrast(bg, str(raw["muted"])) >= 3.0 else _readable(bg, str(raw["fg"]), 3.0),
                 head=raw.get("head") if raw.get("head") in HEADS else "sans", motif=raw.get("motif") if raw.get("motif") in MOTIFS else "bar")
    return d


STAT = re.compile(r"^(\d{1,3}(?:[,.]\d{3})*(?:\.\d+)?\s*(?:of|out of|in)\s*\d{1,3}(?:[,.]\d{3})*|\d{1,3}(?:[,.]\d{3})*(?:\.\d+)?\s?(?:%|x|k|m|bn|billion|million)?)(?=\s|[,.:;]|$)\s*(.*)$", re.I | re.S)
STAT_ANY = re.compile(r"(\d{1,3}(?:[,.]\d{3})*(?:\.\d+)?\s?%|\$\s?\d[\d,.]*\s?(?:billion|million|bn|m|k)?)", re.I)


def stat_of(text: str):
    """(big figure, the words after it) for a text that leads with a number or has a percentage or an amount in it, else None. Mirrors statOf in the app."""
    t = re.sub(r"^In the news \([^)]*\):\s*", "", str(text or "").strip(), flags=re.I)
    m = STAT.match(t)
    if m and re.fullmatch(r"\d{1,3}", m.group(1).strip()):
        m = None                                  # a bare small number is a list count ("5 mistakes"), not a finding
    if m:
        return m.group(1).strip()[:14], m.group(2).strip()
    m = STAT_ANY.search(t)
    return (re.sub(r"\s+", " ", m.group(1)).strip()[:14], re.sub(r"^[\s,:;-]+", "", t.replace(m.group(1), "")).strip()) if m else None


def auto_layout(title: str, body: str = "", fallback: str = "cover") -> str:
    """The layout a text asks for: a figure gets the big-number layout, a question the question layout, a myth the two-part layout, a quote the quote layout."""
    t, b = str(title or "").strip(), str(body or "").strip()
    if re.match(r"^myth\b", t, re.I) or re.match(r"^myth:", b, re.I):          # the same order as the app's layoutFor: myth, question, figure, quote
        return "myth"
    if t.endswith("?") and len(b) < 160:
        return "question"
    first = b.split("\n")[0]
    if (stat_of(t) and len(t) < 160) or (first and stat_of(first)) or (re.match(r"^finding\b", t, re.I) and stat_of(b)):
        return "stat"
    if t[:1] in ('"', "\u201c"):
        return "quote"
    return fallback


FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def _font(bold: bool, size: int, head: str = ""):
    """A font from this PC: the headline styles are serif (Georgia), sans (Segoe UI) and display (Arial Black); body text is always sans."""
    from PIL import ImageFont
    if head == "serif":
        names = ["georgiab.ttf", "georgia.ttf", "arialbd.ttf"]
    elif head == "display":
        names = ["ariblk.ttf", "arialbd.ttf", "segoeuib.ttf"]
    elif head == "sans":
        names = ["segoeuib.ttf", "arialbd.ttf"]
    else:
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


def _fit(draw, text: str, bold: bool, width: int, height: int, start: int, floor: int = 22, head: str = ""):
    """Biggest font size (from start down to floor) whose wrapped text fits the box. Returns (font, lines, line_height)."""
    size = start
    while True:
        f = _font(bold, size, head)
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


def _motif(img, k: dict, W: int, H: int, pad: int):
    """A quiet shape that gives the page a signature (a bar, arcs, a corner, dots) without taking attention from the words."""
    from PIL import Image, ImageDraw
    if k["motif"] in ("none", "bar"):
        return img
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r, g, b = (int(k["accent"][i:i + 2], 16) for i in (1, 3, 5))
    if k["motif"] == "arc":
        for i in range(3):
            rad = int(W * 0.21) + i * int(W * 0.065)
            d.arc((W - rad, -rad, W + rad, rad), 0, 180, fill=(r, g, b, 90), width=max(8, int(W * 0.013)))
    elif k["motif"] == "corner":
        d.polygon([(W, 0), (W - int(W * 0.33), 0), (W, int(W * 0.33))], fill=(r, g, b, 80))
    elif k["motif"] == "dots":
        for row in range(5):
            for col in range(5):
                cx, cy = W - pad - col * int(W * 0.04), pad + row * int(W * 0.04)
                d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=(r, g, b, 90))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def make_graphic(layout: str = "quote", headline: str = "", body: str = "", kicker: str = "", footer: str = "", size: str = "post", theme: str = "ink",
                 picture: str = "", logo: str = "", out_path: str | Path | None = None, kit: dict | None = None) -> Path:
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
    k = parse_kit(kit, theme)
    img = Image.new("RGB", (W, H), k["bg"])
    if picture:
        pp = _resolve(picture, PICS)
        photo = _cover(Image.open(pp).convert("RGB"), W, H)
        shade = Image.new("RGB", (W, H), "#0f1115")
        img = Image.blend(photo, shade, 0.62)
        k = {**k, "fg": "#F6F0E4", "muted": "#D9CFB5", "accent": k["accent"] if _contrast("#2A2D33", k["accent"]) >= 3.0 else "#F2C879"}
    pad = int(W * 0.09)
    inner = W - 2 * pad
    img = _motif(img, k, W, H, pad)
    d = ImageDraw.Draw(img)
    top = pad
    if logo:
        lg = Image.open(_resolve(logo, PICS)).convert("RGBA")
        hgt = max(60, int(H * 0.06))
        lg = lg.resize((max(1, int(lg.width * hgt / lg.height)), hgt), Image.LANCZOS)
        img.paste(lg, (pad, pad), lg)
        top = pad + hgt + int(H * 0.02)
    hd, fg, accent, muted = k["head"], k["fg"], k["accent"], k["muted"]
    if k["motif"] == "bar":
        d.rectangle((pad, top, pad + int(W * 0.12), top + 8), fill=accent)
    y = top + 40
    footer_y = H - pad - int(W * 0.03)
    kk = kicker.strip().upper()[:40]
    if kk and layout not in ("question", "myth"):
        d.text((pad, y), kk, font=_font(True, max(26, int(W * 0.03)), "sans"), fill=accent)
        y += int(W * 0.03) + 36
    area_bottom = footer_y - (int(H * 0.04) if footer.strip() else 0)
    text = headline.strip()
    if layout == "stat":
        st = stat_of(text)
        from_body = False
        if not st and body.strip():
            st, from_body = stat_of(body.strip().split("\n")[0]), True        # the figure may be the first line of the body, with a label such as "Finding 1" as the headline
        big, rest = (st if st else (text[:14], ""))
        if from_body:
            rest = rest or text
        size = int(W * 0.30)                                                  # the figure is one line: it shrinks until it fits the width, so a long number never runs off the picture
        while size > 40 and d.textlength(big, font=_font(True, size, hd)) > inner:
            size -= 6
        bf = _font(True, size, hd)
        blh = int(size * 1.15)
        by = y + int(H * 0.06)
        d.text((pad, by), big, font=bf, fill=accent)
        by += blh + 20
        d.rectangle((pad, by, pad + int(W * 0.15), by + 8), fill=accent)
        words = rest or ("" if from_body else body.strip())
        if words:
            wf, wl, wlh = _fit(d, words, True, inner, area_bottom - by - int(H * 0.12), int(W * 0.062), 28, "sans")
            for i, line in enumerate(wl):
                d.text((pad, by + 40 + i * wlh), line, font=wf, fill=fg)
        m_src = re.search(r"^Source:\s*(.+)$", body, re.I | re.M)
        src = m_src.group(1).strip() if m_src else ""
        if src:
            sf = _font(False, max(24, int(W * 0.03)))
            sl = _wrap(d, "Source: " + src, sf, inner)[:2]
            for i, line in enumerate(sl):
                d.text((pad, area_bottom - int(W * 0.04) * (len(sl) - i)), line, font=sf, fill=muted)
    elif layout == "question":
        qf = _font(True, int(W * 0.95), "serif")
        qb = d.textbbox((0, 0), "?", font=qf)
        r, g, b = (int(accent[i:i + 2], 16) for i in (1, 3, 5))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(layer).text((W - (qb[2] - qb[0]) - 30, -qb[1] + 40), "?", font=qf, fill=(r, g, b, 46))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"); d = ImageDraw.Draw(img)
        hf, hl, hlh = _fit(d, text, True, inner, int(H * 0.5), int(W * 0.10), 40, hd)
        hy = max(y + 40, (H - len(hl) * hlh) // 2 - 40)
        for i, line in enumerate(hl):
            d.text((pad, hy + i * hlh), line, font=hf, fill=fg)
        qsf = _font(True, int(W * 0.043), "sans")
        for i, line in enumerate(_wrap(d, (body.strip() or "Tell me below.")[:160], qsf, inner)[:3]):
            d.text((pad, hy + len(hl) * hlh + 40 + i * int(W * 0.055)), line, font=qsf, fill=accent)
    elif layout == "quote":
        d.text((pad - 10, y - 20), "\u201c", font=_font(True, int(W * 0.32), "serif"), fill=accent)
        qtext = text.strip('"\u201c\u201d')
        hf, hl, hlh = _fit(d, qtext, True, inner, int(H * 0.42), int(W * 0.078), 36, "serif")
        hy = max(y + int(H * 0.16), (H - len(hl) * hlh) // 2 + 30)
        for i, line in enumerate(hl):
            d.text((pad, hy + i * hlh), line, font=hf, fill=fg)
        ly = hy + len(hl) * hlh + 30
        d.rectangle((pad, ly, pad + int(W * 0.08), ly + 6), fill=accent)
        if body.strip():
            qbf = _font(True, int(W * 0.037), "sans")
            for i, line in enumerate(_wrap(d, body.strip()[:120], qbf, inner)[:2]):
                d.text((pad, ly + 30 + i * int(W * 0.048)), line, font=qbf, fill=muted)
    elif layout == "myth":
        mt = re.sub(r"^myth:\s*", "", text, flags=re.I)
        d.text((pad, y + 10), "MYTH", font=_font(True, int(W * 0.037), "sans"), fill=muted)
        mf, ml, mlh = _fit(d, mt, True, inner, int(H * 0.22), int(W * 0.07), 34, hd)
        my = y + 80
        for i, line in enumerate(ml):
            d.text((pad, my + i * mlh), line, font=mf, fill=muted)
        d.line((pad, my + mlh // 2, pad + int(d.textlength(ml[0], font=mf)), my + mlh // 2), fill=accent, width=6)
        fy = max(my + len(ml) * mlh + 90, int(H * 0.53))
        d.rectangle((pad, fy - 50, pad + inner, fy - 46), fill=accent)
        d.text((pad, fy), "FACT", font=_font(True, int(W * 0.037), "sans"), fill=accent)
        ft = re.sub(r"^fact:\s*", "", body.strip(), flags=re.I) or "..."
        ff, fl, flh = _fit(d, ft, True, inner, area_bottom - fy - 90, int(W * 0.08), 36, hd)
        for i, line in enumerate(fl):
            d.text((pad, fy + 70 + i * flh), line, font=ff, fill=fg)
    else:
        foot_h = int(H * 0.08) if footer.strip() else 0
        avail = H - y - pad - foot_h
        body_h = int(avail * 0.30) if body.strip() else 0
        head_h = avail - body_h - (30 if body.strip() else 0)
        start = {"cover": int(W * 0.12), "tip": int(W * 0.085)}.get(layout, int(W * 0.09))
        hf, hl, hlh = _fit(d, text, True, inner, head_h, start, 22, hd)
        for i, line in enumerate(hl):
            d.text((pad, y + i * hlh), line, font=hf, fill=fg)
        if body.strip():
            bf, bl, blh = _fit(d, body.strip(), False, inner, body_h, int(W * 0.045))
            by = y + head_h + 30
            for i, line in enumerate(bl):
                d.text((pad, by + i * blh), line, font=bf, fill=fg)
    if footer.strip():
        d.text((pad, footer_y), footer.strip()[:60], font=_font(True, max(24, int(W * 0.028)), "sans"), fill=accent if layout != "stat" else muted)
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


def _caption_overlay(text: str, W: int, H: int, out: Path) -> None:
    """The caption band on a see-through picture the size of the video (for scenes drawn by Blender, where the card is not a single picture)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    pad = int(W * 0.06)
    f, lines, lh = _fit(d, text, True, W - 2 * pad, int(H * 0.2), int(W * 0.05), 26)
    top = H - int(H * 0.08) - len(lines) * lh - 24
    d.rectangle((0, top - 24, W, H), fill=(15, 17, 21, 190))
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        d.text(((W - tw) / 2, top + i * lh), line, font=f, fill="#f6f0e4")
    img.save(out, "PNG")


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
        if not text and not voice and not s.get("image"):
            continue
        try:
            sec = float(s.get("seconds") or 0)
        except (TypeError, ValueError):
            sec = 0
        sec = max(1.0, min(30.0, sec or max(3.0, len(voice.split()) / 2.5)))
        scenes.append({"text": text, "voice": voice, "image": str(s.get("image") or ""), "seconds": sec})
    if not scenes:
        raise ValueError("Every scene is empty.")
    return {"title": str(raw.get("title") or "video")[:80], "size": size, "theme": raw.get("theme") if raw.get("theme") in THEMES else "ink", "kit": raw.get("kit") if isinstance(raw.get("kit"), dict) else None,
            "engine": "blender" if raw.get("engine") == "blender" else "cards", "quality": "high" if raw.get("quality") == "high" else "draft", "arrive": "fly" if raw.get("arrive") == "fly" else "rise", "move": raw.get("move") if raw.get("move") in ("dolly", "drift", "still") else "dolly",
            "voice": raw.get("voice") if raw.get("voice") in ("windows", "own", "kokoro") else "none", "kokoro_voice": raw.get("kokoro_voice") if KOKORO_VOICE.match(str(raw.get("kokoro_voice") or "")) else DEFAULT_KOKORO_VOICE, "captions": raw.get("captions") is not False, "footer": str(raw.get("footer") or "")[:60], "scenes": scenes}


_KOKORO = None


def kokoro_ready() -> tuple[bool, str]:
    """Is the free Kokoro voice usable on this PC? (the kokoro-onnx package, soundfile and the two model files). Returns (ready, plain words about what is missing)."""
    try:
        import kokoro_onnx, soundfile  # noqa: F401
    except ImportError:
        return False, "the Kokoro voice is not installed yet: run the HQ tool 'Presence: install the free Kokoro voice' once"
    missing = [f for f in KOKORO_FILES if not (KOKORO_DIR / f).exists()]
    if missing:
        return False, f"the Kokoro voice files are missing ({', '.join(missing)}): run the HQ tool 'Presence: install the free Kokoro voice'"
    return True, ""


def _speak_kokoro(text: str, wav: Path, voice: str = DEFAULT_KOKORO_VOICE) -> float | None:
    """The free Kokoro voice (runs on this PC, no account, no internet needed after install) to a WAV. Returns its length in seconds, or None when it cannot."""
    global _KOKORO
    ok, _ = kokoro_ready()
    if not ok or not KOKORO_VOICE.match(voice or ""):
        return None
    try:
        import soundfile
        if _KOKORO is None:
            from kokoro_onnx import Kokoro
            _KOKORO = Kokoro(str(KOKORO_DIR / "kokoro-v1.0.onnx"), str(KOKORO_DIR / "voices-v1.0.bin"))
        samples, rate = _KOKORO.create(text, voice=voice, speed=1.0, lang="en-us")
        soundfile.write(str(wav), samples, rate)
        return len(samples) / float(rate)
    except Exception:
        return None


def install_kokoro(say=print) -> int:
    """One-time setup: installs the packages and downloads the two model files (about 330 MB) from the project's official release page. Safe to run again."""
    import requests
    if not kokoro_ready()[0]:
        try:
            import kokoro_onnx, soundfile  # noqa: F401
        except ImportError:
            say("Installing the Kokoro packages (kokoro-onnx, soundfile)...")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "kokoro-onnx", "soundfile"], capture_output=True, text=True)
            if r.returncode != 0:
                say("The install did not work: " + r.stderr.strip()[-300:])
                return 1
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in KOKORO_FILES.items():
        dest = KOKORO_DIR / name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            say(f"{name}: already there.")
            continue
        say(f"Downloading {name} (this is the big one, a few minutes)...")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(1 << 20):
                        fh.write(chunk)
            if tmp.stat().st_size < 1_000_000:
                tmp.unlink(missing_ok=True)
                say(f"{name}: the download was too small to be right. Try again later.")
                return 1
            tmp.replace(dest)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            say(f"{name}: could not download ({e}).")
            return 1
    ok, why = kokoro_ready()
    say("The Kokoro voice is ready. Choose 'Kokoro' as the voice in the Studio video project." if ok else f"Not ready yet: {why}")
    return 0 if ok else 1


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
        any_3d = False
        for i, s in enumerate(P["scenes"], 1):
            card = td / f"card{i}.png"
            if s["image"]:
                from PIL import Image
                _cover(Image.open(_resolve(s["image"], GRAPHICS if (GRAPHICS / Path(s["image"]).name).exists() else PICS)).convert("RGB"), W, H).save(card)
            else:
                make_graphic(auto_layout(s["text"] or P["title"], "", "cover"), s["text"] or P["title"], "", "", P["footer"], P["size"], P["theme"], out_path=card, kit=P["kit"])
            wav = td / f"v{i}.wav"
            own = _own_audio(P["title"], i) if P["voice"] == "own" else None
            if P["voice"] == "own" and own is None:
                say(f"Scene {i}: no recording found (my-audio/{slug(P['title'])}-scene-{i}.wav), so it is silent.")
            if own is not None:
                wav = own
                length = _duration(ff, own)
                if length:
                    s["seconds"] = max(s["seconds"], round(min(length, 30) + 0.3, 2))
            elif P["voice"] == "kokoro" and s["voice"]:
                length = _speak_kokoro(s["voice"], wav, P["kokoro_voice"])
                if not length:
                    say(f"Scene {i}: {kokoro_ready()[1] or 'the Kokoro voice could not speak this'}. Using the Windows voice for this scene.")
                    length = _speak(s["voice"], wav)
                if length:
                    s["seconds"] = max(s["seconds"], round(length + 0.4, 2))
            elif P["voice"] == "windows" and s["voice"]:
                length = _speak(s["voice"], wav)
                if length:
                    s["seconds"] = max(s["seconds"], round(length + 0.4, 2))
                else:
                    say("The Windows voice did not work for this scene: it will be silent.")
            bl_clip = None
            if P["engine"] == "blender" and not s["image"]:
                try:
                    from . import presence_blender as B
                    kit = parse_kit(P["kit"], P["theme"])
                    q = (W, H) if P["quality"] == "high" else (W // 2 - (W // 2) % 2, H // 2 - (H // 2) % 2)
                    fps_in = B.FPS if P["quality"] == "high" else 12
                    st = stat_of(s["text"] or "") if auto_layout(s["text"] or "", "", "cover") == "stat" else None
                    if not any_3d:
                        say(f"Blender draws every scene in 3D: about {max(20, int(min(120, int(s['seconds'] * (B.FPS if P['quality'] == 'high' else 12))) * (6 if P['quality'] == 'high' else 0.8)))} seconds a scene on a typical PC. Please wait.")
                        any_3d = True
                    spec = B.scene_spec(s["text"] or P["title"], kit, q, min(120, int(s["seconds"] * fps_in)), P["move"], B.SAMPLES[P["quality"]], st, fps_in, P["arrive"])
                    frames = B.render_scene(spec, td / f"bl{i}")
                    bl_clip = B.frames_to_clip(ff, frames, s["seconds"], (W, H), td / f"bl{i}.mp4", fps_in)
                    say(f"Scene {i}: drawn in 3D with Blender ({len(frames)} frames).")
                except Exception as e:                                          # Blender missing or a scene failed: this scene uses the normal card, and the video carries on
                    say(f"Scene {i}: Blender was not used ({e}). Using the normal card for this scene.")
                    bl_clip = None
            if P["captions"] and s["voice"] and not bl_clip:
                _burn_caption(card, s["voice"], W, H)
            clip = td / f"clip{i}.mp4"
            frames = int(s["seconds"] * 30)
            zoom = f"zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30"
            if bl_clip:
                cmd = [ff, "-y", "-loglevel", "error", "-i", str(bl_clip)]
                cap = None
                if P["captions"] and s["voice"]:
                    cap = td / f"cap{i}.png"
                    _caption_overlay(s["voice"], W, H, cap)
                    cmd += ["-i", str(cap)]
                if wav.exists():
                    cmd += ["-i", str(wav)]
                else:
                    cmd += ["-f", "lavfi", "-t", str(s["seconds"]), "-i", "anullsrc=r=44100:cl=mono"]
                a_in = 2 if cap else 1
                vf = ["-filter_complex", f"[0:v][1:v]overlay=0:0,format=yuv420p[v]", "-map", "[v]", "-map", f"{a_in}:a"] if cap else ["-map", "0:v", "-map", f"{a_in}:a", "-pix_fmt", "yuv420p"]
                cmd += vf + ["-c:v", "libx264", "-preset", "veryfast", "-af", "apad", "-c:a", "aac", "-ar", "44100", "-ac", "1", "-t", str(s["seconds"]), str(clip)]
            else:
                cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-t", str(s["seconds"]), "-i", str(card)]
                if wav.exists():
                    cmd += ["-i", str(wav)]
                else:
                    cmd += ["-f", "lavfi", "-t", str(s["seconds"]), "-i", "anullsrc=r=44100:cl=mono"]
                cmd += ["-vf", f"scale={W * 2}:{H * 2},{zoom},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-af", "apad", "-c:a", "aac", "-ar", "44100", "-ac", "1", "-t", str(s["seconds"]), str(clip)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"ffmpeg stopped on scene {i}: {r.stderr.strip()[-300:]}")
            clips.append(clip)
            say(f"Scene {i} of {len(P['scenes'])}: {s['seconds']:.1f}s")
        lst = td / "list.txt"
        lst.write_text("".join("file '" + c.as_posix().replace("'", "'\\''") + "'\n" for c in clips), encoding="utf-8")
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
    return {"title": str(raw.get("title") or "carousel")[:80], "size": raw.get("size") if raw.get("size") in SIZES else "post", "theme": raw.get("theme") if raw.get("theme") in THEMES else "ink", "kit": raw.get("kit") if isinstance(raw.get("kit"), dict) else None,
            "footer": str(raw.get("footer") or "")[:60], "picture": str(raw.get("picture") or "")[:200], "logo": str(raw.get("logo") or "")[:200], "slides": slides}


def make_carousel(project: dict, out_dir: str | Path | None = None, say=print) -> list[Path]:
    """Every slide of a carousel as a finished PNG in my-graphics (cover, points, last slide with your name), in one go."""
    P = parse_carousel(project)
    out = Path(out_dir) if out_dir else GRAPHICS
    out.mkdir(parents=True, exist_ok=True)
    base, n, files = slug(P["title"])[:30] or "carousel", len(P["slides"]), []
    for i, sl in enumerate(P["slides"], 1):
        layout = auto_layout(sl["title"], sl["body"], "cover" if i == 1 else "tip")
        kicker = f"{i} / {n}"
        files.append(make_graphic(layout, sl["title"], sl["body"], kicker, P["footer"] if i == n else "", P["size"], P["theme"], P["picture"], P["logo"], out_path=out / f"{base}-{i:02}.png", kit=P["kit"]))
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
        if kind == "voice-setup":
            return install_kokoro()
        if kind in ("blender-setup", "blender-check"):
            from . import presence_blender as B
            if kind == "blender-check":
                return B.check()
            return B.install_blender(rest[rest.index("--to") + 1] if "--to" in rest and rest.index("--to") + 1 < len(rest) else None)
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
