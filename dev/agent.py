"""The coding agent: describe a change in words, it reads the code, edits files, runs the tests and commits the result to a NEW branch.

    python dse.py dev agent <workspace> --instruction "add a /version endpoint that returns the package version, with a test" --verify test

Safety, all enforced in code (not by asking the model nicely):
  * it works only through the same sandboxed tools as the rest of dev: read, search, write, exact replace, delete, run a NAMED task, diff.
    It has no shell, cannot leave the workspace, cannot touch .git, and cannot read or write secrets files
  * it refuses to start on a workspace with uncommitted changes, and works on a fresh branch (dev/agent-<time>), so undoing it is one command
  * every tool call is limited to your settings (allow_write, allow_run) and the step limit (agent_max_steps)
  * it never pushes. You look at the diff, then push yourself (dev push), which has its own guards
Brain: Claude (claude-opus-5-5) when ANTHROPIC_API_KEY is set and `pip install anthropic` is done: much the strongest. Otherwise your local Ollama model
(OLLAMA_MODEL; use gemma3:4b or bigger: the 1b model cannot edit code reliably). What leaves this PC with Claude: the instruction, the file listing and
the files it chooses to read in this workspace (never secrets files, which the sandbox hides).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

from . import config, files, gitops, tasks
from .sandbox import Refused, scrub, tree

CLAUDE_MODEL = os.environ.get("HQ_DEV_CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
RESULT_CAP = 6000

TOOLS = [
    {"name": "list_files", "description": "List files and folders in the workspace (or a subfolder), 3 levels deep.", "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "subfolder, or . for the top"}}, "required": []}},
    {"name": "read_file", "description": "Read a text file with line numbers. Use start and end to read part of a long file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "search", "description": "Search every file for a regular expression (case-insensitive). Optional glob like *.py.", "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "write_file", "description": "Create a file, or replace a whole file, with the given complete content.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "replace_in_file", "description": "Replace text in a file. 'old' must match exactly once (include enough surrounding lines). Prefer this over rewriting a whole file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "delete_file", "description": "Delete one file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "run_task", "description": "Run a named task for the project: install, build, test or lint (or script with a package.json script name). Use test to check your work.", "input_schema": {"type": "object", "properties": {"task": {"type": "string", "enum": ["install", "build", "test", "lint", "script"]}, "script": {"type": "string"}}, "required": ["task"]}},
    {"name": "git_diff", "description": "Show what has changed so far.", "input_schema": {"type": "object", "properties": {}, "required": []}},
]
SYSTEM = ("You are a careful senior software engineer working in a sandboxed project folder. You can only use the tools provided. "
          "Work like this: read the relevant code first; make the smallest change that does the job and fits the project's style; add or update a test for new behaviour; "
          "run the tests with run_task and fix what you broke; finish with a short plain summary of what you changed and anything the person should check. "
          "Never invent file contents you have not read. Never try to read secrets (.env, keys). If the request is unclear or risky, do the safe part and say what is left. "
          "Do not use the long dash character in anything you write.")


class Session:
    """Executes the model's tool calls inside the sandbox and counts them."""

    def __init__(self, ws: Path, cfg: dict):
        self.ws, self.cfg, self.steps, self.log = ws, cfg, 0, []

    def call(self, name: str, a: dict) -> tuple[str, bool]:
        self.steps += 1
        if self.steps > self.cfg["agent_max_steps"]:
            return f"Step limit reached ({self.cfg['agent_max_steps']}). Finish now with a summary.", True
        try:
            if name == "list_files":
                out = "\n".join(tree(self.ws, a.get("path") or ".")) or "(empty)"
            elif name == "read_file":
                out = files.read(self.ws, a["path"], int(a.get("start") or 1), int(a.get("end") or 0))
            elif name == "search":
                out = files.search(self.ws, a["pattern"], a.get("glob") or "")
            elif name == "write_file":
                out = files.write(self.ws, a["path"], a["content"])
            elif name == "replace_in_file":
                out = files.replace(self.ws, a["path"], a["old"], a["new"])
            elif name == "delete_file":
                out = files.delete(self.ws, a["path"])
            elif name == "run_task":
                out = tasks.run_task(self.ws, a.get("task", ""), a.get("script", ""))
            elif name == "git_diff":
                out = gitops.diff(self.ws, stat=False)
            else:
                return f"Unknown tool '{name}'.", True
            self.log.append(f"{name}({', '.join(f'{k}={str(v)[:40]!r}' for k, v in a.items() if k != 'content')})")
            return scrub(out)[:RESULT_CAP], False
        except Refused as e:
            self.log.append(f"{name} refused: {str(e)[:80]}")
            return str(e), True
        except (KeyError, TypeError, ValueError) as e:
            return f"Bad arguments for {name}: {e}", True


def prompt(ws: Path, instruction: str) -> str:
    eco = ", ".join(tasks.detect(ws)) or "unknown"
    scripts = tasks.npm_scripts(ws) if "node" in tasks.detect(ws) else {}
    return (f"Project folder: {ws.name}\nDetected: {eco}" + (f"\npackage.json scripts: {', '.join(scripts)}" if scripts else "")
            + "\n\nFiles:\n" + "\n".join(tree(ws, ".", depth=2, limit=120)) + f"\n\nTask:\n{instruction}")


def run_claude(sess: Session, text: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    messages: list = [{"role": "user", "content": text}]
    final = ""
    for _ in range(sess.cfg["agent_max_steps"] + 2):
        resp = client.beta.messages.create(model=CLAUDE_MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages, output_config={"effort": "high"},
                                           betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        if resp.stop_reason == "refusal":
            return final or "The model declined this request."
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        final = "".join(b.text for b in resp.content if b.type == "text").strip() or final
        if not uses:
            return final
        results = []
        for b in uses:
            out, err = sess.call(b.name, dict(b.input))
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, **({"is_error": True} if err else {})})
        messages.append({"role": "user", "content": results})
    return final or "Stopped at the step limit."


def ollama_chat(messages: list[dict]) -> str:
    body = json.dumps({"model": OLLAMA_MODEL, "stream": False, "format": "json", "options": {"num_ctx": 8192, "temperature": 0.2}, "messages": messages}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["message"]["content"]


def run_ollama(sess: Session, text: str, chat=ollama_chat) -> str:
    listing = "\n".join(f"- {t['name']}: {t['description']} args: {', '.join(t['input_schema']['properties'])}" for t in TOOLS)
    sysm = (SYSTEM + "\n\nTools:\n" + listing + '\n\nEach turn answer with ONE JSON object and nothing else. To use a tool: {"tool": "<name>", "args": {...}}. '
            'When the work is finished: {"done": "<short summary>"}.')
    msgs = [{"role": "system", "content": sysm}, {"role": "user", "content": text}]
    for _ in range(sess.cfg["agent_max_steps"] + 2):
        raw = chat(msgs)
        try:
            obj = json.loads(raw)
        except ValueError:
            msgs += [{"role": "assistant", "content": raw[:2000]}, {"role": "user", "content": "That was not valid JSON. Answer with one JSON object only."}]
            continue
        if "done" in obj:
            return str(obj["done"])
        out, _err = sess.call(str(obj.get("tool", "")), obj.get("args") if isinstance(obj.get("args"), dict) else {})
        msgs += [{"role": "assistant", "content": raw[:2000]}, {"role": "user", "content": "RESULT:\n" + out}]
    return "Stopped at the step limit."


def pick_brain() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            return "claude"
        except ImportError:
            return "ollama-no-sdk"
    return "ollama"


def agent(ws: Path, instruction: str, verify: str = "", provider: str = "", model_chat=None) -> str:
    cfg = config.load()
    if not cfg["allow_write"]:
        raise Refused("Editing is switched off at this PC (allow_write), so the agent cannot work.")
    instruction = (instruction or "").strip()
    if len(instruction) < 8:
        raise Refused("Describe the change in a sentence or two.")
    gitops.must_be_repo(ws)
    if gitops.status(ws).splitlines()[1:]:
        raise Refused("This workspace has uncommitted changes. Commit or discard them first, so the agent's work can be undone cleanly.")
    brain = provider or pick_brain()
    note = ""
    if brain == "ollama-no-sdk":
        note, brain = "(ANTHROPIC_API_KEY is set but the anthropic package is missing: run pip install anthropic. Using Ollama for now.)\n", "ollama"
    base = gitops.current_branch(ws)
    branch = "dev/agent-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    gitops.new_branch(ws, branch)
    sess = Session(ws, cfg)
    text = prompt(ws, instruction)
    try:
        if brain == "claude":
            final = run_claude(sess, text)
        else:
            final = run_ollama(sess, text, model_chat or ollama_chat)
    except Exception as e:      # a network or model problem: leave the branch as it is, say so
        final = f"The agent stopped: {type(e).__name__}: {str(e)[:200]}"
    changes = gitops.diff(ws, stat=True)
    commit_msg = ""
    if changes != "No changes.":
        try:
            commit_msg = gitops.commit(ws, "Agent: " + instruction[:80])
        except Refused as e:
            commit_msg = "Not committed: " + str(e)
    check = ""
    if verify and verify in tasks.TASKS:
        try:
            check = "\n\nCheck after the change (" + verify + "):\n" + tasks.run_task(ws, verify)
        except Refused as e:
            check = "\n\nCheck could not run: " + str(e)
    steps = "\n".join(f"  {i}. {s}" for i, s in enumerate(sess.log, 1)) or "  (no tool calls)"
    return (f"{note}Agent finished on branch {branch} ({'Claude' if brain == 'claude' else 'Ollama ' + OLLAMA_MODEL}, {sess.steps} tool call(s)).\n\n{final}\n\nWhat it did:\n{steps}\n\n"
            f"Changes:\n{changes}\n{commit_msg}{check}\n\nTo undo it all: dev branch back to {base} (git switch {base}) and delete {branch}. To keep it: look at the diff, then dev push.")
