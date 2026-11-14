"""The sandbox every Dev operation goes through: paths stay inside workspaces/, secrets stay out of reach, commands never go through a shell.

What it enforces:
  * workspace names are plain (a-z, 0-9, dot, dash, underscore) and live under workspaces/
  * a path inside a workspace is relative, never absolute, never leaves the workspace (symlinks are resolved first) and never touches .git
  * files that usually hold secrets (.env, private keys, tokens, credentials) cannot be read or written by the tools or the agent, so they
    never appear in a job log or get sent to an AI provider
  * commands run as an argument list (no shell), with a time limit, a capped output, and an environment WITHOUT your tokens
  * output is scrubbed for anything that looks like a token before it leaves this PC
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config

NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}$")
SECRET_FILE = re.compile(r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|credentials(\.json)?|\.npmrc|\.pypirc|\.netrc|secrets?(\.\w+)?|.*\.tfstate)$", re.I)
TOKEN = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|HQ_RUNNER_TOKEN=\S+)")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", "target", "bin", "obj", ".gradle", ".dart_tool", ".idea", ".next", ".devbench", ".expo"}
STRIP_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|APIKEY|CREDENTIAL|PRIVATE_KEY|^HQ_|^GH_|^GITHUB_|^ANTHROPIC_|^OPENAI_|^AWS_)", re.I)


class Refused(Exception):
    """An operation the sandbox or the settings do not allow. The message says why and what the person at the PC can do."""


def scrub(text: str) -> str:
    return TOKEN.sub("[token hidden]", text or "")


def workspace(name: str, must_exist: bool = True) -> Path:
    if not NAME.match(name or ""):
        raise Refused(f"'{name}' is not a workspace name: use lower-case letters, digits, dot, dash or underscore (up to 61 characters).")
    p = (config.WORKSPACES / name).resolve()
    if config.WORKSPACES.resolve() not in p.parents:
        raise Refused("That workspace is outside the workspaces folder.")
    if must_exist and not p.is_dir():
        have = ", ".join(sorted(x.name for x in config.WORKSPACES.iterdir() if x.is_dir())) if config.WORKSPACES.exists() else ""
        raise Refused(f"No workspace '{name}'. " + (f"You have: {have}." if have else "Make one first: dev new or dev clone."))
    return p


def resolve(ws: Path, rel: str, write: bool = False, allow_secret: bool = False) -> Path:
    """A path inside the workspace, or Refused."""
    rel = (rel or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or rel.startswith("~"):
        raise Refused("Use a path inside the workspace, like src/app.py (not an absolute path).")
    parts = [x for x in rel.split("/") if x not in ("", ".")]
    if ".." in parts:
        raise Refused("A path may not go up out of the workspace ('..').")
    if parts and parts[0].lower() == ".git":
        raise Refused("The .git folder is off limits: use the git operations instead.")
    target = (ws / "/".join(parts)).resolve()
    if ws.resolve() != target and ws.resolve() not in target.parents:
        raise Refused("That path leads outside the workspace (a link, perhaps). Refused.")
    if not allow_secret and SECRET_FILE.search("/".join(parts)):
        raise Refused("That file usually holds secrets (keys, tokens, .env). The dev tools never read or write those: open it yourself on this PC.")
    if write and not config.load()["allow_write"]:
        raise Refused("Editing is switched off. Turn it on at this PC: python dse.py dev config --set allow_write=true")
    return target


def clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not STRIP_ENV.search(k)}
    env.update({"GIT_TERMINAL_PROMPT": "0", "PYTHONIOENCODING": "utf-8", "CI": "1", "NO_COLOR": "1"})
    env.update(extra or {})
    return env


def run(argv: list[str], cwd: Path, timeout: int | None = None, extra_env: dict | None = None, input_text: str | None = None) -> tuple[int, str]:
    """Run a program (never a shell). Returns (exit code, scrubbed and capped output). A missing program is a clear message, not a crash."""
    cfg = config.load()
    timeout = min(timeout or cfg["timeout_s"], cfg["timeout_s"])
    exe = argv[0]
    found = shutil.which(exe)       # finds npm.cmd, mvn.cmd, gradle.bat on Windows without a shell
    if found:
        argv = [found, *argv[1:]]
    try:
        r = subprocess.run(argv, cwd=str(cwd), capture_output=True, timeout=timeout, env=clean_env(extra_env), stdin=subprocess.DEVNULL if input_text is None else None,
                           input=input_text.encode("utf-8") if input_text is not None else None)
        text = (r.stdout + r.stderr).decode("utf-8", "replace")
        code = r.returncode
    except FileNotFoundError:
        return 127, f"'{exe}' is not installed on this PC (or not on the PATH)."
    except subprocess.TimeoutExpired as e:
        text = ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", "replace") + f"\n[stopped after {timeout} seconds]"
        code = 124
    text = scrub(text)
    cap = cfg["max_output_chars"]
    if len(text) > cap:
        text = text[: cap // 3] + f"\n[... {len(text) - cap} characters left out ...]\n" + text[-(2 * cap // 3):]
    return code, text


def tree(ws: Path, rel: str = ".", depth: int = 3, limit: int = 400) -> list[str]:
    base = ws if rel in (".", "") else resolve(ws, rel)
    out: list[str] = []

    def walk(d: Path, level: int, prefix: str):
        if level > depth or len(out) >= limit:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if p.name in SKIP_DIRS or len(out) >= limit:
                continue
            relp = p.relative_to(ws).as_posix()
            if p.is_dir():
                out.append(f"{prefix}{p.name}/")
                walk(p, level + 1, prefix + "  ")
            else:
                hidden = " (secrets file: not shown)" if SECRET_FILE.search(relp) else ""
                out.append(f"{prefix}{p.name}  {p.stat().st_size} B{hidden}")

    walk(base, 1, "")
    return out
