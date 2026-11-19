"""Presence: find the brand art you already have (logos, icons, profile pictures, brand pictures, fonts, brand colours and notes) and hand it to Presence > Brand kit.

    python dse.py presence brand [<engine>]

It looks, READ-ONLY, in the my-brand folder of this toolkit (put your logo files there) and, when you give an engine, in that engine's folders (the folders attached to it and its own folder) at files in a folder
called brand, branding, logo, logos, brand-kit, brand-assets or identity, and at pictures and fonts named like a logo, icon, avatar, profile, brand, favicon or wordmark. It uses the SAME safety rules as the engine
context folders: never _private-keys, the encrypted vault, .ssh, .aws, .env files, key, token or password files, archives or encrypted files; no linked folders; nothing is changed, moved or deleted.
What it keeps, small enough to go to Citadel:
  * SVG files as text (up to 100 KB; Citadel cleans them again before showing them),    * pictures shrunk to 640 px (a see-through picture stays a PNG), with their colours and whether they are see-through,
  * fonts: the family name read from inside the font file and, if the file is small, the file,    * brand colours and fonts named in brand notes, and lines about where the logo goes,    * the names of files it cannot read (PDF, AI, PSD ...).
It writes my-lists/<engine or own>-presence-brand.json. Presence > Brand kit reads it, adds what is new, updates what changed, and never changes what you set by hand. Needs Pillow (already used by the picture tools).
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os
import re
import struct
import sys
from pathlib import Path

from . import context_folder as cf
from .common import LISTS, ROOT
from .presence_context import BRAND_DIR, IMAGE_EXT, STYLE_NAME, inherited_folders, scrub, style_from

MY_BRAND = ROOT / "my-brand"
MAX_ASSETS = 24
MAX_FILES = 600
MAX_TOTAL = 900_000                    # characters of pictures, SVG and fonts in one result (the app keeps the same limit)
MAX_SVG = 100_000
MAX_RASTER = 260_000                   # characters in one picture's data URL
MAX_FONT = 220_000                     # characters in one font's data URL
MAX_SOURCE_BYTES = 20_000_000          # a picture file bigger than this is not opened
RASTER_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}
TEXT_EXT = {".md", ".markdown", ".txt", ".css"}
NAME_HINT = re.compile(r"(logo|icon|avatar|profile|brand|favicon|wordmark|monogram|symbol|emblem|headshot)", re.I)
FONT_DIR = re.compile(r"^(fonts?|typefaces?|typography)$", re.I)
NOTE_LINE = re.compile(r"\b(logo|clear ?space|safe zone|placement|minimum size)\b", re.I)
FAMILY_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,39}$")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
FONT_MIME = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}


# ------------------------------------------------------------------ reading one file

def dominant_colors(im, n: int = 4) -> list[str]:
    """The main colours of a picture: the colours that cover the most of it (see-through pixels left out); near-white and near-black only when nothing else is there."""
    small = im.convert("RGBA").resize((64, 64))
    buckets: dict[int, list[int]] = {}
    for r, g, b, a in small.getdata():
        if a < 200:
            continue
        e = buckets.setdefault(((r >> 5) << 6) | ((g >> 5) << 3) | (b >> 5), [0, 0, 0, 0])
        e[0] += 1
        e[1] += r
        e[2] += g
        e[3] += b
    rows = sorted(buckets.values(), key=lambda e: -e[0])

    def avg(e):
        return [e[1] / e[0], e[2] / e[0], e[3] / e[0]]

    real = [e for e in rows if not (min(avg(e)) > 240 or max(avg(e)) < 15)]
    return ["#%02X%02X%02X" % tuple(round(v) for v in avg(e)) for e in (real or rows)[:n]]


def raster_asset(path: Path, name: str) -> dict | None:
    """A picture as a small data URL, its size, whether it is see-through and its main colours. None when it cannot be opened or cannot be made small enough."""
    from PIL import Image
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            return None
        with Image.open(path) as im0:
            im0.load()
            im = im0.convert("RGBA")
    except Exception:
        return None
    w, h = im.size
    alpha = im.getchannel("A").getextrema()[0] < 245
    colors = dominant_colors(im)
    side = 640
    for attempt in range(7):
        t = im.copy()
        t.thumbnail((side, side))
        buf = io.BytesIO()
        if alpha:
            t.save(buf, "PNG", optimize=True)
            mime = "image/png"
        else:
            t.convert("RGB").save(buf, "JPEG", quality=88 if attempt < 3 else 60, optimize=True)
            mime = "image/jpeg"
        data = f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()
        if len(data) <= MAX_RASTER:
            return {"kind": "raster", "name": name, "w": w, "h": h, "alpha": alpha, "colors": colors, "data": data}
        side = int(side * 0.8)
    return None


def font_family(data: bytes) -> str | None:
    """The family name inside a TrueType or OpenType file (its 'name' table; the typographic family wins). None for anything else, such as compressed web fonts."""
    try:
        off = 0
        tag = struct.unpack_from(">I", data, 0)[0]
        if tag == 0x74746366:
            off = struct.unpack_from(">I", data, 12)[0]
        elif tag not in (0x00010000, 0x4F54544F, 0x74727565):
            return None
        n = struct.unpack_from(">H", data, off + 4)[0]
        for i in range(min(n, 64)):
            rec = off + 12 + i * 16
            if data[rec:rec + 4] != b"name":
                continue
            table = struct.unpack_from(">I", data, rec + 8)[0]
            count, sto = struct.unpack_from(">HH", data, table + 2)
            strings = table + sto
            best, rank = "", 0
            for j in range(min(count, 400)):
                platform, _enc, _lang, nid, length, o = struct.unpack_from(">HHHHHH", data, table + 6 + j * 12)
                if nid not in (1, 16) or strings + o + length > len(data):
                    continue
                raw = data[strings + o:strings + o + length]
                text = raw.decode("utf-16-be", "ignore") if platform in (0, 3) else raw.decode("latin-1", "ignore")
                rk = 2 if nid == 16 else 1
                if FAMILY_OK.match(text.strip()) and rk > rank:
                    best, rank = text.strip(), rk
            return best or None
    except (struct.error, IndexError):
        return None
    return None


def family_from_file(name: str) -> str:
    """A family name from a font's file name when the file cannot be read: 'Playfair-BoldItalic.ttf' gives 'Playfair'."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    stem = re.sub(r"[_-]+", " ", stem)
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    stem = re.sub(r"(regular|bold|italic|light|medium|semibold|extrabold|black|thin|oblique|variable|\d{3})", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem if FAMILY_OK.match(stem) else ""


def font_asset(path: Path, name: str) -> dict | None:
    ext = path.suffix.lower()
    try:
        raw = path.read_bytes() if path.stat().st_size <= 3_000_000 else path.read_bytes()[:600_000]
    except OSError:
        return None
    family = font_family(raw) or family_from_file(name)
    if not family:
        return None
    out = {"kind": "font", "name": name, "family": family, "mime": FONT_MIME[ext]}
    data = f"data:{FONT_MIME[ext]};base64," + base64.b64encode(raw).decode()
    if path.stat().st_size <= 3_000_000 and len(data) <= MAX_FONT:
        out["data"] = data
    return out


def svg_asset(path: Path, name: str) -> dict | None:
    try:
        if path.stat().st_size > MAX_SVG:
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not re.search(r"<svg[\s>]", text, re.I):
        return None
    return {"kind": "svg", "name": name, "svg": text, "w": 100, "h": 100, "alpha": True}


# ------------------------------------------------------------------ walking the folders

def candidates(root: Path, everything: bool):
    """(relative path, path) of files that may be brand art, read-only, with the engine context reader's safety rules. In `everything` mode (the my-brand folder) every picture, font and note counts."""
    root = root.resolve()
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in sorted(dirnames) if d.lower() not in cf.FORBIDDEN_DIRS and not d.startswith(".") and not (Path(dirpath) / d).is_symlink()
                       and depth + 1 <= cf.MAX_DEPTH and cf.inside(root, Path(dirpath) / d)]
        parts = Path(dirpath).relative_to(root).parts
        in_brand = everything or any(BRAND_DIR.match(p) for p in parts)
        in_fonts = any(FONT_DIR.match(p) for p in parts)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.is_symlink() or cf.SECRET_NAME.search(fn) or p.suffix.lower() in cf.ARCHIVE_EXT | cf.ENCRYPTED_EXT:
                continue
            seen += 1
            if seen > MAX_FILES:
                return
            ext = p.suffix.lower()
            rel = str(p.relative_to(root)).replace(os.sep, "/")
            if ext in RASTER_EXT or ext == ".svg":
                if in_brand or NAME_HINT.search(fn):
                    yield rel, p
            elif ext in FONT_EXT:
                if in_brand or in_fonts or NAME_HINT.search(fn):
                    yield rel, p
            elif ext in TEXT_EXT:
                if in_brand or STYLE_NAME.search(rel):
                    yield rel, p
            elif ext in IMAGE_EXT and in_brand:
                yield rel, p


def run_brand(engine: str = "", out=print, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    slug = engine or "own"
    try:
        MY_BRAND.mkdir(parents=True, exist_ok=True)
        folders = [(MY_BRAND, True)]
        if engine:
            folders += [(f, False) for f in inherited_folders(engine)]
    except SystemExit as e:
        out(str(e))
        return 1
    assets: list[dict] = []
    skipped: list[str] = []
    others: list[str] = []
    notes: list[str] = []
    style_items: list[tuple[str, str]] = []
    names: set[str] = set()
    total = 0
    scanned = 0
    for root, everything in folders:
        for rel, p in candidates(root, everything):
            scanned += 1
            ext = p.suffix.lower()
            label = f"{root.name}/{rel}"
            if ext in TEXT_EXT:
                try:
                    text = cf._read(p, 80_000)
                except OSError:
                    continue
                style_items.append((rel, text))
                for ln in text.splitlines():
                    c = re.sub(r"\s+", " ", scrub(ln)).strip(" -*#>|\t\"'")[:200]
                    if 12 <= len(c) and NOTE_LINE.search(c) and "[hidden]" not in c and "[line hidden]" not in c and c not in notes and len(notes) < 12:
                        notes.append(c)
                continue
            if ext in IMAGE_EXT and ext not in RASTER_EXT and ext != ".svg":
                if len(others) < 12:
                    others.append(label[:60])
                continue
            if len(assets) >= MAX_ASSETS:
                skipped.append(f"{label}: more than {MAX_ASSETS} files, the rest were left out")
                break
            key = p.name.lower()
            if key in names:
                skipped.append(f"{label}: another file has the same name")
                continue
            a = svg_asset(p, p.name) if ext == ".svg" else font_asset(p, p.name) if ext in FONT_EXT else raster_asset(p, p.name)
            if not a:
                skipped.append(f"{label}: could not be read or is too big to keep")
                continue
            size = len(a.get("svg", "")) + len(a.get("data", ""))
            if total + size > MAX_TOTAL:
                skipped.append(f"{label}: no room left in the brand kit")
                continue
            total += size
            names.add(key)
            a["path"] = label[:120]
            assets.append(a)
    style = style_from(style_items)
    if not assets and not style and not notes:
        out(f"I looked through {scanned} files and found no brand files. Put your logo, icons, profile picture and fonts in the my-brand folder of the toolkit ({MY_BRAND})"
            + (", or in a folder called brand or logo inside the engine's folder, " if engine else ", ") + "then run this again.")
        return 0
    result = {"v": 1, "kind": "presence-brand", "made": today.isoformat(), "engine": slug, "folders": [r.name for r, _ in folders], "scanned": scanned,
              "assets": assets, "style": style, "notes": notes, "others": others, "skipped": skipped[:12]}
    LISTS.mkdir(parents=True, exist_ok=True)
    p = LISTS / f"{slug}-presence-brand.json"
    p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    kinds = {k: sum(1 for a in assets if a["kind"] == k) for k in ("svg", "raster", "font")}
    out(f"Looked through {scanned} brand files in {len(folders)} folder(s). Found {kinds['svg']} SVG, {kinds['raster']} picture(s), {kinds['font']} font(s)"
        + (f", brand colours {', '.join(style['colors'][:4])}" if style else "") + f", {len(notes)} note(s). Saved {p.name} for Presence > Brand kit.")
    for s in skipped[:6]:
        out(f"  left out: {s}")
    return 0


def cli(args: list[str]) -> int:
    return run_brand(args[0] if args else "")


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
