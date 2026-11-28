"""Connect your own Gemini (Google AI Studio) key: strong DBI-AI answers, paid by you directly to Google (a free tier exists).

    python dse.py gemini setup [--terminal]    a small window asks for the key (hidden as you type); it is checked with Google and saved ON THIS PC only
    python dse.py gemini status [--test]       is a key saved (and, with --test, does Google accept the key)
    python dse.py gemini remove                forget the key on this PC (revoke it at aistudio.google.com too if it leaked)

Where the key lives and who sees it:
  * Only on this PC, in your Windows user settings (GEMINI_API_KEY). A running HQ runner sees it without a restart.
  * It is NEVER typed into Citadel, NEVER sent to Citadel, never in a job, a log or a screen: the app only learns "a key is present" (yes or no).
  * The only place it is sent is Google itself: once now, to check it (a free call that lists models), and later with each answer you ask Gemini for.
  * It is shown back only as AIza...abcd (the last four characters), on this PC.
Cost control: DBI-AI answers with Gemini 2.5 Flash (fast; Google AI Studio has a free tier) by default; choose Gemini 2.5 Pro (strongest) per question in DBI-AI.
You pay Google for what you use beyond the free tier (see aistudio.google.com). No Python package is needed: DBI-AI talks to Google directly. Standard library only.
"""
from __future__ import annotations

import getpass
import os
import re
import sys
import urllib.error
import urllib.request

NAME = "GEMINI_API_KEY"
KEY_RE = re.compile(r"^AIza[A-Za-z0-9_-]{20,80}\Z")
API = "https://generativelanguage.googleapis.com/v1beta/models"


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
            raise RuntimeError("Saving the key works on Windows only. On another system set the GEMINI_API_KEY environment variable yourself.")
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
    return "AIza..." + key[-4:] if key else ""


def current_key(store=None) -> str:
    store = store or WindowsStore()
    return (os.environ.get(NAME, "").strip() or store.get(NAME)).strip()


# ------------------------------------------------------------------ checking a key with Google

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
    """(state, plain words). state: ok | invalid | blocked | offline | error. Lists models: a call that is free and uses no credit."""
    if not KEY_RE.match(key or ""):
        return "invalid", "That does not look like a Google AI Studio key (it starts with AIza and has no spaces)."
    code, _body = http(API, {"x-goog-api-key": key})
    if code == 200:
        return "ok", "Google accepted the key."
    if code in (400, 401):
        return "invalid", "Google says this key is not valid (it may have been deleted or copied with a missing character)."
    if code in (403, 429):
        return "blocked", f"Google answered {code}: the key is real but cannot be used right now (a limit, or the account needs attention at aistudio.google.com)."
    if code == 0:
        return "offline", "Could not reach Google: check your internet and try again."
    return "error", f"Google answered {code}: try again in a minute."


# ------------------------------------------------------------------ the commands

def status(store=None, test: bool = False, http=_http) -> str:
    store = store or WindowsStore()
    key = current_key(store)
    lines = ["# Gemini (your own Google key)", "",
             f"Key on this PC: {'yes (' + mask(key) + ')' if key else 'no'}",
             "Python package: none needed (DBI-AI talks to Google directly)"]
    if test and key:
        state, words = verify(key, http)
        lines.append(f"Google says: {words}")
        if state != "ok":
            lines.append("")
    if key:
        lines += ["", "Default model: Gemini 2.5 Flash (fast; a free tier exists at Google AI Studio). Pick Gemini 2.5 Pro (strongest) per question in DBI-AI.",
                  "", "Gemini is ready for DBI-AI: pick Gemini in the model menu. You pay Google for each answer beyond the free tier."]
    else:
        lines += ["", "Next: python dse.py gemini setup   (a small window asks for the key; it stays on this PC)"]
    return "\n".join(lines) + "\n"


def save(key: str, store=None, http=_http) -> str:
    """Check a key with Google, then keep it on this PC. A key Google rejects is not saved."""
    key = (key or "").strip()
    if not KEY_RE.match(key):
        return "Not saved: that does not look like a Google AI Studio key (it starts with AIza and has no spaces). Copy it again from aistudio.google.com > API keys.\n"
    state, words = verify(key, http)
    if state in ("invalid",):
        return f"Not saved. {words}\n"
    store = store or WindowsStore()
    try:
        store.set(NAME, key)
    except RuntimeError as e:
        return f"Not saved. {e}\n"
    os.environ[NAME] = key
    extra = "" if state == "ok" else f"\nNote: {words} The key is saved anyway; fix that at aistudio.google.com and run: python dse.py gemini status --test"
    return f"Saved on this PC as {mask(key)}. It was not sent anywhere except Google, to check it.{extra}\nDBI-AI will offer Gemini within a minute.\n"


def remove(store=None) -> str:
    store = store or WindowsStore()
    had = bool(current_key(store))
    store.delete(NAME)
    os.environ.pop(NAME, None)
    return ("Removed from this PC. If the key ever leaked, also delete it at aistudio.google.com > API keys.\n" if had else "There was no key on this PC.\n")


def ask_key(window: bool = True) -> str:
    """The key, typed hidden. A small window when tkinter exists, else the terminal."""
    if window:
        try:
            import tkinter
            from tkinter import simpledialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            v = simpledialog.askstring("Gemini key", "Paste your Google AI Studio key (it stays on this PC):", show="*", parent=root)
            root.destroy()
            return (v or "").strip()
        except Exception:
            pass
    return getpass.getpass("Paste your Google AI Studio key (hidden as you type, it stays on this PC): ").strip()


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
    if x == "remove":
        print(remove())
        return 0
    print(__doc__)
    return 0 if x in ("", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
