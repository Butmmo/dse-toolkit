"""Which Ollama model the HQ chat uses. Shared by chat.py and both runners.

Order, first that gives an answer wins:
  1. OLLAMA_MODEL in this process (set before the program started)
  2. OLLAMA_MODEL saved in your Windows user settings. A running program does not see a variable you set after it started, which is why DBI-AI kept
     using gemma3:1b until the runner was restarted; reading the saved value directly means a restart is not needed for this setting
  3. the best model actually installed in Ollama (gemma3:4b before gemma3:1b), asked from Ollama itself
  4. gemma3:1b, only if nothing else can be found
The answer carries WHY, so the chat footer can say where the choice came from.
"""
from __future__ import annotations

import json
import os
import urllib.request

# best first: all of these read pictures except none; 1b is last because it is too small to follow a conversation or read a picture
PREFER = ["gemma3:4b", "gemma3:latest", "gemma3:12b", "gemma3:27b", "gemma3:1b"]
DEFAULT = "gemma3:1b"


def user_setting(name: str = "OLLAMA_MODEL") -> str:
    """The value saved in Windows user environment variables (HKCU\\Environment), or '' elsewhere or when not set."""
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, name)[0]).strip()
    except (OSError, ImportError, ValueError):
        return ""


def installed(timeout: float = 2.0) -> list[str]:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=timeout) as r:
            return [str(m.get("name", "")) for m in json.loads(r.read()).get("models", []) if m.get("name")]
    except Exception:
        return []


def pick(env=None, saved=None, have=None) -> tuple[str, str]:
    """(model, why). The three sources can be passed in for testing."""
    env = os.environ.get("OLLAMA_MODEL", "").strip() if env is None else env
    if env:
        return env, "your OLLAMA_MODEL setting"
    saved = user_setting() if saved is None else saved
    if saved:
        return saved, "your saved OLLAMA_MODEL setting (read from Windows, no restart needed)"
    have = installed() if have is None else have
    for p in PREFER:
        if p in have:
            return p, "the best model installed (no OLLAMA_MODEL setting found)"
    if have:
        return have[0], "the only kind installed"
    return DEFAULT, "the default (Ollama did not answer)"
