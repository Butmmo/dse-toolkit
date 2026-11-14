"""Git operations inside a workspace, with the safety rules built in.

  * committing refuses to stage a file that looks like a secret (.env, keys, tokens): add it to .gitignore first
  * pushing needs allow_push, a repository owned by an account you listed (allowed_owners, or your own GitHub login), and never forces
  * a push from main or master goes to a NEW dev/... branch instead, unless you turned allow_push_default_branch on; you then open a pull request
  * pulls are fast-forward only, so they can never rewrite your work
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from . import config, github
from .sandbox import SECRET_FILE, Refused, run

DEFAULT_BRANCHES = {"main", "master"}


def git(ws: Path, *args: str, auth: bool = False, timeout: int | None = None) -> tuple[int, str]:
    extra = github.git_auth_env(github.find_token()) if auth else None
    return run(["git", *args], ws, timeout, extra)


def must_be_repo(ws: Path) -> None:
    if not (ws / ".git").exists():
        raise Refused(f"'{ws.name}' is not a git repository. Start one with: dev new (scaffolds include one) or clone a repository.")


def need(ws: Path, *args: str, auth: bool = False) -> str:
    code, out = git(ws, *args, auth=auth)
    if code != 0:
        raise Refused(f"git {args[0]} failed:\n{out.strip()}")
    return out


def current_branch(ws: Path) -> str:
    return need(ws, "rev-parse", "--abbrev-ref", "HEAD").strip()


def remote_owner(ws: Path) -> tuple[str, str]:
    code, url = git(ws, "remote", "get-url", "origin")
    parsed = github.parse_remote(url.strip()) if code == 0 else None
    if not parsed:
        raise Refused("This workspace has no GitHub remote called origin. Add one at this PC: git remote add origin https://github.com/OWNER/REPO.git")
    return parsed


def status(ws: Path) -> str:
    must_be_repo(ws)
    return need(ws, "status", "--short", "--branch").strip() or "Clean."


def diff(ws: Path, stat: bool = False) -> str:
    must_be_repo(ws)
    code, tracked = git(ws, "diff", "HEAD", *(["--stat"] if stat else []))
    code2, new = git(ws, "ls-files", "--others", "--exclude-standard")
    names = [n for n in new.splitlines() if n and not SECRET_FILE.search(n)]
    extra = ("\nNew files:\n" + "\n".join("  " + n for n in names[:60])) if names else ""
    return ((tracked.strip() if code == 0 else "") + extra).strip() or "No changes."


def log(ws: Path, n: int = 10) -> str:
    must_be_repo(ws)
    code, out = git(ws, "log", f"-{min(max(n, 1), 50)}", "--pretty=format:%h  %ad  %an  %s", "--date=short")
    return out.strip() if code == 0 and out.strip() else "No commits yet."


def init(ws: Path, message: str = "Initial commit") -> None:
    if not (ws / ".git").exists():
        need(ws, "init", "-b", "main")
    commit(ws, message, quiet=True)


def secrets_in_changes(ws: Path) -> list[str]:
    _c, a = git(ws, "ls-files", "--others", "--exclude-standard")
    _c, b = git(ws, "diff", "--name-only", "HEAD")
    return sorted({n for n in (a + "\n" + b).splitlines() if n and SECRET_FILE.search(n)})


def commit(ws: Path, message: str, quiet: bool = False) -> str:
    if not config.load()["allow_write"]:
        raise Refused("Editing is switched off at this PC (allow_write).")
    must_be_repo(ws)
    message = re.sub(r"[\r\n]+", " ", (message or "").strip())[:200]
    if len(message) < 3:
        raise Refused("Write a commit message of a few words.")
    bad = secrets_in_changes(ws)
    if bad:
        raise Refused("These files look like secrets and would be committed: " + ", ".join(bad) + ". Add them to .gitignore (or remove them), then try again. Nothing was committed.")
    need(ws, "add", "-A")
    code, out = git(ws, "-c", "user.name=" + _author(ws)[0], "-c", "user.email=" + _author(ws)[1], "commit", "-m", message)
    if code != 0:
        if "nothing to commit" in out or "nothing added" in out:
            return "Nothing to commit: no changes."
        raise Refused("git commit failed:\n" + out.strip())
    return out.strip().splitlines()[0] if not quiet else ""


def _author(ws: Path) -> tuple[str, str]:
    n = git(ws, "config", "user.name")[1].strip() or "DSE Toolkit"
    e = git(ws, "config", "user.email")[1].strip() or "dse-toolkit@users.noreply.github.com"
    return n, e


def new_branch(ws: Path, name: str) -> str:
    must_be_repo(ws)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,80}", name or "") or ".." in name or name.endswith("/") or name.endswith(".lock"):
        raise Refused("A branch name uses letters, digits, dot, dash, underscore and slash.")
    need(ws, "switch", "-c", name)
    return f"On new branch {name}."


def pull(ws: Path) -> str:
    must_be_repo(ws)
    return need(ws, "pull", "--ff-only", auth=True).strip()


def push(ws: Path, title: str = "") -> str:
    cfg = config.load()
    if not cfg["allow_push"]:
        raise Refused("Pushing to GitHub is switched off. Turn it on at this PC (it can never be turned on from Citadel): python dse.py dev setup --github-user YOUR-GITHUB-NAME")
    must_be_repo(ws)
    owner, repo = remote_owner(ws)
    me = github.whoami(github.find_token())
    allowed = set(cfg["allowed_owners"]) | ({me} if me else set())
    if owner.lower() not in allowed:
        raise Refused(f"This repository belongs to '{owner}', which is not on your allowed list ({', '.join(sorted(allowed)) or 'empty'}). Add it at this PC: python dse.py dev config --set allowed_owners={owner.lower()}")
    bad = secrets_in_changes(ws)
    if bad:
        raise Refused("Uncommitted files that look like secrets are in this workspace: " + ", ".join(bad) + ". Move them out or add them to .gitignore first.")
    branch = current_branch(ws)
    note = ""
    if branch in DEFAULT_BRANCHES and not cfg["allow_push_default_branch"]:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
        slug = re.sub(r"[^a-z0-9]+", "-", (title or ws.name).lower()).strip("-")[:30] or ws.name
        branch = f"dev/{slug}-{stamp}"
        need(ws, "switch", "-c", branch)
        note = f"You were on a main branch, so the work went to a new branch, {branch}, instead of straight to main.\n"
    out = need(ws, "push", "-u", "origin", branch, auth=True)      # never --force
    return (note + f"Pushed {owner}/{repo} branch {branch}.\n" + out.strip() + f"\nOpen a pull request: https://github.com/{owner}/{repo}/pull/new/{branch}").strip()


def clone(owner_repo: str, name: str = "") -> str:
    owner, repo = github.check_repo(owner_repo)
    config.WORKSPACES.mkdir(exist_ok=True)
    name = (name or repo.lower()).strip().lower()
    from .sandbox import workspace
    target = workspace(name, must_exist=False)
    if target.exists():
        raise Refused(f"A workspace called '{name}' already exists. Pick another name, or use it as it is.")
    code, out = run(["git", "clone", f"https://github.com/{owner}/{repo}.git", str(target)], config.WORKSPACES,
                    extra_env=github.git_auth_env(github.find_token()))
    if code != 0:
        raise Refused("Clone failed (a private repository needs your GitHub login: GITHUB_TOKEN or the GitHub CLI).\n" + out.strip()[-500:])
    return f"Cloned {owner}/{repo} into workspace '{name}'."
