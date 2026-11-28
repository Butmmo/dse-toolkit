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
import re
import urllib.request

# best first: all of these read pictures except none; 1b is last because it is too small to follow a conversation or read a picture
PREFER = ["gemma3:4b", "gemma3:latest", "gemma3:12b", "gemma3:27b", "gemma3:1b"]
CODING_TASK = re.compile(r"\b(code|coding|program|programming|python|javascript|typescript|sql|debug|bug|stack trace|compiler|repository|repo|function|class|api|migration|build app|dev)\b", re.I)
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


def pick(env=None, saved=None, have=None, task="") -> tuple[str, str]:
    """(model, why). Coding work prefers an installed Qwen coder; other tasks use the saved/default preference."""
    env = os.environ.get("OLLAMA_MODEL", "").strip() if env is None else env
    if env:
        return env, "your OLLAMA_MODEL setting"
    saved = user_setting() if saved is None else saved
    if saved:
        return saved, "your saved OLLAMA_MODEL setting (read from Windows, no restart needed)"
    have = installed() if have is None else have
    if task and CODING_TASK.search(str(task)):
        coder = sorted((m for m in have if "coder" in m.lower() and "qwen" in m.lower()), key=lambda m: ("14b" not in m.lower(), "7b" not in m.lower(), m.lower()))
        if coder:
            return coder[0], "the best installed local coding model for this task"
    for p in PREFER:
        if p in have:
            return p, "the best model installed (no OLLAMA_MODEL setting found)"
    if have:
        return have[0], "the only kind installed"
    return DEFAULT, "the default (Ollama did not answer)"


# ------------------------------------------------------------------ what the DBI-AI model picker can offer

def has_claude_key() -> bool:
    """An Anthropic key on this PC: in this process or saved in Windows user settings. The key itself is never read out or sent anywhere from here."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or user_setting("ANTHROPIC_API_KEY"))


def claude_ready() -> bool:
    """Claude can be used: a key is present AND the anthropic package is installed for this Python."""
    try:
        import importlib.util
        return has_claude_key() and importlib.util.find_spec("anthropic") is not None
    except Exception:
        return False


def has_openai_key() -> bool:
    """An OpenAI key on this PC: in this process or saved in Windows user settings. The key itself is never read out or sent anywhere from here."""
    return bool(os.environ.get("OPENAI_API_KEY", "").strip() or user_setting("OPENAI_API_KEY"))


def openai_ready() -> bool:
    """ChatGPT can be used: a key is present (no package is needed; chat.py talks to OpenAI directly)."""
    return has_openai_key()


def has_gemini_key() -> bool:
    """A Google AI Studio key on this PC: in this process or saved in Windows user settings. The key itself is never read out or sent anywhere from here."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip() or user_setting("GEMINI_API_KEY"))


def gemini_ready() -> bool:
    """Gemini can be used: a key is present (no package is needed; chat.py talks to Google directly)."""
    return has_gemini_key()


def has_paystack_key() -> bool:
    """A Paystack secret key on this PC: in this process or saved in Windows user settings. The key itself is never read out or sent anywhere from here."""
    return bool(os.environ.get("PAYSTACK_SECRET_KEY", "").strip() or user_setting("PAYSTACK_SECRET_KEY"))


def paystack_ready() -> bool:
    """Paystack can be used (payment links and recent payments): a key is present (no package is needed; paylinks.py talks to Paystack directly)."""
    return has_paystack_key()


def models_info(timeout: float = 4.0, limit: int = 12) -> list[dict]:
    """Installed Ollama models with whether each reads pictures and its size: [{name, vision, size_gb}]. Asks Ollama itself."""
    out: list[dict] = []
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            tags = json.loads(r.read()).get("models", [])
    except Exception:
        return out
    for m in tags[:limit]:
        name = str(m.get("name", ""))
        if not name:
            continue
        vision = False
        try:
            req = urllib.request.Request("http://localhost:11434/api/show", json.dumps({"model": name}).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                vision = "vision" in (json.loads(r.read()).get("capabilities") or [])
        except Exception:
            pass
        out.append({"name": name, "vision": vision, "size_gb": round(float(m.get("size", 0)) / 1e9, 1)})
    return out
