"""Tests for connecting your own ChatGPT (OpenAI) and Gemini (Google) keys: the Claude pattern, one slot per provider.
The key stays on the PC, is never shown, and is sent only to its own provider, to check it.   python tests/test_providerkeys.py"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import geminikey as G  # noqa: E402
from dse import openaikey as O  # noqa: E402

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


def http(code, calls):
    def f(url, headers, timeout=20):
        calls.append((url, headers))
        return code, ""
    return f


CASES = [
    ("OpenAI", O, "sk-proj-" + "abcDEF123_-" * 4 + "WXYZ", "sk-...WXYZ", "openai", "AIza" + "a" * 35),
    ("Gemini", G, "AIza" + "abcDEF123_-" * 3 + "WXYZ", "AIza...WXYZ", "gemini", "sk-proj-" + "a" * 40),
]

for label, M, KEY, MASKED, cmd, OTHER in CASES:
    saved_env = os.environ.pop(M.NAME, None)
    calls = []
    try:
        # ---------------------------------------------------------------- the key's shape
        check(f"{label}: a real-looking key passes", bool(M.KEY_RE.match(KEY)))
        for bad in ["", "short", KEY + " ", KEY + "\n", " " + KEY, OTHER]:
            check(f"{label}: refused shape: {bad[:20]!r}", not M.KEY_RE.match(bad))
        check(f"{label}: the key is shown only masked", M.mask(KEY) == MASKED and KEY not in M.mask(KEY) and M.mask("") == "")

        # ---------------------------------------------------------------- checking with the provider
        check(f"{label}: accepted key verifies ok", M.verify(KEY, http(200, calls))[0] == "ok")
        check(f"{label}: the check sends the key only to the provider", len(calls) == 1 and KEY in str(calls[0][1]) and "citadel" not in calls[0][0].lower())
        check(f"{label}: a 401 is invalid", M.verify(KEY, http(401, []))[0] == "invalid")
        check(f"{label}: no network is offline", M.verify(KEY, http(0, []))[0] == "offline")
        check(f"{label}: a bad shape never reaches the network", M.verify("nope", http(200, calls))[0] == "invalid" and len(calls) == 1)

        # ---------------------------------------------------------------- save, status, remove
        st = Store()
        out = M.save(KEY, store=st, http=http(401, []))
        check(f"{label}: a rejected key is not saved", out.startswith("Not saved") and not st.d)
        out = M.save(KEY, store=st, http=http(200, []))
        check(f"{label}: an accepted key is saved on this PC only", out.startswith("Saved on this PC") and st.d.get(M.NAME) == KEY and os.environ.get(M.NAME) == KEY)
        s = M.status(store=st)
        check(f"{label}: status with a key says ready and never shows it", "Key on this PC: yes" in s and "ready for DBI-AI" in s and KEY not in s and MASKED in s)
        out = M.remove(store=st)
        check(f"{label}: remove forgets the key", "Removed from this PC" in out and not st.d and M.NAME not in os.environ)
        s = M.status(store=Store())
        check(f"{label}: status with no key says the next step", "Key on this PC: no" in s and f"dse.py {cmd} setup" in s)
        check(f"{label}: removing nothing is honest", "no key on this PC" in M.remove(store=Store()))
    finally:
        os.environ.pop(M.NAME, None)
        if saved_env is not None:
            os.environ[M.NAME] = saved_env

# ---------------------------------------------------------------- the two slots never read each other's key
check("the slots are separate settings", O.NAME == "OPENAI_API_KEY" and G.NAME == "GEMINI_API_KEY" and O.NAME != G.NAME)
check("an OpenAI key is not a Gemini key and the other way round", not G.KEY_RE.match(CASES[0][2]) and not O.KEY_RE.match(CASES[1][2]))

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
