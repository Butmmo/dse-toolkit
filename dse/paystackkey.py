"""Connect your own Paystack key: create payment links and read your payments, in Citadel's Get Paid tools.

    python dse.py paystack setup [--terminal]    a small window asks for the key (hidden as you type); it is checked with Paystack and saved ON THIS PC only
    python dse.py paystack status [--test]       is a key saved (and, with --test, does Paystack accept the key)
    python dse.py paystack remove                forget the key on this PC (roll it at dashboard.paystack.com too if it leaked)

Where the key lives and who sees it:
  * Only on this PC, in your Windows user settings (PAYSTACK_SECRET_KEY). A running HQ runner sees it without a restart.
  * It is NEVER typed into Citadel, NEVER sent to Citadel, never in a job, a log or a screen: the app only learns "a key is present" (yes or no).
  * The only place it is sent is Paystack itself: once now, to check it (a free call that lists one transaction), and later when you create a payment link or check your payments.
  * It is shown back only masked (the last four characters), on this PC.
Treat this key like a bank password: with it, a person could read your transactions and change your Paystack settings. Get it at dashboard.paystack.com > Settings > API Keys & Webhooks. No Python package is needed: the toolkit talks to Paystack directly. Standard library only.
"""
from __future__ import annotations

import getpass
import os
import re
import sys
import urllib.error
import urllib.request

NAME = "PAYSTACK_SECRET_KEY"
KEY_RE = re.compile(r"^sk_(test|live)_[A-Za-z0-9]{16,200}\Z")
API = "https://api.paystack.co/transaction?perPage=1"


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
            raise RuntimeError("Saving the key works on Windows only. On another system set the PAYSTACK_SECRET_KEY environment variable yourself.")
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
    return "sk_..." + key[-4:] if key else ""


def mode(key: str) -> str:
    return "test" if key.startswith("sk_test_") else "live"


def current_key(store=None) -> str:
    store = store or WindowsStore()
    return (os.environ.get(NAME, "").strip() or store.get(NAME)).strip()


# ------------------------------------------------------------------ checking a key with Paystack

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
    """(state, plain words). state: ok | invalid | blocked | offline | error. Lists one transaction: a free call that moves nothing."""
    if not KEY_RE.match(key or ""):
        return "invalid", "That does not look like a Paystack secret key (it starts with sk_test_ or sk_live_ and has no spaces)."
    code, _body = http(API, {"Authorization": "Bearer " + key})
    if code == 200:
        return "ok", "Paystack accepted the key."
    if code == 401:
        return "invalid", "Paystack says this key is not valid (it may have been rolled, or copied with a missing character)."
    if code in (403, 429):
        return "blocked", f"Paystack answered {code}: the key is real but cannot be used right now (see dashboard.paystack.com for what needs attention)."
    if code == 0:
        return "offline", "Could not reach Paystack: check your internet and try again."
    return "error", f"Paystack answered {code}: try again in a minute."


# ------------------------------------------------------------------ the commands

def status(store=None, test: bool = False, http=_http) -> str:
    store = store or WindowsStore()
    key = current_key(store)
    lines = ["# Paystack (your own key, for getting paid)", "",
             f"Key on this PC: {'yes (' + mask(key) + ', ' + mode(key) + ' mode)' if key else 'no'}",
             "Python package: none needed (the toolkit talks to Paystack directly)"]
    if test and key:
        state, words = verify(key, http)
        lines.append(f"Paystack says: {words}")
        if state != "ok":
            lines.append("")
    if key:
        lines += ["", "Paystack is ready: Citadel can create a payment link with it and check your recent payments, from the Clients page and the Quotes tab.",
                  "", "The key never leaves this PC except to Paystack itself. Citadel only ever learns yes or no."]
    else:
        lines += ["", "Next: python dse.py paystack setup   (a small window asks for the key; it stays on this PC)",
                  "Get the key at dashboard.paystack.com > Settings > API Keys & Webhooks."]
    return "\n".join(lines) + "\n"


def save(key: str, store=None, http=_http) -> str:
    """Check a key with Paystack, then keep it on this PC. A key Paystack rejects is not saved."""
    key = (key or "").strip()
    if not KEY_RE.match(key):
        return "Not saved: that does not look like a Paystack secret key (it starts with sk_test_ or sk_live_ and has no spaces). Copy it again from dashboard.paystack.com > Settings > API Keys & Webhooks.\n"
    state, words = verify(key, http)
    if state in ("invalid",):
        return f"Not saved. {words}\n"
    store = store or WindowsStore()
    try:
        store.set(NAME, key)
    except RuntimeError as e:
        return f"Not saved. {e}\n"
    os.environ[NAME] = key
    extra = "" if state == "ok" else f"\nNote: {words} The key is saved anyway; fix that at dashboard.paystack.com and run: python dse.py paystack status --test"
    return f"Saved on this PC as {mask(key)} ({mode(key)} mode). It was not sent anywhere except Paystack, to check it.{extra}\nCitadel will offer Paystack within a minute.\n"


def remove(store=None) -> str:
    store = store or WindowsStore()
    had = bool(current_key(store))
    store.delete(NAME)
    os.environ.pop(NAME, None)
    return ("Removed from this PC. If the key ever leaked, also roll it at dashboard.paystack.com > Settings > API Keys & Webhooks.\n" if had else "There was no key on this PC.\n")


def ask_key(window: bool = True) -> str:
    """The key, typed hidden. A small window when tkinter exists, else the terminal."""
    if window:
        try:
            import tkinter
            from tkinter import simpledialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            v = simpledialog.askstring("Paystack key", "Paste your Paystack secret key (it stays on this PC):", show="*", parent=root)
            root.destroy()
            return (v or "").strip()
        except Exception:
            pass
    return getpass.getpass("Paste your Paystack secret key (hidden as you type, it stays on this PC): ").strip()


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
