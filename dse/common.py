"""Shared helpers for the DSE Toolkit: fetching pages (with a real browser when needed), CSV in/out."""
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]          # dse-toolkit/
LISTS = ROOT / "my-lists"
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (compatible; DSEToolkit/1.0; lead research)"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
JUNK_EMAIL = ("sentry", "wixpress", "example.", "domain.com", "email.com", "yourname", ".png", ".jpg", ".webp", ".svg")
DEAD_TEXT = ("domain is for sale", "buy this domain", "this domain isn't connected", "this domain is not connected",
             "account suspended", "domain is parked", "website is no longer available", "site not found",
             "may be for sale", "has expired and may be available", "domain has expired", "this domain has expired",
             "is available for purchase", "parked free", "hugedomains", "dan.com", "sedo.com/search", "afternic")
JS_BUILDERS = ("squarespace", "wix.com", "wixstatic", "showit", "webflow", "framer", "godaddy", "duda", "__next", "react-root")
EDGE_PATHS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url or " " in url or "." not in url:
        return ""
    return url if url.startswith("http") else "https://" + url


def domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(norm_url(url)).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def fetch(url: str, timeout: int = 15, tries: int = 2) -> tuple[int, str, str]:
    """(status, final url, html). Status 0 = no answer."""
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
            text = r.text if "text" in r.headers.get("content-type", "text") or "xml" in r.headers.get("content-type", "") else ""
            return r.status_code, r.url, text
        except Exception:
            if attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
    return 0, url, ""


def edge_path() -> str:
    return next((p for p in EDGE_PATHS if os.path.exists(p)), "")


def render_dom(url: str, timeout: int = 40) -> str:
    """The page's HTML after its JavaScript ran, from hidden Microsoft Edge ('' if Edge is missing or it fails).
    Squarespace, Wix, Showit and similar draw text and forms with JavaScript, so a plain download can't see them."""
    edge = edge_path()
    if not edge:
        return ""
    prof = tempfile.mkdtemp(prefix="dse-edge-")
    try:
        r = subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                            "--virtual-time-budget=8000", f"--user-data-dir={prof}", "--dump-dom", url],
                           capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*"
              + os.path.basename(prof) + "*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30)
        return ""
    finally:
        time.sleep(0.5)
        shutil.rmtree(prof, ignore_errors=True)


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows: list[dict], first: list[str] | None = None):
    cols: list[str] = list(first or [])
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:n] or "list"


def out_path(*parts: str) -> Path:
    LISTS.mkdir(exist_ok=True)
    return LISTS / (time.strftime("%Y-%m-%d") + "-" + "-".join(slug(p, 30) for p in parts if p) + ".csv")


def contacts_from(html: str) -> dict:
    """Emails, phones, Instagram and Facebook found in a page."""
    out = {"email": "", "phone": "", "instagram": "", "facebook": ""}
    low = urllib.parse.unquote(html)
    for e in EMAIL.findall(low):
        e = e.lower().strip(".")
        if not any(j in e for j in JUNK_EMAIL):
            out["email"] = e
            break
    m = PHONE.search(re.sub(r"<[^>]+>", " ", html))
    if m:
        out["phone"] = re.sub(r"\s+", " ", m.group(0)).strip()
    m = re.search(r"instagram\.com/(?!p/|reel|explore|accounts|stories)([A-Za-z0-9._]{2,30})", html)
    if m:
        out["instagram"] = "https://instagram.com/" + m.group(1)
    m = re.search(r"facebook\.com/(pages/[^\"'<>\s?#]{3,120}|profile\.php\?id=\d+|(?!sharer|tr\?|plugins|dialog|pages|share|login|events|groups)[A-Za-z0-9._-]{3,60})", html)
    if m:
        out["facebook"] = "https://facebook.com/" + m.group(1).rstrip("/")
    return out
