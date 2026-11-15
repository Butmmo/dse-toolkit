"""Tests for connecting your own Claude key (kept on the PC, never shown, never sent anywhere but Anthropic).   python tests/test_claudekey.py"""
import contextlib
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import claudekey as C  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Store:
    def __init__(self):
        self.d = {}

    def get(self, n):
        return self.d.get(n, "")

    def set(self, n, v):
        self.d[n] = v

    def delete(self, n):
        self.d.pop(n, None)


class Broken(Store):
    def set(self, n, v):
        raise RuntimeError("Saving the key works on Windows only.")


KEY = "sk-ant-api03-" + "abcDEF123_-" * 4 + "WXYZ"
saved_env = os.environ.pop(C.NAME, None)
calls = []


def http(code):
    def f(url, headers, timeout=20):
        calls.append((url, headers))
        return code, ""
    return f


# ---------------------------------------------------------------- the key's shape
check("a real-looking key passes", bool(C.KEY_RE.match(KEY)))
for bad in ["", "sk-ant-short", "sk-proj-" + "a" * 40, "sk-ant-" + "a" * 30 + " b", "sk-ant-" + "a" * 30 + "\n", " " + KEY, "sk-ant-" + "a" * 400, "sk-ant-" + "a" * 25 + "$%"]:
    check(f"refused shape: {bad[:24]!r}", not C.KEY_RE.match(bad))
check("the key is shown only as its last four characters", C.mask(KEY) == "sk-ant-...WXYZ" and KEY not in C.mask(KEY) and C.mask("") == "")

# ---------------------------------------------------------------- checking with Anthropic
check("accepted", C.verify(KEY, http(200))[0] == "ok")
check("rejected as invalid", C.verify(KEY, http(401))[0] == "invalid")
check("a real key that cannot be used right now", C.verify(KEY, http(429))[0] == "blocked" and C.verify(KEY, http(403))[0] == "blocked")
check("no internet", C.verify(KEY, http(0))[0] == "offline")
check("any other answer", C.verify(KEY, http(500))[0] == "error")
calls.clear()
check("a key of the wrong shape never reaches the network", C.verify("nope", http(200))[0] == "invalid" and not calls)
verify_call = []
C.verify(KEY, lambda url, headers, timeout=20: verify_call.append((url, headers)) or (200, ""))
check("the check is the free model-list call and sends the key only to api.anthropic.com", verify_call[0][0].startswith("https://api.anthropic.com/v1/models") and verify_call[0][1]["x-api-key"] == KEY)

# ---------------------------------------------------------------- saving
st = Store()
out = C.save("sk-ant-bad", st, http(200))
check("a key of the wrong shape is not saved", out.startswith("Not saved") and not st.d)
out = C.save(KEY, st, http(401))
check("a key Anthropic rejects is not saved", out.startswith("Not saved") and not st.d and KEY not in out)
out = C.save("  " + KEY + "  ", st, http(200))
check("a good key is saved on this PC (spaces around it are tolerated) and the words never contain the key", st.d.get(C.NAME) == KEY and os.environ.get(C.NAME) == KEY and out.startswith("Saved") and KEY not in out and "sk-ant-...WXYZ" in out, out)
check("the answer says where it was sent", "not sent anywhere except Anthropic" in out)
st2 = Store()
os.environ.pop(C.NAME, None)
out = C.save(KEY, st2, http(429))
check("a real key that is blocked right now is saved, with the reason", st2.d.get(C.NAME) == KEY and "Note:" in out and "credit" in out and KEY not in out, out)
os.environ.pop(C.NAME, None)
out = C.save(KEY, Broken(), http(200))
check("a PC that cannot keep it (not Windows) says so and saves nothing", out.startswith("Not saved") and "Windows only" in out and C.NAME not in os.environ)

# ---------------------------------------------------------------- status
os.environ.pop(C.NAME, None)
empty = C.status(Store())
check("with no key it says what to do next, in the order to do it", "Key on this PC: no" in empty and "claude setup" in empty)
os.environ[C.NAME] = KEY
calls.clear()
text = C.status(Store(), test=True, http=http(200))
check("with a key it shows only the masked key, and asks Anthropic when told to", "sk-ant-...WXYZ" in text and KEY not in text and "Anthropic accepted the key" in text and len(calls) == 1, text)
calls.clear()
C.status(Store(), test=False, http=http(200))
check("without --test it makes no network call", not calls)
os.environ.pop(C.NAME, None)
check("a key saved in Windows (not in this process) is found", "Key on this PC: yes" in C.status(SimpleNamespace(get=lambda n: KEY)))

# ---------------------------------------------------------------- removing
st3 = Store()
st3.d[C.NAME] = KEY
os.environ[C.NAME] = KEY
check("remove forgets it everywhere on this PC", "Removed" in C.remove(st3) and not st3.d and C.NAME not in os.environ)
check("remove with no key says so", "no key" in C.remove(Store()))

# ---------------------------------------------------------------- the package
C.sdk_installed = lambda: False
good = lambda *a, **k: SimpleNamespace(returncode=0, stdout="Successfully installed anthropic", stderr="")  # noqa: E731
bad = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="ERROR: no internet")  # noqa: E731
check("the package install succeeds or says why not", "Installed" in C.install_sdk(good) and "did not work" in C.install_sdk(bad) and "python -m pip install anthropic" in C.install_sdk(bad))
seen = []
C.install_sdk(lambda argv, **k: seen.append(argv) or good())
check("it installs only the official package, with this Python's pip", seen[0][1:] == ["-m", "pip", "install", "--upgrade", "anthropic"])
C.sdk_installed = lambda: True
check("already installed is not installed again", "already installed" in C.install_sdk(bad))

# ---------------------------------------------------------------- the command line never prints the key
C.ask_key = lambda window=True: KEY
C.save = lambda key, store=None, http=C._http: "Saved on this PC as sk-ant-...WXYZ.\n"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    code = C.run_cli(["setup"])
check("setup prints no key and returns 0 when saved", code == 0 and KEY not in buf.getvalue())
C.ask_key = lambda window=True: ""
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    code = C.run_cli(["setup"])
check("an empty entry saves nothing", code == 1 and "no key saved" in buf.getvalue())

# ---------------------------------------------------------------- the module
src = (ROOT / "dse" / "claudekey.py").read_text(encoding="utf-8")
check("no em dash", chr(0x2014) not in src)
check("the module never talks to Citadel", not any(w in src.lower() for w in ("supabase", "hq_runner", "hq_queue", "citadel.rpc")))
check("the only address the key can go to is Anthropic's", src.count("http") and "api.anthropic.com" in src and src.count("https://") == 1 or src.count("https://api.anthropic.com") == 1)
if saved_env is not None:
    os.environ[C.NAME] = saved_env
else:
    os.environ.pop(C.NAME, None)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
