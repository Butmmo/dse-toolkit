"""One-off generator: adds the Dev tools (group "Dev") to catalog.json. Safe to re-run (it replaces the dev.* entries)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dev import scaffold  # noqa: E402

p = ROOT / "bridge" / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dev.")]:
    del T[k]

WS = {"name": "ws", "label": "Workspace", "type": "choice", "required": True, "choices_from": "workspaces", "choices": []}
SAFE = r"^[A-Za-z0-9][A-Za-z0-9 ,.'&/()!:_#-]{2,99}$"


def txt(name, label, mx=200, pat=None, req=True):
    f = {"name": name, "label": label, "type": "text", "required": req, "max": mx}
    if pat:
        f["pattern"] = pat
    return f


PATH = txt("path", "File path inside the workspace (like src/app.py)", 200, r"^[A-Za-z0-9_][A-Za-z0-9_./ -]{0,199}$")
REPO = txt("repo", "GitHub repository (owner/name)", 100, r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
LANGS = [{"value": k, "label": v} for k, v in scaffold.LANGS.items()]
TASKS = [{"value": x, "label": x} for x in ("install", "build", "test", "lint", "script")]


def tool(label, help_, args, fields, tmo=10):
    return {"label": label, "group": "Dev", "help": help_, "script": "dse.py", "args": [{"lit": "dev"}] + args, "fields": fields, "timeout_min": tmo, "outputs": []}


def F(n):
    return {"field": n}


T["dev.config"] = tool("Dev: what is allowed on this PC", "Shows what the dev tools may do here (editing, tasks, pushing to GitHub, PowerShell). These switches can only be changed at the PC itself, never from here.", [{"lit": "config"}], [], 1)
T["dev.workspaces"] = tool("Dev: my workspaces", "Lists your workspaces (project folders on this PC), what kind of project each is and which git branch it is on.", [{"lit": "workspaces"}], [], 1)
T["dev.new"] = tool("Dev: start a new project", "Creates a project folder with starter code, a test and git, in one of 14 starters: JavaScript, TypeScript, Python (command line or web API), Java, Kotlin, C#, C, C++, Dart, Flutter, Go, Rust, PowerShell. Tick the last box to use the language's own generator when it is installed.",
                    [{"lit": "new"}, F("name"), {"opt": "--lang", "field": "lang"}, {"flag": "--official", "field": "official"}],
                    [txt("name", "Project name", 60, r"^[A-Za-z0-9][A-Za-z0-9 _-]{1,59}$"), {"name": "lang", "label": "Language", "type": "choice", "required": True, "choices": LANGS},
                     {"name": "official", "label": "Use the language's own generator if installed", "type": "bool", "default": False}], 3)
T["dev.clone"] = tool("Dev: copy a GitHub repository here", "Copies a repository from GitHub into a workspace so you can read and change it. Public repositories need no login; private ones use the GitHub login on this PC.", [{"lit": "clone"}, F("repo")], [REPO], 10)
T["dev.repo"] = tool("Dev: look at a GitHub repository", "Reads a repository's description, language, stars and default branch from GitHub.", [{"lit": "repo"}, F("repo")], [REPO], 2)
T["dev.issues"] = tool("Dev: open issues of a GitHub repository", "Lists the latest open issues and pull requests.", [{"lit": "issues"}, F("repo")], [REPO], 2)
T["dev.tree"] = tool("Dev: show the files", "Lists the files and folders of a workspace.", [{"lit": "tree"}, F("ws")], [WS], 1)
T["dev.read"] = tool("Dev: read a file", "Shows a file with line numbers. Files that hold secrets (.env, keys) are never shown.", [{"lit": "read"}, F("ws"), F("path")], [WS, PATH], 1)
T["dev.search"] = tool("Dev: search the code", "Finds lines matching a word or pattern in every file of the workspace.", [{"lit": "search"}, F("ws"), F("pattern")], [WS, txt("pattern", "Word or pattern to find", 100)], 1)
T["dev.replace"] = tool("Dev: change a line of code", "Replaces text in a file. The old text must match exactly once. For bigger changes use Dev: let the AI make a change.",
                        [{"lit": "replace"}, F("ws"), F("path"), {"opt": "--old", "field": "old"}, {"opt": "--new", "field": "new"}],
                        [WS, PATH, txt("old", "Exact text to replace", 300), txt("new", "New text", 300, req=False)], 1)
T["dev.run"] = tool("Dev: install, build, test or lint", "Runs the project's own install, build, test or lint step (npm, pip, Maven, Gradle, dotnet, CMake, Dart, Flutter, Cargo, Go). If a tool is missing it tells you the one command that installs it.",
                    [{"lit": "run"}, F("ws"), F("task"), {"opt": "--script", "field": "script"}],
                    [WS, {"name": "task", "label": "What to run", "type": "choice", "required": True, "choices": TASKS}, txt("script", "npm script name (only for 'script')", 40, r"^[A-Za-z0-9:_-]{1,40}$", req=False)], 15)
T["dev.status"] = tool("Dev: what changed (git status)", "Shows the branch and which files changed.", [{"lit": "status"}, F("ws")], [WS], 1)
T["dev.diff"] = tool("Dev: show the changes (git diff)", "Shows exactly what changed since the last commit.", [{"lit": "diff"}, F("ws")], [WS], 1)
T["dev.branch"] = tool("Dev: start a branch", "Creates and switches to a new git branch.", [{"lit": "branch"}, F("ws"), F("name")], [WS, txt("name", "Branch name", 60, r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,59}$")], 1)
T["dev.commit"] = tool("Dev: save a commit", "Saves the current changes as a commit. Refuses if a file that looks like a secret would be included.", [{"lit": "commit"}, F("ws"), {"opt": "-m", "field": "message"}], [WS, txt("message", "Commit message", 100, SAFE)], 1)
T["dev.pull"] = tool("Dev: update from GitHub (pull)", "Brings in new commits from GitHub (fast-forward only, it can never rewrite your work).", [{"lit": "pull"}, F("ws")], [WS], 5)
T["dev.push"] = tool("Dev: push to GitHub", "Pushes the current branch to GitHub. Works only when you switched pushing on at this PC and the repository belongs to an account you allowed. From main it pushes a new dev/ branch instead; it never forces.", [{"lit": "push"}, F("ws")], [WS], 5)
T["dev.pr"] = tool("Dev: open a pull request", "Opens a pull request on GitHub for the current branch (same permission as pushing, and your GitHub login on this PC).",
                   [{"lit": "pr"}, F("ws"), {"opt": "--title", "field": "title"}, {"opt": "--body", "field": "body"}, {"opt": "--base", "field": "base"}],
                   [WS, txt("title", "Title", 100, SAFE), txt("body", "Description (optional)", 300, req=False), txt("base", "Merge into branch (default main)", 40, r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$", req=False)], 3)
T["dev.agent"] = tool("Dev: let the AI make a change", "An AI engineer reads the project, edits the files, runs the tests and saves the result on a NEW branch (dev/agent-...). It cannot leave the workspace, read secrets, run a shell or push. You read the diff, then push yourself. Uses Claude when ANTHROPIC_API_KEY is set on this PC, otherwise your local Ollama model.",
                      [{"lit": "agent"}, F("ws"), {"opt": "--instruction", "field": "instruction"}, {"opt": "--verify", "field": "verify"}],
                      [WS, txt("instruction", "What should change? (one or two sentences)", 300),
                       {"name": "verify", "label": "Check afterwards", "type": "choice", "required": False, "choices": [{"value": "test", "label": "Run the tests"}, {"value": "build", "label": "Build"}, {"value": "lint", "label": "Lint"}]}], 30)
T["dev.shell"] = tool("Dev: run a PowerShell command", "Runs one PowerShell command inside a workspace. OFF unless you turned it on at this PC (allow_shell). Dangerous commands are refused, but this is not a sandbox: switch it on only if you accept that.", [{"lit": "shell"}, F("ws"), F("command")], [WS, txt("command", "PowerShell command", 300)], 10)

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dev.")]), "dev tools,", len(T), "tools in all")
