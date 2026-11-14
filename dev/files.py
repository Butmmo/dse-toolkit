"""Read, search and edit files inside a workspace. Every path goes through the sandbox; every edit is exact and reversible (git).

Editing is deliberately exact: 'replace' needs the old text to appear exactly once, so a change can never land in the wrong place by luck.
Nothing here can touch .git or a secrets file, and all writes need allow_write.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import config
from .sandbox import SECRET_FILE, SKIP_DIRS, Refused, resolve

MAX_READ = 200_000
MAX_WRITE = 400_000
BINARY = re.compile(rb"[\x00]")


def read(ws: Path, rel: str, start: int = 1, end: int = 0) -> str:
    p = resolve(ws, rel)
    if not p.is_file():
        raise Refused(f"No file '{rel}' in this workspace.")
    raw = p.read_bytes()
    if BINARY.search(raw[:4000]):
        return f"'{rel}' is a binary file ({len(raw)} bytes): not shown."
    lines = raw[:MAX_READ].decode("utf-8", "replace").splitlines()
    total = len(lines)
    lo, hi = max(1, start), (min(end, total) if end else min(total, lo_hi(start, total)))
    body = "\n".join(f"{i:>5}  {lines[i - 1]}" for i in range(lo, hi + 1))
    more = f"\n[showing lines {lo}-{hi} of {total}; ask for more with a start and end line]" if hi < total or lo > 1 else ""
    return f"{rel}  ({total} lines)\n{body}{more}"


def lo_hi(start: int, total: int) -> int:
    return start + 399          # 400 lines at a time keeps results readable


def search(ws: Path, pattern: str, glob: str = "", limit: int = 60) -> str:
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        raise Refused(f"That is not a valid search pattern: {e}") from None
    hits: list[str] = []
    for p in sorted(ws.rglob("*")):
        if len(hits) >= limit:
            break
        rel = p.relative_to(ws).as_posix()
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(ws).parts) or SECRET_FILE.search(rel):
            continue
        if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(p.name, glob):
            continue
        try:
            raw = p.read_bytes()[:MAX_READ]
        except OSError:
            continue
        if BINARY.search(raw[:2000]):
            continue
        for i, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                if len(hits) >= limit:
                    break
    return "\n".join(hits) + (f"\n[stopped at {limit} matches]" if len(hits) >= limit else "") if hits else "No matches."


def write(ws: Path, rel: str, content: str, overwrite: bool = True) -> str:
    p = resolve(ws, rel, write=True)
    if len(content.encode("utf-8")) > MAX_WRITE:
        raise Refused(f"That file is larger than {MAX_WRITE // 1000} KB. Split it.")
    if p.exists() and not overwrite:
        raise Refused(f"'{rel}' already exists.")
    if p.is_dir():
        raise Refused(f"'{rel}' is a folder.")
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    return f"{'Updated' if existed else 'Created'} {rel} ({content.count(chr(10)) + 1} lines)."


def replace(ws: Path, rel: str, old: str, new: str) -> str:
    p = resolve(ws, rel, write=True)
    if not p.is_file():
        raise Refused(f"No file '{rel}' in this workspace.")
    text = p.read_text(encoding="utf-8", errors="replace")
    n = text.count(old)
    if not old:
        raise Refused("Say which text to replace.")
    if n == 0:
        raise Refused(f"The text to replace was not found in {rel}. Read the file again and copy the exact text.")
    if n > 1:
        raise Refused(f"The text appears {n} times in {rel}. Include more surrounding text so it matches exactly once.")
    p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    return f"Changed {rel}: replaced {old.count(chr(10)) + 1} line(s) with {new.count(chr(10)) + 1}."


def delete(ws: Path, rel: str) -> str:
    p = resolve(ws, rel, write=True)
    if not p.is_file():
        raise Refused(f"No file '{rel}' to delete (only single files can be deleted).")
    p.unlink()
    return f"Deleted {rel} (it is still in git history if it was committed)."


def apply_patch(ws: Path, patch: str) -> str:
    """Apply a unified diff with git, after checking every path it touches is allowed."""
    from .gitops import git
    if not config.load()["allow_write"]:
        raise Refused("Editing is switched off at this PC (allow_write).")
    for m in re.finditer(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", patch, re.M):
        if m.group(1) != "/dev/null":
            resolve(ws, m.group(1), write=True)
    from .sandbox import run
    code, out = run(["git", "apply", "--whitespace=nowarn", "-"], ws, input_text=patch)
    if code != 0:
        raise Refused("The patch does not apply cleanly:\n" + out.strip())
    return "Patch applied."
