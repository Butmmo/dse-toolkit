"""Dev workspace commands:  python dse.py dev <command> ...

  config [--set key=value]            what the dev tools may do on this PC (only you can change it here)
  setup --github-user NAME            allow pushes to NAME's repositories (turns pushing on)
  languages                           the languages you can start a project in
  workspaces                          your workspaces
  new "My App" --lang python-cli      start a project (add --official to use the language's own generator when installed)
  clone owner/repo [--name x]         copy a GitHub repository into a workspace
  repo owner/repo | issues owner/repo read GitHub facts (public repositories need no login)
  tree WS [path] | read WS path [--start N --end N] | search WS pattern [--glob *.py]
  write WS path --from-file F | replace WS path --old TEXT --new TEXT | delete WS path | patch WS --from-file F
  status WS | diff WS | log WS | branch WS name | commit WS -m "message" | pull WS | push WS | pr WS --title T [--body B] [--base main]
  run WS install|build|test|lint|script [--script NAME] [--eco node|python|...]
  shell WS -- <PowerShell command>     only when you turned allow_shell on
  agent WS --instruction "..." [--verify test]   an AI engineer edits the code on a new branch and commits it
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import agent, config, files, github, gitops, scaffold, shell, tasks
from .sandbox import Refused, resolve, scrub, tree, workspace


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="dse.py dev", description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 2)[2])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config"); c.add_argument("--set")
    s = sub.add_parser("setup"); s.add_argument("--github-user", required=True)
    sub.add_parser("languages")
    sub.add_parser("workspaces")
    n = sub.add_parser("new"); n.add_argument("name"); n.add_argument("--lang", required=True, choices=list(scaffold.LANGS)); n.add_argument("--official", action="store_true")
    cl = sub.add_parser("clone"); cl.add_argument("repo"); cl.add_argument("--name", default="")
    for k in ("repo", "issues"):
        x = sub.add_parser(k); x.add_argument("repo")
    t = sub.add_parser("tree"); t.add_argument("ws"); t.add_argument("path", nargs="?", default="."); t.add_argument("--depth", type=int, default=3)
    r = sub.add_parser("read"); r.add_argument("ws"); r.add_argument("path"); r.add_argument("--start", type=int, default=1); r.add_argument("--end", type=int, default=0)
    se = sub.add_parser("search"); se.add_argument("ws"); se.add_argument("pattern"); se.add_argument("--glob", default="")
    w = sub.add_parser("write"); w.add_argument("ws"); w.add_argument("path"); w.add_argument("--from-file", dest="from_file", required=True); w.add_argument("--no-overwrite", action="store_true")
    rp = sub.add_parser("replace"); rp.add_argument("ws"); rp.add_argument("path"); rp.add_argument("--old", required=True); rp.add_argument("--new", default="")
    d = sub.add_parser("delete"); d.add_argument("ws"); d.add_argument("path")
    pa = sub.add_parser("patch"); pa.add_argument("ws"); pa.add_argument("--from-file", dest="from_file", required=True)
    for k in ("status", "log", "pull", "push"):
        x = sub.add_parser(k); x.add_argument("ws")
    df = sub.add_parser("diff"); df.add_argument("ws"); df.add_argument("--stat", action="store_true")
    b = sub.add_parser("branch"); b.add_argument("ws"); b.add_argument("name")
    cm = sub.add_parser("commit"); cm.add_argument("ws"); cm.add_argument("-m", "--message", required=True)
    pr = sub.add_parser("pr"); pr.add_argument("ws"); pr.add_argument("--title", required=True); pr.add_argument("--body", default=""); pr.add_argument("--base", default="")
    ru = sub.add_parser("run"); ru.add_argument("ws"); ru.add_argument("task", choices=list(tasks.TASKS)); ru.add_argument("--script", default=""); ru.add_argument("--eco", default="")
    sh = sub.add_parser("shell"); sh.add_argument("ws"); sh.add_argument("command", nargs=argparse.REMAINDER)
    ag = sub.add_parser("agent"); ag.add_argument("ws"); ag.add_argument("--instruction", required=True); ag.add_argument("--verify", default="", choices=["", *tasks.TASKS]); ag.add_argument("--provider", default="", choices=["", "claude", "ollama"])
    a = ap.parse_args(argv)
    try:
        print(scrub(dispatch(a)))
        return 0
    except (Refused, ValueError) as e:
        print(scrub(str(e)))
        return 2


def dispatch(a) -> str:
    cmd = a.cmd
    if cmd == "config":
        if a.set:
            k, _, v = a.set.partition("=")
            config.set_value(k.strip(), v.strip())
        return config.describe()
    if cmd == "setup":
        cfg = config.load()
        cfg["allow_push"] = True
        cfg["allowed_owners"] = sorted(set(cfg["allowed_owners"]) | {a.github_user.strip().lower()})
        config.save(cfg)
        return config.describe(cfg) + "\n\nNow set your GitHub login on this PC (a fine-grained token limited to the repositories you need is best): setx GITHUB_TOKEN \"your-token\" , or sign in with the GitHub CLI."
    if cmd == "languages":
        return "\n".join(f"  {k:<12} {v}" for k, v in scaffold.LANGS.items())
    if cmd == "workspaces":
        config.WORKSPACES.mkdir(exist_ok=True)
        rows = []
        for p in sorted(x for x in config.WORKSPACES.iterdir() if x.is_dir()):
            eco = ", ".join(tasks.detect(p)) or "?"
            br = gitops.git(p, "rev-parse", "--abbrev-ref", "HEAD")[1].strip() if (p / ".git").exists() else "no git"
            rows.append(f"  {p.name:<28} {eco:<16} {br}")
        return "\n".join(rows) or "No workspaces yet. Start one: dev new \"My App\" --lang python-cli, or clone: dev clone owner/repo"
    if cmd == "new":
        return scaffold.new(a.name, a.lang, a.official)
    if cmd == "clone":
        return gitops.clone(a.repo, a.name)
    if cmd in ("repo", "issues"):
        o, r = github.check_repo(a.repo)
        tok = github.find_token()
        return github.repo_info(o, r, tok) if cmd == "repo" else github.issues(o, r, tok)
    ws = workspace(a.ws)
    if cmd == "tree":
        return "\n".join(tree(ws, a.path, a.depth)) or "(empty)"
    if cmd == "read":
        return files.read(ws, a.path, a.start, a.end)
    if cmd == "search":
        return files.search(ws, a.pattern, a.glob)
    if cmd == "write":
        return files.write(ws, a.path, Path(a.from_file).read_text(encoding="utf-8"), not a.no_overwrite)
    if cmd == "replace":
        return files.replace(ws, a.path, a.old, a.new)
    if cmd == "delete":
        return files.delete(ws, a.path)
    if cmd == "patch":
        return files.apply_patch(ws, Path(a.from_file).read_text(encoding="utf-8"))
    if cmd == "status":
        return gitops.status(ws)
    if cmd == "diff":
        return gitops.diff(ws, a.stat)
    if cmd == "log":
        return gitops.log(ws)
    if cmd == "branch":
        return gitops.new_branch(ws, a.name)
    if cmd == "commit":
        return gitops.commit(ws, a.message)
    if cmd == "pull":
        return gitops.pull(ws)
    if cmd == "push":
        return gitops.push(ws)
    if cmd == "pr":
        o, r = gitops.remote_owner(ws)
        head = gitops.current_branch(ws)
        base = a.base or "main"
        return github.create_pr(o, r, head, base, a.title, a.body, github.find_token())
    if cmd == "run":
        return tasks.run_task(ws, a.task, a.script, a.eco)
    if cmd == "shell":
        return shell.shell(ws, " ".join(x for x in a.command if x != "--"))
    if cmd == "agent":
        return agent.agent(ws, a.instruction, a.verify, a.provider)
    raise Refused(f"Unknown command {cmd}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
