"""dse_sdk: the only door a Tool Studio tool has to your files and the web. The launcher (studio_run.py) configures it, then the tool imports it:

    from dse_sdk import inputs, log, read_csv, write_csv, read_text, write_text, http_get

Limits (applied here, not left to the tool): reads only from engines/, my-lists/, data/ and the tool's own work folder, never a file that looks like a
secret; writes only csv, json, txt or md files into the tool's own work folder (at most 20 files of 5 MB); web requests only to http(s) addresses on the
public internet (never your own network), never to LinkedIn, Instagram, Facebook, X, TikTok, Reddit or Google Maps (the toolkit never scrapes them), at most
30 requests of 2 MB each, redirects re-checked. Pure standard library, no relative imports.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, urlencode, urljoin, urlparse  # noqa: F401 (re-exported to tools)

inputs: dict = {}
_cfg = {"root": None, "work": None, "writes": 0, "requests": 0}

READ_ROOTS = ("engines", "my-lists", "data")
WRITE_EXT = (".csv", ".json", ".txt", ".md")
MAX_FILE = 5 * 1024 * 1024
MAX_FILES = 20
MAX_BODY = 2 * 1024 * 1024
MAX_REQUESTS = 30
SECRETISH = re.compile(r"(^\.|\.env|token|secret|password|passwd|credential|private|\.pem$|\.key$|id_rsa|api[-_]?key)", re.I)
BLOCKED_HOSTS = ("linkedin.com", "instagram.com", "facebook.com", "fb.com", "x.com", "twitter.com", "tiktok.com", "reddit.com", "maps.google.", "google.com/maps")
UA = "Mozilla/5.0 (compatible; DSEToolkit-Studio/1.0)"


def configure(root: str, work: str, values: dict) -> None:
    global inputs
    _cfg.update(root=Path(root).resolve(), work=Path(work).resolve(), writes=0, requests=0)
    _cfg["work"].mkdir(parents=True, exist_ok=True)
    inputs = dict(values)
    globals()["inputs"] = inputs


def log(*a) -> None:
    print(*a, flush=True)


def _readable(rel: str) -> Path:
    rel = str(rel).replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/") or ":" in rel:
        raise ValueError(f"not a path inside this toolkit: {rel}")
    p = (_cfg["root"] / rel).resolve()
    work = _cfg["work"]
    ok = work in p.parents or any(_cfg["root"] / r in p.parents for r in READ_ROOTS)
    if not ok:
        raise ValueError(f"tools may read only from {', '.join(READ_ROOTS)} and their own work folder: {rel}")
    if any(SECRETISH.search(part) for part in p.relative_to(_cfg["root"]).parts):
        raise ValueError(f"that file looks like a secret and cannot be read: {rel}")
    if not p.is_file():
        raise ValueError(f"no such file: {rel}")
    if p.stat().st_size > 20 * MAX_FILE:
        raise ValueError(f"file too big to read: {rel}")
    return p


def read_text(rel: str) -> str:
    return _readable(rel).read_text(encoding="utf-8-sig", errors="replace")


def read_csv(rel: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(read_text(rel))))


def _writable(name: str) -> Path:
    name = str(name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name) or not name.lower().endswith(WRITE_EXT):
        raise ValueError(f"a result file needs a plain name ending in {', '.join(WRITE_EXT)}: {name}")
    p = _cfg["work"] / name
    if not p.exists():
        if _cfg["writes"] >= MAX_FILES:
            raise ValueError(f"a tool may write at most {MAX_FILES} files per run")
        _cfg["writes"] += 1
    return p


def write_text(name: str, text: str) -> str:
    p = _writable(name)
    data = str(text).encode("utf-8")
    if len(data) > MAX_FILE:
        raise ValueError("result file too big")
    p.write_bytes(data)
    return p.name


def write_csv(name: str, rows: list) -> str:
    rows = [dict(r) for r in rows]
    cols = list(dict.fromkeys(k for r in rows for k in r))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return write_text(name, buf.getvalue())


def _public(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("only http and https addresses are allowed")
    host = u.hostname.lower()
    full = host + (u.path or "")
    if any(b in full or host == b or host.endswith("." + b) for b in BLOCKED_HOSTS):
        raise ValueError(f"{host} is never fetched by the toolkit (it breaks that site's terms and risks your accounts)")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise ValueError(f"could not look up {host}: {e}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError(f"{host} is not on the public internet")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def http_get(url: str, timeout: int = 20) -> tuple[int, str]:
    """(status, text) of a public web page. Redirects are followed up to 3 times and every hop is checked again."""
    if _cfg["requests"] >= MAX_REQUESTS:
        raise ValueError(f"a tool may make at most {MAX_REQUESTS} web requests per run")
    _cfg["requests"] += 1
    opener = urllib.request.build_opener(_NoRedirect)
    cur = url
    for _ in range(4):
        _public(cur)
        req = urllib.request.Request(cur, headers={"User-Agent": UA, "Accept-Language": "en"})
        try:
            with opener.open(req, timeout=min(int(timeout), 30)) as r:
                return r.status, r.read(MAX_BODY).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                cur = urllib.parse.urljoin(cur, e.headers["Location"])
                continue
            return e.code, ""
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, ""
    return 0, ""


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
