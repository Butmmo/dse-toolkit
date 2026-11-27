"""Spec-driven site editing checks for builder/build.py: re-render from an edited spec, the preview,
the spec rules, and the save-with-backup path. Offline; everything happens in temp folders.
Run: python tests/test_builder_render.py"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
specmod = importlib.util.spec_from_file_location("citadel_builder", ROOT / "builder" / "build.py")
B = importlib.util.module_from_spec(specmod)
specmod.loader.exec_module(B)

fails = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


def website_spec(**over):
    screens = B.blueprint("landing", "Acme Desk", "Old tagline", "A short brief", "USD")
    screens = [{**sc, "blocks": [b for b in sc["blocks"] if b["type"] in B.WEBSITE_OK]} for sc in screens]
    screens = [sc for sc in screens if sc["blocks"]]
    spec = {"name": "Acme Desk", "slug": "acme-desk", "color": "#123456", "tagline": "Old tagline",
            "description": "A short brief", "platform": "web", "currency": "USD", "email": "",
            "kind": "website", "blueprint": "landing", "screens": screens}
    spec.update(over)
    return spec


with tempfile.TemporaryDirectory() as td:
    dst = Path(td) / "acme-desk-website"
    spec = website_spec()
    B.build_site(dst, spec, B.palette(spec["color"]))
    check("a fresh build writes its home page", (dst / "index.html").is_file())
    check("the brand colour from the spec reaches the styles", "#123456" in (dst / "styles.css").read_text(encoding="utf-8"))

    # Edit the spec the way the Citadel form will: new tagline, new price, one page removed.
    edited = website_spec(tagline="A brand new promise")
    pages_before = {p.name for p in dst.glob("*.html")}
    if len(edited["screens"]) > 1:
        edited["screens"] = edited["screens"][:-1]
    B.render_site(dst, edited)
    home = (dst / "index.html").read_text(encoding="utf-8")
    check("re-render puts the edited tagline on the home page", "A brand new promise" in home)
    pages_after = {p.name for p in dst.glob("*.html")}
    check("a removed screen's page is deleted on re-render", pages_after < pages_before or len(edited["screens"]) == len(spec["screens"]))

    preview = B.preview_html(dst, edited)
    check("the preview inlines the styles", "<style>" in preview and 'href="styles.css"' not in preview)
    check("the preview inlines the script", "<script>" in preview and 'src="app.js"' not in preview)
    check("the preview carries the edited words", "A brand new promise" in preview)
    check("the preview neutralises page links", 'href="index.html"' not in preview)

    # save_spec: backup kept, new spec written, site rebuilt.
    B.write_json(dst / "spec.json", spec)
    saved = website_spec(tagline="Saved through the editor")
    backup = B.save_spec(dst, saved)
    check("save keeps a backup of the previous spec", backup.is_file() and json.loads(backup.read_text(encoding="utf-8"))["tagline"] == "Old tagline")
    check("save writes the edited spec", json.loads((dst / "spec.json").read_text(encoding="utf-8"))["tagline"] == "Saved through the editor")
    check("save rebuilds the site", "Saved through the editor" in (dst / "index.html").read_text(encoding="utf-8"))

    # The rules: non-website kinds and unknown blocks are refused, in plain words (SystemExit).
    for label, bad in [
        ("an app spec is refused for editing", website_spec(kind="webapp")),
        ("a spec with no pages is refused", website_spec(screens=[])),
        ("a spec with an app-only block is refused", website_spec(screens=[{"id": "home", "title": "Home", "blocks": [{"type": "cart"}]}])),
        ("a spec with no name is refused", website_spec(name="  ")),
    ]:
        try:
            B.check_spec(bad)
            check(label, False)
        except SystemExit:
            check(label, True)

    # make_spec carries the colour now, so a re-render years later keeps the brand.
    args = SimpleNamespace(name="Acme Desk", brief="A short brief", currency="USD", email="",
                           kind="website", blueprint="landing", color="#0a5c2e", ai=False)
    made = B.make_spec(args)
    check("new specs record their brand colour", made.get("color") == "#0a5c2e")

print("FAILED: " + str(len(fails))) if fails else print("ALL PASS")
sys.exit(1 if fails else 0)
