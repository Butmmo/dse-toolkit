"""Tests for Presence > Brand kit on the PC: finding brand art in the my-brand folder and an engine's folders (dse/presence_brand.py) and drawing the brand on a carousel (dse/presence_make.py).   python tests/test_presence_brand.py"""
import base64
import io
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image  # noqa: E402

from dse import engines as E  # noqa: E402
from dse import presence_brand as B  # noqa: E402
from dse import presence_context as C  # noqa: E402
from dse import presence_make as M  # noqa: E402

fails = 0


def ok(name, cond):
    global fails
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        fails += 1


td = Path(tempfile.mkdtemp())
E.ENGINES = td / "engines"
C.engine_dir = E.engine_dir
B.engine_dir = E.engine_dir
B.LISTS = td / "lists"
B.MY_BRAND = td / "my-brand"
out_dir = td / "out"


def png_bytes(size, color, alpha=True, shape="full"):
    im = Image.new("RGBA", size, color + ((255,) if len(color) == 3 else ()))
    if alpha and shape == "ring":
        for x in range(size[0]):
            for y in range(size[1]):
                if (x - size[0] / 2) ** 2 + (y - size[1] / 2) ** 2 > (size[1] / 2) ** 2:
                    im.putpixel((x, y), (0, 0, 0, 0))
    buf = io.BytesIO()
    (im if alpha else im.convert("RGB")).save(buf, "PNG")
    return buf.getvalue()


def fake_font(family, extra_plain=None):
    def u16(n): return struct.pack(">H", n)
    names = [(1, extra_plain)] if extra_plain else []
    names.append((16 if extra_plain else 1, family))
    strs = [n[1].encode("utf-16-be") for n in names]
    off, recs = 0, b""
    for (nid, _), sb in zip(names, strs):
        recs += u16(3) + u16(1) + u16(0x409) + u16(nid) + u16(len(sb)) + u16(off)
        off += len(sb)
    table = u16(0) + u16(len(names)) + u16(6 + 12 * len(names)) + recs + b"".join(strs)
    return struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0) + b"name" + struct.pack(">III", 0, 28, len(table)) + table


# ---- a work folder
brand = B.MY_BRAND
brand.mkdir(parents=True)
(brand / "acme-logo.png").write_bytes(png_bytes((600, 200), (26, 77, 58), shape="ring"))
(brand / "acme-logo-white.png").write_bytes(png_bytes((600, 200), (255, 255, 255), shape="ring"))
(brand / "profile-ada.jpg").write_bytes(png_bytes((800, 800), (153, 102, 51), alpha=False))
(brand / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#1A4D3A"/></svg>', encoding="utf-8")
(brand / "evil.svg").write_text("<html><body>not an svg</body></html>", encoding="utf-8")
(brand / "Brand.ttf").write_bytes(fake_font("Brand Sans", extra_plain="Brand Sans Bold"))
(brand / "Serif-Bold.woff2").write_bytes(b"wOF2 not readable")
(brand / "guide.pdf").write_bytes(b"%PDF-1.4")
(brand / "brand-notes.md").write_text("# Brand notes\n\nPrimary colour: #1A4D3A\nAccent colour: #E8B84A\nFont: Montserrat\n\nPlace the logo in the top right of every post.\nThe logo needs clear space of 20 px.\nThe admin password is Hunter2 and the logo token abc.\n", encoding="utf-8")
(brand / ".env").write_text("KEY=hunter2", encoding="utf-8")
(brand / "api-token-logo.png").write_bytes(png_bytes((10, 10), (1, 2, 3)))
(brand / "archive.zip").write_bytes(b"PK")
(brand / "_private-keys").mkdir()
(brand / "_private-keys" / "logo.png").write_bytes(png_bytes((10, 10), (9, 9, 9)))
huge = brand / "huge-logo.png"
Image.effect_noise((2500, 2500), 80).convert("RGB").save(huge, "PNG")


def noisy(path, side=900):
    """A see-through picture full of noise: far too big to keep as it is (a PNG of several hundred KB even when small)."""
    im = Image.effect_noise((side, side), 90).convert("RGBA")
    im.putpixel((0, 0), (0, 0, 0, 0))
    im.save(path, "PNG")


noisy(brand / "noisy-logo.png")

eng = E.ENGINES / "acme"
eng.mkdir(parents=True)
work = td / "work" / "old-assets"
(work / "branding").mkdir(parents=True)
(work / "branding" / "acme-icon.png").write_bytes(png_bytes((256, 256), (242, 184, 75), shape="ring"))
(work / "random").mkdir()
(work / "random" / "holiday.png").write_bytes(png_bytes((50, 50), (5, 5, 5)))
(work / "random" / "company-logo-old.png").write_bytes(png_bytes((300, 100), (200, 0, 0)))
(eng / "engine.json").write_text(json.dumps({"context_folders": [{"path": str(work)}], "title": "Acme"}), encoding="utf-8")

out = []
code = B.run_brand("", out.append)
j = json.loads((B.LISTS / "own-presence-brand.json").read_text(encoding="utf-8"))
byname = {a["name"]: a for a in j["assets"]}
ok("it writes my-lists/own-presence-brand.json with the kind, version and engine 'own' when no engine is given", code == 0 and j["kind"] == "presence-brand" and j["v"] == 1 and j["engine"] == "own")
ok("pictures are found and kept small: size, see-through and main colours are right", {"acme-logo.png", "acme-logo-white.png", "profile-ada.jpg"} <= set(byname) and byname["acme-logo.png"]["alpha"] is True and byname["acme-logo.png"]["w"] == 600 and byname["acme-logo.png"]["colors"][0] == "#1A4D3A" and byname["profile-ada.jpg"]["alpha"] is False and byname["profile-ada.jpg"]["data"].startswith("data:image/jpeg;base64,") and byname["acme-logo.png"]["data"].startswith("data:image/png;base64,") and byname["acme-logo-white.png"]["colors"] == ["#FFFFFF"])
ok("an oversized picture is shrunk to the keeping limit or left out with a reason, never sent whole", "noisy-logo.png" in byname and 0 < len(byname["noisy-logo.png"]["data"]) <= B.MAX_RASTER and byname["noisy-logo.png"]["w"] == 900 and all(len(a.get("data", "")) <= B.MAX_RASTER for a in j["assets"] if a["kind"] == "raster"))
ok("an SVG is kept as text, and a file called .svg that is not an SVG is refused with a reason", byname["mark.svg"]["svg"].startswith("<svg") and "evil.svg" not in byname and any("evil.svg" in s for s in j["skipped"]))
ok("a font gives its family name read from inside the file (the typographic family wins), and its file when small", byname["Brand.ttf"]["kind"] == "font" and byname["Brand.ttf"]["family"] == "Brand Sans" and byname["Brand.ttf"]["data"].startswith("data:font/ttf;base64,"))
ok("a web font that cannot be read gets its name from the file name, without Bold", byname["Serif-Bold.woff2"]["family"] == "Serif")
ok("brand colours and fonts come from brand notes, and lines about the logo are kept as notes", j["style"] and j["style"]["colors"][:2] == ["#1A4D3A", "#E8B84A"] and "Montserrat" in j["style"]["fonts"] and any("top right" in n for n in j["notes"]) and any("clear space" in n for n in j["notes"]))
ok("a note line that talks about a password or token is never kept", not any("Hunter2" in n or "password" in n.lower() or "token" in n.lower() or "hidden" in n for n in j["notes"]))
ok("nothing secret is read: no .env, no token-named file, no archive, no key folder", not any(x in " ".join(a["name"] + a.get("path", "") for a in j["assets"]) for x in (".env", "api-token", "archive", "_private-keys")) and "hunter2" not in json.dumps(j).lower())
ok("files it cannot read as pictures are listed by name only", any("guide.pdf" in o for o in j["others"]))
ok("nothing in the folder was changed, moved or deleted", sorted(p.name for p in brand.iterdir()) == sorted([".env", "Brand.ttf", "Serif-Bold.woff2", "_private-keys", "acme-logo-white.png", "acme-logo.png", "api-token-logo.png", "archive.zip", "brand-notes.md", "evil.svg", "guide.pdf", "huge-logo.png", "mark.svg", "noisy-logo.png", "profile-ada.jpg"]) and "hunter2" in (brand / ".env").read_text())
ok("the total stays under the limit the app keeps", sum(len(a.get("svg", "")) + len(a.get("data", "")) for a in j["assets"]) <= B.MAX_TOTAL and len(j["assets"]) <= B.MAX_ASSETS)

# a link in the folder is never followed, and too many or too heavy files are cut with a reason
many = td / "many-brand"
many.mkdir()
for i in range(30):
    Image.new("RGBA", (40 + i, 40), (i * 8, 10, 10, 255)).save(many / f"logo-{i:02}.png")
outside = td / "outside-logo.png"
outside.write_bytes(png_bytes((20, 20), (1, 2, 3)))
linked = False
try:
    (many / "linked-logo.png").symlink_to(outside)
    linked = True
except (OSError, NotImplementedError):
    pass
B.MY_BRAND = many
B.run_brand("", [].append)
jm = json.loads((B.LISTS / "own-presence-brand.json").read_text(encoding="utf-8"))
ok("at most 24 files are kept and the rest are named as left out", len(jm["assets"]) == B.MAX_ASSETS and any("more than 24" in x for x in jm["skipped"]))
ok("a link to a file elsewhere is never followed (when the system allows links)", not linked or not any(a["name"] == "linked-logo.png" for a in jm["assets"]))
heavy = td / "heavy-brand"
heavy.mkdir()
for i in range(6):
    noisy(heavy / f"noise-{i}-logo.png", 700 + i * 8)
B.MY_BRAND = heavy
B.run_brand("", [].append)
jh = json.loads((B.LISTS / "own-presence-brand.json").read_text(encoding="utf-8"))
ok("the total size stays under the limit: files that do not fit are left out with a reason", sum(len(a.get("data", "")) for a in jh["assets"]) <= B.MAX_TOTAL and len(jh["assets"]) < 6 and any("no room" in x for x in jh["skipped"]))
B.MY_BRAND = brand
B.run_brand("", [].append)

out2 = []
code2 = B.run_brand("acme", out2.append)
j2 = json.loads((B.LISTS / "acme-presence-brand.json").read_text(encoding="utf-8"))
names2 = {a["name"] for a in j2["assets"]}
ok("with an engine it also looks in the engine's folders: a file in a branding folder, and a picture named like a logo anywhere, but not a random picture", code2 == 0 and j2["engine"] == "acme" and {"acme-icon.png", "company-logo-old.png", "acme-logo.png"} <= names2 and "holiday.png" not in names2)
ok("a see-through icon keeps its see-through corners", next(a for a in j2["assets"] if a["name"] == "acme-icon.png")["alpha"] is True)

empty = td / "empty-brand"
B.MY_BRAND = empty
out3 = []
code3 = B.run_brand("", out3.append)
ok("with nothing to find it says so plainly (the app looks for 'found no brand') and writes no result", code3 == 0 and "found no brand" in out3[0] and empty.is_dir())
B.MY_BRAND = brand

cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]["dse.presence_brand"]
ok("the tool is in the catalog, takes an optional engine and uploads only the brand result", [f["name"] for f in cat["fields"]] == ["engine"] and cat["fields"][0]["required"] is False and cat["outputs"] == [{"glob": "my-lists/*-presence-brand.json", "upload": True}] and cat["args"][:2] == [{"lit": "presence"}, {"lit": "brand"}])

# ---- placement: the same numbers as the app's placeLogo
arr = ("tl", 20, 9)
ok("the logo is placed by the same sums as the app (whole pixels, round half up)", M.place_logo(*arr, 3, 1080, 1350) == (97, 97, 216, 72) and M.place_logo("tr", 20, 9, 3, 1080, 1350)[0] == 1080 - 97 - 216 and M.place_logo("tc", 20, 9, 3, 1080, 1350)[0] == 432 and M.place_logo("bl", 20, 9, 3, 1080, 1350)[1] == 1350 - 97 - 72 - 68)
ok("a story keeps clear of the edges apps cover", M.place_logo(*arr, 3, 1080, 1920, "story")[1] == 97 + 134 and M.place_logo("bl", 20, 9, 3, 1080, 1920, "story")[1] == 1920 - 97 - 72 - 230)
ok("a tall logo is limited, a tiny one grows, and nothing leaves the page", M.place_logo(*arr, 0.5, 1080, 1350)[3] == 81 and M.place_logo("tl", 6, 9, 6, 1080, 1350)[3] == 41 and (lambda p: p[0] >= 0 and p[0] + p[2] <= 1080)(M.place_logo("tr", 45, 14, 8, 1080, 1350)))
ok("rounding is half up, not to the even number (a 2.5 pixel result would differ)", M._round(2.5) == 3 and M._round(3.5) == 4 and M._round(0.5) == 1)

# ---- the brand block of a project
def b64(bs): return base64.b64encode(bs).decode()


good = {"logo": {"name": "l.png", "mime": "image/png", "b64": b64(png_bytes((600, 200), (255, 0, 0))), "w": 600, "h": 200},
        "avatar": {"name": "a.jpg", "mime": "image/png", "b64": b64(png_bytes((300, 300), (0, 0, 255), alpha=False)), "shape": "circle"}, "place": {"corner": "tl", "size": 20, "margin": 9}}
pb = M.parse_brand(good)
ok("a brand block is read: logo, profile picture, placement", pb and pb["logo"].size == (600, 200) and pb["avatar"] is not None and pb["corner"] == "tl" and pb["shape"] == "circle")
noisy(td / "big.png", 600)
big = (td / "big.png").read_bytes()
ok("a picture over the size limit is refused before it is decoded", len(big) > M.MAX_BRAND_BYTES and M.parse_brand({"logo": {"mime": "image/png", "b64": b64(big)}}) is None)
ok("anything that is not a real picture, is the wrong type or is too big is refused", M.parse_brand({"logo": {"mime": "image/png", "b64": b64(b"not a picture")}}) is None and M.parse_brand({"logo": {"mime": "text/html", "b64": b64(png_bytes((5, 5), (1, 1, 1)))}}) is None and M.parse_brand({"logo": {"mime": "image/png", "b64": "A" * 600_000}}) is None and M.parse_brand({"logo": {"mime": "image/png", "b64": "%%%"}}) is None and M.parse_brand("x") is None and M.parse_brand(None) is None and M.parse_brand({}) is None)
ok("odd placement values are held in range or fall back", M.parse_brand({**good, "place": {"corner": "middle", "size": 999, "margin": -5}})["corner"] == "tl" and M.parse_brand({**good, "place": {"corner": "br", "size": 999, "margin": -5}})["size"] == 45 and M.parse_brand({**good, "place": {"size": "x"}})["size"] == 20 and M.parse_brand({**good, "avatar": {**good["avatar"], "shape": "star"}})["shape"] == "circle")
tinted = M.parse_brand({**good, "logo": {**good["logo"], "b64": b64(png_bytes((60, 20), (0, 0, 0), shape="ring")), "tint": "#FBF6E9"}})
px = [tinted["logo"].getpixel((30, 10)), tinted["logo"].getpixel((0, 0))]
ok("a one-colour see-through logo can be tinted: its shape (the see-through part) stays and the colour changes", px[0][:3] == (0xFB, 0xF6, 0xE9) and px[0][3] == 255 and px[1][3] == 0)
ok("a tint is ignored for a logo with a solid background (it would become a plain box) and for a bad colour", M.parse_brand({**good, "logo": {**good["logo"], "tint": "#FBF6E9"}})["logo"].getpixel((5, 5))[:3] == (255, 0, 0) and M.parse_brand({**good, "logo": {**good["logo"], "b64": b64(png_bytes((60, 20), (0, 0, 0), shape="ring")), "tint": "red"}})["logo"].getpixel((30, 10))[:3] == (0, 0, 0))

# ---- drawing a carousel with the brand
proj = {"v": 1, "title": "brand test", "size": "post", "theme": "ink", "kit": {"bg": "#1A1410", "fg": "#FBF6E9", "accent": "#C99A3B", "muted": "#B9AD91", "head": "serif", "motif": "none"}, "footer": "@ada",
        "brand": good, "slides": [{"title": "Do your patients text you first?", "body": "Most people message before they call."}, {"title": "Reply fast", "body": "Answer in a minute."}]}
files = M.make_carousel(proj, out_dir, say=lambda *_: None)
im1, im2 = Image.open(files[0]).convert("RGB"), Image.open(files[1]).convert("RGB")
ok("every slide is made at the carousel size", len(files) == 2 and im1.size == (1080, 1350) and im2.size == (1080, 1350))
ok("the logo is drawn where the arrangement says (top left, 216 x 72 at 97,97): the red logo pixels are there and not elsewhere", im1.getpixel((150, 130)) == (255, 0, 0) and im1.getpixel((97 + 215, 97 + 71)) == (255, 0, 0) and im1.getpixel((97 + 230, 130)) != (255, 0, 0) and im1.getpixel((900, 130)) != (255, 0, 0))
ok("text starts below a logo in the top row, so the two never overlap: the whole logo box is still logo", all(im1.getpixel((x, y)) == (255, 0, 0) for x in range(100, 310, 6) for y in range(100, 166, 6)))
proj2 = {**proj, "brand": {**good, "place": {"corner": "br", "size": 20, "margin": 9}}}
im3 = Image.open(M.make_carousel(proj2, out_dir / "b", say=lambda *_: None)[0]).convert("RGB")
bx, by, bw, bh = M.place_logo("br", 20, 9, 3, 1080, 1350)
ok("a bottom-right logo is drawn there and not at the top left", im3.getpixel((bx + 10, by + 10)) == (255, 0, 0) and im3.getpixel((150, 130)) != (255, 0, 0))
ok("the profile picture sits beside the handle on the last slide only, in the shape asked for (a circle has see-through corners)", im2.getpixel((97 + 40, 1350 - 97 - 40 - 8)) == (0, 0, 255) or any(im2.getpixel((97 + x, y)) == (0, 0, 255) for x in (30, 40, 50) for y in range(1150, 1250)))
ok("a slide that is not the last has no profile picture", not any(im1.getpixel((97 + x, y)) == (0, 0, 255) for x in (30, 40, 50) for y in range(1150, 1250)))
plain = {k: v for k, v in proj.items() if k != "brand"}
files3 = M.make_carousel(plain, out_dir / "c", say=lambda *_: None)
ok("a project with no brand block is made as before: no logo, nothing breaks", len(files3) == 2 and Image.open(files3[0]).convert("RGB").getpixel((150, 130)) != (255, 0, 0))
ok("a broken brand block is ignored and the slides are still made", len(M.make_carousel({**proj, "brand": {"logo": {"mime": "image/png", "b64": "!!"}}}, out_dir / "d", say=lambda *_: None)) == 2)

src = Path(B.__file__).read_text(encoding="utf-8")
ok("it only reads the folders: its one write is its own result file, no delete or move, no network", src.count(".write_text(") == 1 and "unlink" not in src and "rename" not in src and "shutil" not in src and "requests" not in src and "urlopen" not in src and "socket" not in src)
ok("no em dash in the new files", chr(0x2014) not in src and chr(0x2014) not in Path(__file__).read_text(encoding="utf-8").replace("chr(0x2014)", ""))
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
