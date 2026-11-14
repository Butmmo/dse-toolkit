"""GitHub: read repository facts, issues and pull requests through the REST API (standard library only).

Your token is found in this order, and is used but never printed, logged or sent to Citadel:
  1. the GITHUB_TOKEN or GH_TOKEN environment variable (set it yourself on this PC; a fine-grained token limited to the repositories you need is best)
  2. `gh auth token`, if the GitHub CLI is installed and signed in
  3. Git's own credential store (Git Credential Manager on Windows), the same login your normal git push uses
Public repositories need no token for reading.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from .sandbox import Refused, scrub

API = "https://api.github.com"
OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def parse_remote(url: str) -> tuple[str, str] | None:
    m = re.match(r"^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", (url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def check_repo(owner_repo: str) -> tuple[str, str]:
    m = re.match(r"^(?:https?://github\.com/)?([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", (owner_repo or "").strip())
    if not m or not OWNER.match(m.group(1)) or not REPO.match(m.group(2)) or m.group(2) in (".", ".."):
        raise Refused("Write the repository as owner/name, for example Butmmo/dse-toolkit.")
    return m.group(1), m.group(2)


def find_token() -> str:
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k].strip()
    for cmd, inp in ((["gh", "auth", "token"], None), (["git", "credential", "fill"], "protocol=https\nhost=github.com\n\n")):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=15, input=inp.encode() if inp else None, stdin=None if inp else subprocess.DEVNULL,
                               env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        out = r.stdout.decode("utf-8", "replace")
        if r.returncode == 0:
            if cmd[0] == "gh" and out.strip():
                return out.strip()
            m = re.search(r"^password=(.+)$", out, re.M)
            if m:
                return m.group(1).strip()
    return ""


def git_auth_env(token: str) -> dict:
    """Lets one git command authenticate to github.com without writing the token anywhere."""
    if not token:
        return {}
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"}


def api(path: str, token: str = "", method: str = "GET", body: dict | None = None) -> dict | list:
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "dse-toolkit-dev", "X-GitHub-Api-Version": "2022-11-28",
                                          **({"Authorization": f"Bearer {token}"} if token else {}), **({"Content-Type": "application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = scrub(e.read().decode("utf-8", "replace"))[:300]
        hint = {401: " (the token was refused)", 403: " (not allowed, or rate limited: set GITHUB_TOKEN)", 404: " (not found, or private and the token cannot see it)", 422: " (GitHub rejected the request)"}.get(e.code, "")
        raise Refused(f"GitHub said HTTP {e.code}{hint}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Refused(f"Could not reach GitHub: {e}") from None


def whoami(token: str) -> str:
    if not token:
        return ""
    try:
        return str(api("/user", token).get("login", "")).lower()           # type: ignore[union-attr]
    except Refused:
        return ""


def repo_info(owner: str, repo: str, token: str = "") -> str:
    r = api(f"/repos/{owner}/{repo}", token)
    assert isinstance(r, dict)
    return (f"{r['full_name']}: {r.get('description') or 'no description'}\n"
            f"  {'private' if r.get('private') else 'public'} - default branch {r.get('default_branch')} - language {r.get('language') or '?'} - "
            f"{r.get('stargazers_count', 0)} stars - {r.get('open_issues_count', 0)} open issues/PRs - last push {str(r.get('pushed_at', ''))[:10]}\n  {r.get('html_url')}")


def issues(owner: str, repo: str, token: str = "", state: str = "open", n: int = 15) -> str:
    rows = api(f"/repos/{owner}/{repo}/issues?state={state}&per_page={min(n, 50)}", token)
    assert isinstance(rows, list)
    if not rows:
        return f"No {state} issues or pull requests."
    return "\n".join(f"#{x['number']:<5} {'PR ' if 'pull_request' in x else 'issue'} {x['title'][:80]}  ({x['user']['login']}, {str(x['updated_at'])[:10]})" for x in rows)


def create_pr(owner: str, repo: str, head: str, base: str, title: str, body: str, token: str) -> str:
    if not token:
        raise Refused("Opening a pull request needs your GitHub login. Set GITHUB_TOKEN (a fine-grained token with 'Pull requests: write' on this repository) or sign in with the GitHub CLI (gh auth login).")
    r = api(f"/repos/{owner}/{repo}/pulls", token, "POST", {"title": title, "head": head, "base": base, "body": body, "draft": False})
    assert isinstance(r, dict)
    return f"Pull request opened: {r.get('html_url')}"
