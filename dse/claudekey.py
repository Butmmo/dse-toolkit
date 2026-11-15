"""Connect your own Claude (Anthropic) key: the strongest DBI-AI answers, paid by you directly to Anthropic.

    python dse.py claude setup [--terminal]    a small window asks for the key (hidden as you type); it is checked with Anthropic and saved ON THIS PC only
    python dse.py claude status [--test]       is a key saved, is the package installed (and, with --test, does Anthropic accept the key)
    python dse.py claude sdk                   install the `anthropic` Python package (pip install anthropic)
    python dse.py claude remove                forget the key on this PC (revoke it at console.anthropic.com too if it leaked)

Where the key lives and who sees it:
  * Only on this PC, in your Windows user settings (ANTHROPIC_API_KEY), the same place DBI-AI already reads it from. A running HQ runner sees it without a restart.
  * It is NEVER typed into Citadel, NEVER sent to Citadel, never in a job, a log or a screen: the app only learns "a key is present" (yes or no).
  * The only place it is sent is Anthropic itself: once now, to check it (a free call that lists models), and later with each answer you ask Claude for.
  * It is shown back only as sk-ant-...abcd (the last four characters), on this PC.
You pay Anthropic for what you use (add a small credit and a monthly limit at console.anthropic.com). Standard library only (tkinter for the window, if your Python has it).
"""
from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

NAME = "ANTHROPIC_API_KEY"
KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,300}\Z")
API = "https://api.anthropic.com/v1/models?limit=1"


# ------------------------------------------------------------------ where the key is kept

class WindowsStore:
    """Your Windows user environment variables (HKCU\\Environment). Other systems have none: setup says so instead of guessing."""

    def get(self, name: str) -> str:
        if os.name != "nt":
            return ""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return str(winreg.QueryValueEx(k, name)[0]).strip()
        except (OSError, ImportError, ValueError):
            return ""

    def set(self, name: str, value: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Saving the key works on Windows only. On another system set the ANTHROPIC_API_KEY environment variable yourself.")
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        self._broadcast()

    def delete(self, name: str) -> None:
        if os.name != "nt":
            return
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass
        self._broadcast()

    @staticmethod
    def _broadcast() -> None:
        """Tell Windows the environment changed, so programs started afterwards see it."""
        try:
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 3000, None)
        except Exception:
            pass


def mask(key: str) -> str:
    return "sk-ant-..." + key[-4:] if key else ""


def current_key(store=None) -> str:
    store = store or WindowsStore()
    return (os.environ.get(NAME, "").strip() or store.get(NAME)).strip()


def sdk_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("anthropic") is not None


# ------------------------------------------------------------------ checking a key with Anthropic

def _http(url: str, headers: dict, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def verify(key: str, http=_http) -> tuple[str, str]:
    """(state, plain words). state: ok | invalid | blocked | offline | error. Lists one model: a call that is free and uses no credit."""
    if not KEY_RE.match(key or ""):
        return "invalid", "That does not look like an Anthropic key (it starts with sk-ant- and has no spaces)."
    code, _body = http(API, {"x-api-key": key, "anthropic-version": "2023-06-01"})
    if code == 200:
        return "ok", "Anthropic accepted the key."
    if code == 401:
        return "invalid", "Anthropic says this key is not valid (it may have been deleted or copied with a missing character)."
    if code in (403, 429):
        return "blocked", f"Anthropic answered {code}: the key is real but cannot be used right now (no credit, a limit, or the account needs attention at console.anthropic.com)."
    if code == 0:
        return "offline", "Could not reach Anthropic: check your internet and try again."
    return "error", f"Anthropic answered {code}: try again in a minute."


# ------------------------------------------------------------------ the commands

def status(store=None, test: bool = False, http=_http) -> str:
    store = store or WindowsStore()
    key = current_key(store)
    sdk = sdk_installed()
    lines = ["# Claude (your own key)", "",
             f"Key on this PC: {'yes (' + mask(key) + ')' if key else 'no'}",
             f"Python package `anthropic`: {'installed' if sdk else 'not installed'}"]
    if test and key:
        state, words = verify(key, http)
        lines.append(f"Anthropic says: {words}")
        if state != "ok":
            lines.append("")
    if key and sdk:
        lines += ["", "Claude is ready for DBI-AI: pick Claude in the 'Answering with' menu. You pay Anthropic for each answer."]
    else:
        lines.append("")
        if not key:
            lines.append("Next: python dse.py claude setup   (a small window asks for the key; it stays on this PC)")
        if not sdk:
            lines.append("Next: python dse.py claude sdk     (installs the package Claude needs)")
    return "\n".join(lines) + "\n"


def save(key: str, store=None, http=_http) -> str:
    """Check a key with Anthropic, then keep it on this PC. A key Anthropic rejects is not saved."""
    key = (key or "").strip()
    if not KEY_RE.match(key):
        return "Not saved: that does not look like an Anthropic key (it starts with sk-ant- and has no spaces). Copy it again from console.anthropic.com > API keys.\n"
    state, words = verify(key, http)
    if state in ("invalid",):
        return f"Not saved. {words}\n"
    store = store or WindowsStore()
    try:
        store.set(NAME, key)
    except RuntimeError as e:
        return f"Not saved. {e}\n"
    os.environ[NAME] = key
    extra = "" if state == "ok" else f"\nNote: {words} The key is saved anyway; fix that at console.anthropic.com and run: python dse.py claude status --test"
    sdk = "" if sdk_installed() else "\nOne more step: python dse.py claude sdk   (installs the package Claude needs)"
    return f"Saved on this PC as {mask(key)}. It was not sent anywhere except Anthropic, to check it.{extra}{sdk}\nDBI-AI will offer Claude within a minute.\n"


def remove(store=None) -> str:
    store = store or WindowsStore()
    had = bool(current_key(store))
    store.delete(NAME)
    os.environ.pop(NAME, None)
    return ("Removed from this PC. If the key ever leaked, also delete it at console.anthropic.com > API keys.\n" if had else "There was no key on this PC.\n")


def install_sdk(run=subprocess.run) -> str:
    if sdk_installed():
        return "The `anthropic` package is already installed.\n"
    r = run([sys.executable, "-m", "pip", "install", "--upgrade", "anthropic"], capture_output=True, text=True, timeout=600)
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-4:])
    if r.returncode == 0:
        return "Installed the `anthropic` package.\n" + tail + "\n"
    return "The install did not work:\n" + tail + "\nTry it yourself: python -m pip install anthropic\n"


def ask_key(window: bool = True) -> str:
    """The key, typed hidden. A small window when tkinter exists, else the terminal."""
    if window:
        try:
            import tkinter
            from tkinter import simpledialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            v = simpledialog.askstring("Claude key", "Paste your Anthropic key (it stays on this PC):", show="*", parent=root)
            root.destroy()
            return (v or "").strip()
        except Exception:
            pass
    return getpass.getpass("Paste your Anthropic key (hidden as you type, it stays on this PC): ").strip()


def run_cli(args: list[str]) -> int:
    x = args[0] if args else ""
    if x == "setup":
        key = ask_key(window="--terminal" not in args)
        if not key:
            print("Nothing entered: no key saved.")
            return 1
        out = save(key)
        print(out)
        return 0 if out.startswith("Saved") else 1
    if x == "status":
        print(status(test="--test" in args))
        return 0
    if x == "sdk":
        out = install_sdk()
        print(out)
        return 0 if ("Installed" in out or "already" in out) else 1
    if x == "remove":
        print(remove())
        return 0
    print(__doc__)
    return 0 if x in ("", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
