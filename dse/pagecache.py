"""One download per web page, however many steps read it.

Finding, checking the website, detecting its technology and enriching it each used to download the same home page. A research run turns this cache on, so
every page is fetched once, kept on disk for a few days, and a second run on the same leads is mostly instant and does not hit the same sites again.

  with pagecache.active():          every pagecache.get(url) inside is cached (memory and data/page-cache/)
  pagecache.get(url)                a response with .status_code .text .url .headers; the plain requests.get when the cache is off

Off by default, so single commands behave exactly as before and tests that fake requests.get are unaffected.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import time
from pathlib import Path

import requests

from .common import DATA, UA

TTL_DAYS = 7
MAX_TEXT = 400_000
_state = {"on": False, "dir": None, "ttl": TTL_DAYS, "hits": 0, "misses": 0}
_mem: dict[str, "Page"] = {}
_lock = threading.Lock()


class Page:
    """What a cached download looks like: the same four things callers use from a requests response."""

    def __init__(self, status_code: int, text: str, url: str, headers: dict):
        self.status_code, self.text, self.url = status_code, text, url
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})


def _key(url: str) -> str:
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()[:24]


def _file(url: str) -> Path:
    return Path(_state["dir"]) / (_key(url) + ".json")


def stats() -> dict:
    return {"hits": _state["hits"], "misses": _state["misses"]}


@contextlib.contextmanager
def active(directory: str | Path | None = None, ttl_days: float = TTL_DAYS):
    """Turn the cache on for the code inside. Counts are reset; the in-memory part is dropped at the end, the files stay."""
    prev = dict(_state)
    d = Path(directory) if directory else DATA / "page-cache"
    d.mkdir(parents=True, exist_ok=True)
    _state.update(on=True, dir=d, ttl=ttl_days, hits=0, misses=0)
    try:
        yield d
    finally:
        _state.update(prev)
        _mem.clear()


def _load(url: str) -> Page | None:
    k = _key(url)
    with _lock:
        if k in _mem:
            return _mem[k]
    f = _file(url)
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - d.get("at", 0) > _state["ttl"] * 86400:
        return None
    p = Page(d["status"], d["text"], d["url"], d["headers"])
    with _lock:
        _mem[k] = p
    return p


def get(url: str, timeout: int = 15, **kw) -> Page | requests.Response:
    """requests.get, cached while a research run has the cache on. Network errors are raised as before and never cached."""
    if not _state["on"]:
        return requests.get(url, timeout=timeout, headers=kw.pop("headers", UA), allow_redirects=kw.pop("allow_redirects", True), **kw)
    hit = _load(url)
    if hit is not None:
        _state["hits"] += 1
        return hit
    r = requests.get(url, timeout=timeout, headers=UA, allow_redirects=True)
    _state["misses"] += 1
    if r.status_code >= 500 or r.status_code == 429:
        return r                                   # a temporary failure is not worth remembering
    ctype = r.headers.get("content-type", "text")
    text = r.text[:MAX_TEXT] if ("text" in ctype or "xml" in ctype or "json" in ctype) else ""
    p = Page(r.status_code, text, r.url, dict(r.headers))
    with _lock:
        _mem[_key(url)] = p
    try:
        _file(url).write_text(json.dumps({"at": time.time(), "status": p.status_code, "text": p.text, "url": p.url, "headers": dict(r.headers)}), encoding="utf-8")
    except OSError:
        pass
    return p
