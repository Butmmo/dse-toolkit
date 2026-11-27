"""App Builder: one tool that scaffolds a real, working project for any kind of app.

    python builder/build.py new --kind webapp --name "Acme Desk" --blueprint dashboard --color "#7a1f2b" \
        --brief "Helps small agencies track client work" [--email me@x.com] [--currency USD] [--ai] [--install]
    python builder/build.py kinds         what you can build
    python builder/build.py blueprints    the ready-made starting points
    python builder/build.py list          the builds on this PC
    python builder/build.py render <build>   rebuild a website from its spec.json (after editing the spec, by hand or in Citadel)

Kinds:      website | webapp | mobile | desktop | tv
Blueprints: landing | dashboard | store | booking | blank

What you get in builds/<slug>/ : a project that runs and builds as it is (no placeholders to fix first), a
README with the exact commands, BUILD-BRIEF.md (what was built and the next things to build), AGENTS.md (rules
so an AI coding agent can carry on safely) and spec.json (the screens, as data). Free: stdlib only here; the
generated project needs Node.js (nodejs.org, LTS) to run, except the plain website which needs nothing.
Nothing here publishes, pays or sends: you do every deploy yourself.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TPL = HERE / "templates"
OUT = ROOT / "builds"

KINDS = {
    "website": "A fast, accessible multi-page website (plain HTML, CSS, a little JavaScript). Needs no tools to open; host it free.",
    "webapp": "A web app (React + TypeScript + Vite) that installs on phones like an app (PWA) and works offline.",
    "mobile": "A native iPhone + Android app (Expo / React Native) you test on your own phone with Expo Go.",
    "desktop": "A Windows/Mac/Linux desktop app (Electron wrapping the web app) with an installer build.",
    "tv": "A TV app (Samsung Tizen, LG webOS, Android TV browsers): big text, remote-control navigation, packaging files.",
}
BLUEPRINTS = {
    "landing": "Home, Pricing, About, Contact. For a business or product that needs customers.",
    "dashboard": "Overview with live counts, an Items manager (add, status, delete), Settings. For tools people log in to use.",
    "store": "Shop with add-to-cart, Cart with totals, About. For selling products.",
    "booking": "Home, Book (appointment form), Bookings list. For services that take appointments.",
    "blank": "One home screen. Start from nothing but the design system.",
}
WEBSITE_OK = {"hero", "features", "pricing", "text", "form", "products"}   # blocks a static website can do on its own


# ----------------------------------------------------------------------------- small helpers

def clean_text(s: str, limit: int) -> str:
    s = re.sub(r"[\"\\<>`{}$]", "", s or "")
    return re.sub(r"\s+", " ", s).strip()[:limit]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40].strip("-") or "my-app"


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))


def palette(color: str) -> dict:
    r, g, b = hex_to_rgb(color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    strong = rgb_to_hex(*colorsys.hls_to_rgb(h, max(0.0, l - 0.09), s))
    light = rgb_to_hex(*colorsys.hls_to_rgb(h, min(0.82, l + 0.2), s))
    tint = rgb_to_hex(*colorsys.hls_to_rgb(h, 0.94, min(s, 0.85)))
    return {"color": color.lower(), "strong": strong, "light": light, "tint": tint,
            "on": "#ffffff" if lum < 0.6 else "#14161c"}


def tokens_css(p: dict) -> str:
    return (f":root{{--brand:{p['color']};--brand-strong:{p['strong']};--brand-light:{p['light']};--on-brand:{p['on']};--tint:{p['tint']};"
            "--bg:#ffffff;--surface:#ffffff;--ink:#14161c;--muted:#5b6472;--line:#e5e8ee;--danger:#d92d20;"
            "--shadow-sm:0 1px 2px rgba(16,24,40,.06);--shadow:0 14px 34px -14px rgba(16,24,40,.28)}\n"
            "@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--surface:#181b22;--ink:#f2f4f8;--muted:#9aa3b2;--line:#2a2f3a;"
            "--tint:color-mix(in srgb,var(--brand) 20%,#0f1115);--brand-strong:var(--brand-light)}}\n")


# ----------------------------------------------------------------------------- the spec: screens as data

def blueprint(bp: str, name: str, tagline: str, brief: str, currency: str) -> list[dict]:
    desc = brief or f"{name} makes the work simpler, faster and clearer."
    hero = lambda eyebrow, cta, to, cta2=None, to2=None: {  # noqa: E731
        "type": "hero", "eyebrow": eyebrow, "headline": tagline, "sub": desc,
        "cta": {"label": cta, "to": to}, **({"cta2": {"label": cta2, "to": to2}} if cta2 else {})}
    contact_fields = [
        {"name": "name", "label": "Your name", "type": "text", "required": True},
        {"name": "email", "label": "Email", "type": "email", "required": True},
        {"name": "message", "label": "How can we help?", "type": "textarea", "required": True}]
    if bp == "landing":
        return [
            {"id": "home", "title": "Home", "blocks": [
                hero("Welcome", "See pricing", "pricing", "Talk to us", "contact"),
                {"type": "features", "title": "Why people choose " + name, "items": [
                    {"title": "Clear from day one", "text": "Simple steps and plain language, so you know what happens next."},
                    {"title": "Built for results", "text": "Everything here exists to move you closer to the outcome you came for."},
                    {"title": "Support that answers", "text": "Ask a question and a real person replies, usually the same day."}]}]},
            {"id": "pricing", "title": "Pricing", "blocks": [{"type": "pricing", "title": "Simple pricing", "tiers": [
                {"name": "Starter", "price": "$0", "per": "to begin", "features": ["Core features", "Email support", "Cancel any time"]},
                {"name": "Pro", "price": "$29", "per": "per month", "features": ["Everything in Starter", "Priority support", "Advanced tools"], "featured": True},
                {"name": "Team", "price": "$79", "per": "per month", "features": ["Everything in Pro", "Up to 10 people", "Shared workspace"]}]}]},
            {"id": "about", "title": "About", "blocks": [{"type": "text", "title": "About " + name, "body": [desc,
                "We keep things honest: clear prices, clear promises, and work you can check for yourself."]}]},
            {"id": "contact", "title": "Contact", "blocks": [{"type": "form", "title": "Talk to us", "intro": "Tell us what you need and we will reply.",
                "collection": "messages", "fields": contact_fields, "submit": "Send message", "success": "Thanks. We got your message and will reply soon."}]}]
    if bp == "dashboard":
        return [
            {"id": "overview", "title": "Overview", "blocks": [
                {"type": "hero", "eyebrow": "Dashboard", "headline": tagline, "sub": desc, "cta": {"label": "Add an item", "to": "items"}},
                {"type": "stats", "items": [
                    {"label": "Total items", "collection": "items"},
                    {"label": "In progress", "collection": "items", "where": {"field": "status", "equals": "Doing"}},
                    {"label": "Done", "collection": "items", "where": {"field": "status", "equals": "Done"}}]}]},
            {"id": "items", "title": "Items", "blocks": [{"type": "list", "title": "Your items", "collection": "items", "titleField": "title", "badgeField": "status", "addable": True,
                "fields": [{"name": "title", "label": "Title", "type": "text", "required": True},
                           {"name": "status", "label": "Status", "type": "select", "options": ["To do", "Doing", "Done"]},
                           {"name": "notes", "label": "Notes", "type": "textarea"}]}]},
            {"id": "settings", "title": "Settings", "blocks": [{"type": "form", "title": "Your details", "collection": "profile",
                "fields": [{"name": "name", "label": "Name", "type": "text", "required": True}, {"name": "email", "label": "Email", "type": "email"}],
                "submit": "Save", "success": "Saved."}]}]
    if bp == "store":
        return [
            {"id": "shop", "title": "Shop", "blocks": [
                hero("New in", "Browse the shop", "shop"),
                {"type": "products", "title": "Products", "items": [
                    {"id": "p1", "name": "Starter pack", "price": 15, "text": "A simple way to begin."},
                    {"id": "p2", "name": "Standard pack", "price": 35, "text": "Our most popular choice."},
                    {"id": "p3", "name": "Premium pack", "price": 79, "text": "Everything, with extras."}]}]},
            {"id": "cart", "title": "Cart", "blocks": [{"type": "cart", "title": "Your cart"}]},
            {"id": "about", "title": "About", "blocks": [{"type": "text", "title": "About " + name, "body": [desc, "Edit the products in spec.json, then rebuild."]}]}]
    if bp == "booking":
        return [
            {"id": "home", "title": "Home", "blocks": [hero("Book online", "Book now", "book"),
                {"type": "features", "items": [
                    {"title": "Pick a time", "text": "Choose the day and time that suits you."},
                    {"title": "Get confirmed", "text": "We confirm your slot so nothing is left to chance."},
                    {"title": "Show up", "text": "Arrive, and we take care of the rest."}]}]},
            {"id": "book", "title": "Book", "blocks": [{"type": "form", "title": "Book an appointment", "collection": "bookings",
                "fields": [{"name": "name", "label": "Your name", "type": "text", "required": True},
                           {"name": "email", "label": "Email", "type": "email", "required": True},
                           {"name": "service", "label": "Service", "type": "select", "options": ["Consultation", "Standard visit", "Extended visit"]},
                           {"name": "date", "label": "Date", "type": "date", "required": True},
                           {"name": "time", "label": "Time", "type": "time", "required": True}],
                "submit": "Request booking", "success": "Booking requested. We will confirm shortly."}]},
            {"id": "bookings", "title": "Bookings", "blocks": [{"type": "list", "title": "Bookings", "collection": "bookings", "titleField": "name", "badgeField": "service",
                "addable": False, "fields": [{"name": "name", "label": "Name", "type": "text"}, {"name": "service", "label": "Service", "type": "select", "options": []},
                                             {"name": "date", "label": "Date", "type": "date"}, {"name": "time", "label": "Time", "type": "time"}]}]}]
    return [{"id": "home", "title": "Home", "blocks": [hero("Welcome", "Get started", "home"),
            {"type": "text", "title": "Start here", "body": ["This is your blank starting point. Add screens in spec.json and rebuild."]}]}]


def ask_ollama(name: str, brief: str) -> dict | None:
    """Optional: the free local AI writes the tagline and 3 benefits. Any problem and we just use the built-in copy."""
    model = os.environ.get("OLLAMA_MODEL", "gemma3:1b")
    prompt = (f"App name: {name}. What it does: {brief}. Reply with JSON only: "
              '{"tagline": "max 8 words", "benefits": [{"title": "3 words", "text": "one short sentence"}, {"title": "..", "text": ".."}, {"title": "..", "text": ".."}]}')
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
        out = json.loads(json.loads(urllib.request.urlopen(req, timeout=150).read())["response"])
        tag = clean_text(str(out["tagline"]), 80)
        ben = [{"title": clean_text(str(b["title"]), 40), "text": clean_text(str(b["text"]), 140)} for b in out["benefits"][:3]]
        if tag and len(ben) == 3 and all(b["title"] and b["text"] for b in ben):
            return {"tagline": tag, "benefits": ben}
    except Exception:
        pass
    return None


def make_spec(a) -> dict:
    name = clean_text(a.name, 40)
    brief = clean_text(a.brief, 200)
    tagline = f"{name}: built for people who want results"
    copy = ask_ollama(name, brief) if a.ai and brief else None
    if copy:
        tagline = copy["tagline"]
    screens = blueprint(a.blueprint, name, tagline, brief, a.currency)
    if copy:
        for sc in screens:
            for b in sc["blocks"]:
                if b["type"] == "features":
                    b["items"] = copy["benefits"]
    if a.kind == "website":      # a static site has no database: keep what it can do alone
        screens = [{**sc, "blocks": [b for b in sc["blocks"] if b["type"] in WEBSITE_OK]} for sc in screens]
        screens = [sc for sc in screens if sc["blocks"]]
    return {"name": name, "slug": slugify(name), "color": a.color, "tagline": tagline,
            "description": brief or f"{name}: {tagline}", "platform": {"desktop": "desktop", "tv": "tv"}.get(a.kind, "web"),
            "currency": a.currency, "email": a.email or "", "kind": a.kind, "blueprint": a.blueprint, "screens": screens}


# ----------------------------------------------------------------------------- writing files

def tokens_for(spec: dict, p: dict) -> dict:
    slugclean = re.sub(r"[^a-z0-9]", "", spec["slug"]) or "app"
    return {"__NAME__": spec["name"], "__SLUG__": spec["slug"], "__SLUGCLEAN__": slugclean, "__SHORT__": spec["name"][:12],
            "__DESC__": spec["description"], "__COLOR__": p["color"], "__COLORSTRONG__": p["strong"], "__ONCOLOR__": p["on"],
            "__TINT__": p["tint"], "__INITIAL__": spec["name"][:1].upper(),
            "__TIZENID__": hashlib.sha1(spec["slug"].encode()).hexdigest()[:10].replace("e", "E")}


TEXT_EXT = {".json", ".ts", ".tsx", ".js", ".cjs", ".mjs", ".html", ".css", ".xml", ".svg", ".webmanifest", ".md", ".txt", ".gitignore"}


def copy_tree(src: Path, dst: Path, toks: dict) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_dir():
            continue
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix in TEXT_EXT:
            s = f.read_text(encoding="utf-8")
            for k, v in toks.items():
                s = s.replace(k, v)
            target.write_text(s, encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(f, target)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_web(dst: Path, spec: dict, p: dict, toks: dict, kind: str) -> None:
    copy_tree(TPL / "web", dst, toks)
    css = (TPL / "common" / "base.css").read_text(encoding="utf-8")
    (dst / "src" / "base.css").write_text(tokens_css(p) + css, encoding="utf-8", newline="\n")
    write_json(dst / "src" / "spec.json", {k: v for k, v in spec.items() if k not in ("email", "kind", "blueprint")})
    pkg = json.loads((dst / "package.json").read_text(encoding="utf-8"))
    if kind == "desktop":
        copy_tree(TPL / "desktop", dst, toks)
        pkg["main"] = "electron/main.cjs"
        pkg["description"] = spec["description"]
        pkg["author"] = "D'Famocious Ltd"
        pkg["scripts"].update({
            "desktop": "vite build && electron .",
            "desktop:dev": 'concurrently -k "vite --port 5173 --strictPort" "wait-on tcp:5173 && cross-env VITE_DEV_URL=http://localhost:5173 electron ."',
            "desktop:build": "npm run build && electron-builder"})
        pkg["devDependencies"].update({"electron": "^38.0.0", "electron-builder": "^26.0.0", "concurrently": "^9.0.0", "wait-on": "^8.0.0", "cross-env": "^7.0.3"})
        pkg["build"] = {"appId": f"com.example.{toks['__SLUGCLEAN__']}", "productName": spec["name"], "files": ["dist/**", "electron/**", "package.json"],
                        "directories": {"output": "release"}, "win": {"target": "nsis"}, "mac": {"target": "dmg"}, "linux": {"target": "AppImage"}}
    if kind == "tv":
        copy_tree(TPL / "tv", dst, toks)
    write_json(dst / "package.json", pkg)


def build_mobile(dst: Path, spec: dict, p: dict, toks: dict) -> None:
    copy_tree(TPL / "mobile", dst, toks)
    write_json(dst / "src" / "spec.json", {k: v for k, v in spec.items() if k not in ("email", "kind", "blueprint")})


# ---- the plain website (no framework)

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def page_href(spec: dict, sid: str) -> str:
    return "index.html" if sid == spec["screens"][0]["id"] else f"{sid}.html"


def site_block(spec: dict, b: dict) -> str:
    t = b["type"]
    if t == "hero":
        btns = "".join(f'<a class="btn{" ghost" if i else ""}" href="{page_href(spec, c["to"])}">{esc(c["label"])}</a>'
                       for i, c in enumerate([b.get("cta"), b.get("cta2")]) if c)
        eb = f'<span class="eyebrow">{esc(b["eyebrow"])}</span>' if b.get("eyebrow") else ""
        return f'<section class="hero"><div class="container">{eb}<h1>{esc(b["headline"])}</h1><p class="lead">{esc(b["sub"])}</p><div class="actions">{btns}</div></div></section>'
    if t == "features":
        cards = "".join(f'<div class="card reveal"><div class="icon">{i + 1}</div><h3>{esc(f["title"])}</h3><p class="muted">{esc(f["text"])}</p></div>' for i, f in enumerate(b["items"]))
        title = f'<h2>{esc(b["title"])}</h2>' if b.get("title") else ""
        return f'<section class="section"><div class="container">{title}<div class="grid">{cards}</div></div></section>'
    if t == "pricing":
        cards = ""
        for x in b["tiers"]:
            ticks = "".join(f"<li>{esc(f)}</li>" for f in x["features"])
            cards += f'<div class="card reveal{" featured" if x.get("featured") else ""}"><h3>{esc(x["name"])}</h3><div class="price">{esc(x["price"])} <small>{esc(x["per"])}</small></div><ul class="ticks">{ticks}</ul></div>'
        return f'<section class="section"><div class="container"><h2>{esc(b["title"])}</h2><div class="grid">{cards}</div></div></section>'
    if t == "text":
        ps = "".join(f"<p>{esc(x)}</p>" for x in b["body"])
        return f'<section class="section"><div class="container reveal" style="max-width:760px"><h2>{esc(b["title"])}</h2>{ps}</div></section>'
    if t == "products":
        mail = spec.get("email") or "you@example.com"
        cards = "".join(
            f'<div class="card reveal"><div class="icon">{esc(p["name"][:1])}</div><h3>{esc(p["name"])}</h3><p class="muted">{esc(p["text"])}</p>'
            f'<div class="price">{esc(spec["currency"])} {esc(p["price"])}</div>'
            f'<p><a class="btn" href="mailto:{esc(mail)}?subject={esc("Order: " + p["name"])}">Order this</a></p></div>' for p in b["items"])
        return f'<section class="section"><div class="container"><h2>{esc(b["title"])}</h2><div class="grid">{cards}</div></div></section>'
    if t == "form":
        fields = ""
        for f in b["fields"]:
            n, req = esc(f["name"]), " required" if f.get("required") else ""
            if f["type"] == "textarea":
                inp = f'<textarea id="{n}" name="{n}"{req}></textarea>'
            elif f["type"] == "select":
                inp = f'<select id="{n}" name="{n}">' + "".join(f"<option>{esc(o)}</option>" for o in f.get("options", [])) + "</select>"
            else:
                inp = f'<input id="{n}" name="{n}" type="{esc(f["type"])}"{req}>'
            fields += f'<div class="field"><label for="{n}">{esc(f["label"])}</label>{inp}</div>'
        intro = f'<p class="muted">{esc(b["intro"])}</p>' if b.get("intro") else ""
        return (f'<section class="section"><div class="container" style="max-width:640px"><h2>{esc(b["title"])}</h2>{intro}'
                f'<p class="note" id="ok" role="status" hidden>{esc(b["success"])}</p>'
                f'<form id="form" data-mail="{esc(spec.get("email") or "")}" data-subject="{esc(b["title"])}">{fields}<button class="btn" type="submit">{esc(b["submit"])}</button></form></div></section>')
    return ""


def build_site(dst: Path, spec: dict, p: dict) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "styles.css").write_text(tokens_css(p) + (TPL / "common" / "base.css").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    (dst / "app.js").write_text((TPL / "site" / "app.js").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    (dst / "icon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="{p["color"]}"/>'
        f'<text x="32" y="43" font-family="Arial,sans-serif" font-size="34" font-weight="800" text-anchor="middle" fill="{p["on"]}">{esc(spec["name"][:1].upper())}</text></svg>\n', encoding="utf-8")
    for sc in spec["screens"]:
        cur = ' aria-current="page"'
        nav = "".join(f'<a href="{page_href(spec, s["id"])}"{cur if s["id"] == sc["id"] else ""}>{esc(s["title"])}</a>' for s in spec["screens"])
        body = "".join(site_block(spec, b) for b in sc["blocks"])
        title = f'{sc["title"]} | {spec["name"]}' if sc is not spec["screens"][0] else f'{spec["name"]}: {spec["tagline"]}'
        page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(spec['description'])}">
<meta name="theme-color" content="{p['color']}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(spec['description'])}">
<meta property="og:type" content="website">
<link rel="icon" type="image/svg+xml" href="icon.svg">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header"><div class="container bar">
<a class="brand" href="index.html"><span class="mark">{esc(spec['name'][:1].upper())}</span>{esc(spec['name'])}</a>
<button class="menu-btn" aria-expanded="false" aria-controls="nav">Menu</button>
<nav id="nav" class="nav" aria-label="Main">{nav}</nav>
</div></header>
<main id="main">{body}</main>
<footer class="site-footer"><div class="container">&copy; <span id="yr"></span> {esc(spec['name'])}. {esc(spec['tagline'])}</div></footer>
<script src="app.js" defer></script>
</body>
</html>
"""
        (dst / page_href(spec, sc["id"])).write_text(page, encoding="utf-8", newline="\n")
    base = "https://example.com"
    urls = "".join(f"<url><loc>{base}/{page_href(spec, s['id'])}</loc></url>" for s in spec["screens"])
    (dst / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n', encoding="utf-8")
    (dst / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    write_json(dst / "spec.json", spec)


# ----------------------------------------------------------------------------- the documents

SHIP = {
    "website": """1. Open `index.html` by double-clicking it: that is your whole site.
2. Put your real address in `sitemap.xml` and `robots.txt` (replace `https://example.com`).
3. Host it free: Cloudflare Pages -> Create a project -> Direct upload -> drag this folder in. You get a `.pages.dev` address at once.
4. Later: connect your own domain in the same Cloudflare screen, then add the address to Google Search Console.
5. The contact form opens the visitor's email app addressed to you. For forms that arrive in a dashboard, use a free form service (Formspree, Web3Forms) and set the form's `action`.""",
    "webapp": """1. `npm install` (once), then `npm run dev` and open the address it prints.
2. `npm run build` makes the `dist/` folder. That folder is the finished app.
3. Host it free: Cloudflare Pages (Direct upload of `dist/`) or Netlify Drop. Phones can then "Add to home screen": it installs like an app and works offline.
4. Your data is saved in each person's browser. When you need accounts and shared data, add a backend (Supabase free tier is the usual choice) in `src/store.ts`: it is the only file that reads and writes data.""",
    "mobile": """1. Install Node.js LTS, then in this folder: `npm install` and `npx expo install --fix` (this picks versions that match each other).
2. `npx expo start`. Install **Expo Go** from the Play Store or App Store on your phone and scan the QR code: your app opens on your phone, live.
3. To get a real installable app: `npm install -g eas-cli`, `eas login`, `eas build -p android --profile preview` gives you an APK file you can send to anyone (free tier, queue can be slow).
4. Stores: Google Play costs a one-time $25; Apple costs $99 per year. Do not pay until the app is tested by real users.
5. Data is saved on the phone. For accounts and shared data, change `src/store.ts` to call your backend.""",
    "desktop": """1. `npm install` (once), then `npm run desktop:dev` for a live window while you build.
2. `npm run desktop` builds the app and opens it as the installed version would look.
3. `npm run desktop:build` makes the installer in `release/` (a Windows `.exe` when you run it on Windows; build on a Mac for the Mac version).
4. Windows warns about apps without a code-signing certificate. That is normal at the start. Sign it once you have paying users.
5. The window shows exactly your web app; `electron/preload.cjs` is where safe desktop features (files, notifications) are added.""",
    "tv": """1. `npm install`, then `npm run dev`. Open it in a browser and use only the **arrow keys, Enter and Esc**: that is how a TV remote behaves.
2. `npm run build` makes `dist/`. This is the TV app.
3. **Samsung (Tizen):** install Tizen Studio, copy `packaging/tizen/config.xml` into `dist/`, create a TV project from that folder and package it. Test on the TV emulator, then submit through Samsung Seller Office.
4. **LG (webOS):** install the webOS CLI (`npm i -g @webos-tooling/cli`), copy `packaging/webos/appinfo.json` and a 80x80 `icon.png` into `dist/`, run `ares-package dist`.
5. **Android TV / Fire TV:** wrap `dist/` with Capacitor (`npx cap add android`) and add the Leanback launcher in the manifest, or host the app and use a Trusted Web Activity.
6. TV store review is strict about remote navigation, back-button behaviour and loading speed: test every screen with the keyboard only.""",
}
RUN = {"website": "Open `index.html`.", "webapp": "`npm install` then `npm run dev`.", "mobile": "`npm install`, `npx expo install --fix`, `npx expo start`.",
       "desktop": "`npm install` then `npm run desktop:dev`.", "tv": "`npm install` then `npm run dev` (use only the keyboard arrows)."}


# ----------------------------------------------------------------------------- re-rendering an existing build

def find_build(arg: str) -> Path:
    p = Path(arg)
    if not p.is_absolute() and not p.exists():
        p = OUT / arg
    if not (p / "spec.json").is_file():
        sys.exit(f"No build found at {p}. List them with: python builder/build.py list")
    return p


def load_spec(dst: Path) -> dict:
    try:
        return json.loads((dst / "spec.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"That build's spec.json cannot be read: {e}")


def render_site(dst: Path, spec: dict) -> None:
    """Rebuild a website's pages from its spec, exactly as 'new' made them. Pages whose screens were removed are deleted."""
    if spec.get("kind") != "website":
        sys.exit("Only website builds re-render from their spec here. Apps keep their screens in src/spec.json and rebuild with their own project commands (see the build's README).")
    for old in dst.glob("*.html"):
        old.unlink()
    build_site(dst, spec, palette(spec.get("color") or "#7a1f2b"))


def check_spec(spec) -> dict:
    """The rules an edited spec must pass before it may replace a build's spec. Plain words, no partial writes."""
    if not isinstance(spec, dict):
        sys.exit("The spec must be a JSON object.")
    if spec.get("kind") != "website":
        sys.exit("Spec editing covers website builds for now; this build is a " + str(spec.get("kind") or "unknown") + ".")
    if not str(spec.get("name") or "").strip():
        sys.exit("The spec needs the business name.")
    screens = spec.get("screens")
    if not isinstance(screens, list) or not screens:
        sys.exit("The spec needs at least one screen (page).")
    for sc in screens:
        if not isinstance(sc, dict) or not str(sc.get("id") or "").strip() or not isinstance(sc.get("blocks"), list):
            sys.exit("Every screen needs an id and a list of blocks.")
        for b in sc["blocks"]:
            if not isinstance(b, dict) or b.get("type") not in WEBSITE_OK:
                sys.exit("A website block has an unknown type: " + str((b or {}).get("type")) + ". Website blocks are: " + ", ".join(sorted(WEBSITE_OK)) + ".")
    return spec


def save_spec(dst: Path, spec: dict) -> Path:
    """Keep the previous spec, write the edited one, and rebuild the site from it."""
    check_spec(spec)
    keep = dst / "spec-backups"
    keep.mkdir(exist_ok=True)
    n = 1
    while (keep / f"spec-{n}.json").exists():
        n += 1
    backup = keep / f"spec-{n}.json"
    backup.write_text((dst / "spec.json").read_text(encoding="utf-8"), encoding="utf-8")
    write_json(dst / "spec.json", spec)
    render_site(dst, spec)
    return backup


def preview_html(dst: Path, spec: dict) -> str:
    """The home page as one self-contained file (styles and script inlined), for the in-app preview in Citadel."""
    render_site(dst, spec)
    page = (dst / "index.html").read_text(encoding="utf-8")
    css = (dst / "styles.css").read_text(encoding="utf-8")
    js = (dst / "app.js").read_text(encoding="utf-8")
    page = page.replace('<link rel="stylesheet" href="styles.css">', "<style>\n" + css + "\n</style>")
    page = page.replace('<script src="app.js" defer></script>', "<script>\n" + js + "\n</script>")
    for sc in spec["screens"]:
        page = page.replace(f'href="{page_href(spec, sc["id"])}"', 'href="#"')
    return page


def cmd_list() -> int:
    found = False
    if OUT.exists():
        for d in sorted(OUT.iterdir()):
            if (d / "spec.json").is_file():
                s = load_spec(d)
                print(f"BUILD\t{d.name}\t{s.get('name', '')}\t{s.get('kind', '')}\t{s.get('blueprint', '')}\t{len(s.get('screens', []))}")
                found = True
    if not found:
        print("No builds yet. Make one with the App Builder in HQ Tools.")
    return 0


def cmd_spec(a) -> int:
    dst = find_build(a.build)
    print("SPEC_JSON_BEGIN")
    print(json.dumps(load_spec(dst)))
    print("SPEC_JSON_END")
    return 0


def cmd_save(a) -> int:
    dst = find_build(a.build)
    try:
        spec = json.loads(a.spec)
    except ValueError as e:
        sys.exit(f"The spec sent from Citadel is not valid JSON: {e}")
    backup = save_spec(dst, spec)
    print(f"Saved and rebuilt '{spec['name']}'. The previous spec is kept at {backup}.")
    return 0


def cmd_render(a) -> int:
    dst = find_build(a.build)
    spec = load_spec(dst)
    if a.color:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", a.color):
            sys.exit('The colour must look like "#7a1f2b".')
        spec["color"] = a.color
        write_json(dst / "spec.json", spec)
    render_site(dst, spec)
    print(f"Rebuilt '{spec.get('name', '')}' from its spec.")
    return 0


def cmd_preview(a) -> int:
    dst = find_build(a.build)
    spec = load_spec(dst)
    text = preview_html(dst, spec)
    (dst / "preview.html").write_text(text, encoding="utf-8", newline="\n")
    print("PREVIEW_HTML_BEGIN")
    print(text)
    print("PREVIEW_HTML_END")
    print(f"A standalone copy is at {dst / 'preview.html'}")
    return 0


def write_docs(dst: Path, spec: dict, a) -> None:
    kind = a.kind
    screens = "\n".join(f"- **{s['title']}** (`{s['id']}`): " + ", ".join(b["type"] for b in s["blocks"]) for s in spec["screens"])
    (dst / "README.md").write_text(f"""# {spec['name']}

{spec['description']}

Built with the DSE Toolkit App Builder: **{kind}**, starting point **{a.blueprint}**. It runs as it is. Nothing is a placeholder you must fix first.

## Run it
{RUN[kind]}

## Screens
{screens}

## Ship it
{SHIP[kind]}

## Change things
- Words, prices, products, screens: edit `{'spec.json' if kind == 'website' else 'src/spec.json'}`{'' if kind == 'website' else ' and rebuild'}. Every screen is data: a list of blocks (`hero`, `features`, `pricing`, `text`, `form`, `list`, `stats`, `products`, `cart`).
- Colour: `{'styles.css' if kind == 'website' else 'src/base.css'}`, the first lines (`--brand`).
- To let an AI coding agent carry on, open this folder in it. `AGENTS.md` tells it the rules. `BUILD-BRIEF.md` lists what to build next.
""", encoding="utf-8", newline="\n")
    (dst / "AGENTS.md").write_text(f"""# Rules for an AI coding agent working on {spec['name']}

Read `README.md` and `BUILD-BRIEF.md` first. This project was generated by the App Builder and already builds.

- Kind: **{kind}**. Screens are data in `{'spec.json' if kind == 'website' else 'src/spec.json'}`; the renderer is `{'the builder: edit spec.json (or use My builds in Citadel) and rebuild with: python builder/build.py render <this folder>' if kind == 'website' else ('src/sections.tsx' if kind != 'mobile' else 'src/screens.tsx')}`.
- Keep it working: after every change run `{'open each page and check it' if kind == 'website' else 'npm run typecheck'}`{'' if kind == 'website' else ' and the build (`npm run build`)' if kind != 'mobile' else ''}. Do not leave it broken.
- Data access lives only in `src/store.ts`. To add a backend, change that file, not every screen.
- Keep the design system: colours come from CSS variables / `src/theme.ts`. Do not hard-code new colours. Keep text readable in dark mode and every control reachable by keyboard{' and by TV remote (arrow keys)' if kind == 'tv' else ''}.
- Do not add a library for something the code already does. Keep dependencies few.
- Never put secrets (API keys, passwords) in the project. Use environment variables.
- Do not use the long dash character in any text. Use a colon or a hyphen.
- Do not publish, pay or send anything on the owner's behalf. The owner deploys.
""", encoding="utf-8", newline="\n")
    nexts = {
        "landing": ["Replace the placeholder pricing with your real prices", "Add 3 real testimonials or results to the Home screen", "Connect the contact form to email (Formspree or Web3Forms)", "Add a real photo or logo to Home and About", "Write the About screen with your true story and proof"],
        "dashboard": ["Add login (Supabase Auth) and move `store.ts` to a real database", "Add edit (not just add/delete) on Items", "Add search and filters on Items", "Add an export to CSV button", "Add charts to Overview from real data"],
        "store": ["Connect checkout with Paystack or Stripe (screen `cart`)", "Add product photos and a detail view", "Add stock counts and order emails", "Add delivery fees by location", "Add a policies page: returns, delivery, privacy"],
        "booking": ["Send a confirmation email or WhatsApp message on each booking", "Block already-taken time slots", "Add opening hours and days closed", "Let owners confirm or cancel bookings", "Add reminders the day before"],
        "blank": ["Decide the 3 screens the app needs and add them to spec.json", "Pick the first real feature and build only that", "Add data saving in store.ts", "Add a settings screen", "Write the README for a new user"],
    }[a.blueprint]
    (dst / "BUILD-BRIEF.md").write_text(f"""# Build brief: {spec['name']}

| | |
|---|---|
| What it is | {kind} app |
| Starting point | {a.blueprint}: {BLUEPRINTS[a.blueprint]} |
| One line | {spec['tagline']} |
| For | {spec['description']} |
| Brand colour | {a.color} |

## What exists now
{screens}

It builds and runs, saves its data locally ({'in the visitor\'s browser' if kind in ('webapp', 'desktop', 'tv', 'website') else 'on the phone'}), looks right in light and dark mode, and is keyboard accessible.

## Build next (in this order)
{chr(10).join(f"{i}. {n}" for i, n in enumerate(nexts, 1))}

## Before you tell anyone about it
- [ ] Every screen opened and used by someone who did not build it
- [ ] Real words, real prices, real contact details everywhere (search for "example.com" and "$")
- [ ] Works on a cheap phone and a slow connection
- [ ] A privacy note if you collect any personal data
- [ ] You know who it is for and the one action they should take

## How to ask an AI to continue
"Open this folder. Read AGENTS.md and BUILD-BRIEF.md. Do item 1 of 'Build next'. Run the checks in AGENTS.md. Tell me what changed."
""", encoding="utf-8", newline="\n")
    (dst / ".gitignore").write_text("node_modules/\ndist/\nrelease/\n.expo/\n*.log\n.env\n.env.*\n", encoding="utf-8", newline="\n")


# ----------------------------------------------------------------------------- checking and packaging

def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str], cwd: Path, label: str, timeout: int = 900) -> bool:
    print(f"... {label}", flush=True)
    exe = shutil.which(cmd[0])
    if not exe:
        print(f"    {cmd[0]} not found")
        return False
    try:
        r = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("    timed out")
        return False
    if r.returncode:
        print((r.stdout + r.stderr)[-1500:])
        return False
    return True


def verify(dst: Path, kind: str) -> list[str]:
    notes = []
    if kind == "website":
        pages = list(dst.glob("*.html"))
        notes.append(f"OK: {len(pages)} pages written, no install needed")
        return notes
    if not have("node") or not have("npm"):
        return ["Node.js is not installed, so the project was not test-built. Install Node.js LTS from nodejs.org, then follow README.md."]
    if not run(["npm", "install", "--no-audit", "--no-fund"], dst, "npm install (a few minutes the first time)"):
        return ["npm install failed: see the message above. The files are written; fix your internet and run npm install yourself."]
    if kind == "mobile":
        ok = run(["npx", "expo", "install", "--fix"], dst, "expo install --fix")
        notes.append("OK: dependencies match the Expo version" if ok else "Run `npx expo install --fix` yourself.")
        ok = run(["npm", "run", "typecheck"], dst, "type check")
        notes.append("OK: type check passed" if ok else "Type check reported problems (see above).")
        return notes
    ok = run(["npm", "run", "build"], dst, "build")
    notes.append("OK: the app builds" if ok else "The build reported problems (see above).")
    if kind == "desktop":
        notes.append("OK: electron files present" if (dst / "electron" / "main.cjs").exists() else "electron files missing")
    return notes


def make_zip(dst: Path) -> Path:
    z = dst.with_suffix(".zip")
    skip = {"node_modules", "dist", "release", ".expo"}
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in dst.rglob("*"):
            if f.is_file() and not (skip & set(f.relative_to(dst).parts)):
                zf.write(f, Path(dst.name) / f.relative_to(dst))
    return z


# ----------------------------------------------------------------------------- command line

def cmd_new(a) -> int:
    if a.kind not in KINDS:
        sys.exit(f"kind must be one of: {', '.join(KINDS)}")
    if a.blueprint not in BLUEPRINTS:
        sys.exit(f"blueprint must be one of: {', '.join(BLUEPRINTS)}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '-]{1,39}", a.name or ""):
        sys.exit("The name needs 2-40 letters, numbers, spaces or hyphens.")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", a.color):
        sys.exit('The colour must look like "#7a1f2b".')
    if a.email and not re.fullmatch(r"[^@\s\"'<>]{1,60}@[^@\s\"'<>]{3,60}", a.email):
        sys.exit("That email address does not look right.")
    a.currency = (a.currency or "USD").upper()
    if not re.fullmatch(r"[A-Z]{3}", a.currency):
        sys.exit("Currency is a 3-letter code such as USD, GBP, NGN.")
    spec = make_spec(a)
    p = palette(a.color)
    OUT.mkdir(exist_ok=True)
    dst, n = OUT / f"{spec['slug']}-{a.kind}", 1
    while dst.exists():
        n += 1
        dst = OUT / f"{spec['slug']}-{a.kind}-{n}"
    toks = tokens_for(spec, p)
    if a.kind == "website":
        build_site(dst, spec, p)
    elif a.kind == "mobile":
        build_mobile(dst, spec, p, toks)
    else:
        build_web(dst, spec, p, toks, a.kind)
    write_docs(dst, spec, a)
    print(f"Built {a.kind} project '{spec['name']}' ({a.blueprint}) in {dst}")
    for line in (verify(dst, a.kind) if a.install else ["Not test-built (tick 'Install and test the build' to do that)."]):
        print(line)
    z = make_zip(dst)
    print(f"Zip for sharing: {z}")
    print("\nNext: open README.md in the project folder. It has the exact commands to run and to ship it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--kind", required=True)
    n.add_argument("--name", required=True)
    n.add_argument("--blueprint", default="landing")
    n.add_argument("--color", default="#7a1f2b")
    n.add_argument("--brief", default="")
    n.add_argument("--email", default="")
    n.add_argument("--currency", default="USD")
    n.add_argument("--ai", action="store_true")
    n.add_argument("--install", action="store_true")
    sub.add_parser("kinds")
    sub.add_parser("blueprints")
    li = sub.add_parser("list")
    sp = sub.add_parser("spec")
    sp.add_argument("build")
    sv = sub.add_parser("save")
    sv.add_argument("build")
    sv.add_argument("--spec", required=True)
    rn = sub.add_parser("render")
    rn.add_argument("build")
    rn.add_argument("--color", default="")
    pv = sub.add_parser("preview")
    pv.add_argument("build")
    a = ap.parse_args()
    if a.cmd == "kinds":
        for k, v in KINDS.items():
            print(f"{k:8} {v}")
        return 0
    if a.cmd == "blueprints":
        for k, v in BLUEPRINTS.items():
            print(f"{k:10} {v}")
        return 0
    if a.cmd == "list":
        return cmd_list()
    if a.cmd == "spec":
        return cmd_spec(a)
    if a.cmd == "save":
        return cmd_save(a)
    if a.cmd == "render":
        return cmd_render(a)
    if a.cmd == "preview":
        return cmd_preview(a)
    return cmd_new(a)


if __name__ == "__main__":
    sys.exit(main())
