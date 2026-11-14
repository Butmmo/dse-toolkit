"""Dev workspace settings: what the Dev tools may do on THIS PC. Only a person at this PC can change them.

The settings live in dev/dev.config.json (not in Git, not in Citadel). DBI Citadel can only ask for a named operation; it can never
switch a permission on. That is the whole point: if someone ever got into a Citadel account, they still could not push code or run a
shell on your PC unless you had turned that on here yourself.

    python dse.py dev config                    show the current settings
    python dse.py dev setup --github-user NAME  allow pushes to repositories owned by NAME (and turn pushing on)
    python dse.py dev config --set allow_shell=true     (edit dev/dev.config.json by hand works too)

Settings (defaults in brackets):
  allow_write [true]      the tools and the agent may create and edit files inside workspaces/
  allow_run [true]        run the named tasks: install, build, test, lint (git, npm, pip, mvn, gradle, dotnet, cmake, flutter, dart, cargo, go ...)
  npm_scripts [false]     let 'npm install' run packages' install scripts (off: --ignore-scripts, the safe default for code you did not write)
  allow_push [false]      commit and push to GitHub
  allowed_owners []       the only GitHub accounts or organisations you may push to (lower case)
  allow_push_default_branch [false]   push straight to main or master (off: pushes a new dev/... branch and you open a pull request)
  allow_shell [false]     run a PowerShell command inside a workspace (a deny list blocks the worst, but it is NOT a sandbox: turn on only if you accept that)
  timeout_s [600]         longest any one operation may run
  max_output_chars [20000]  how much output is returned to Citadel
  agent_max_steps [30]    most tool calls one agent run may make
"""
from __future__ import annotations

import json
from pathlib import Path

from dse.common import ROOT

CONFIG = ROOT / "dev" / "dev.config.json"
WORKSPACES = ROOT / "workspaces"
DEFAULTS = {
    "allow_write": True, "allow_run": True, "npm_scripts": False, "allow_push": False, "allowed_owners": [],
    "allow_push_default_branch": False, "allow_shell": False, "timeout_s": 600, "max_output_chars": 20000, "agent_max_steps": 30,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        try:
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except ValueError:
            pass
    cfg["allowed_owners"] = [str(o).lower() for o in cfg.get("allowed_owners", [])]
    return cfg


def save(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, indent=2) + "\n", encoding="utf-8")


def set_value(key: str, raw: str) -> dict:
    if key not in DEFAULTS:
        raise ValueError(f"Unknown setting '{key}'. Settings: {', '.join(DEFAULTS)}")
    cfg = load()
    d = DEFAULTS[key]
    if isinstance(d, bool):
        if raw.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError(f"{key} is true or false")
        cfg[key] = raw.lower() in ("true", "1", "yes")
    elif isinstance(d, int):
        cfg[key] = int(raw)
    else:
        cfg[key] = [x.strip().lower() for x in raw.split(",") if x.strip()]
    save(cfg)
    return cfg


def describe(cfg: dict | None = None) -> str:
    cfg = cfg or load()
    on = lambda b: "ON " if b else "off"  # noqa: E731
    return "\n".join([
        f"Settings file: {CONFIG}  (only you can change it, at this PC)",
        f"  files:    write/edit inside workspaces/ ..... {on(cfg['allow_write'])}",
        f"  tasks:    install, build, test, lint ........ {on(cfg['allow_run'])}   (npm install scripts: {on(cfg['npm_scripts'])})",
        f"  GitHub:   commit and push ................... {on(cfg['allow_push'])}   allowed accounts: {', '.join(cfg['allowed_owners']) or 'none set'}",
        f"            push straight to main/master ...... {on(cfg['allow_push_default_branch'])}",
        f"  PowerShell: run a command in a workspace .... {on(cfg['allow_shell'])}",
        f"  limits:   {cfg['timeout_s']} s per operation, {cfg['agent_max_steps']} agent steps, {cfg['max_output_chars']} characters of output",
    ])
