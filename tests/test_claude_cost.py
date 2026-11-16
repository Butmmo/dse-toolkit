"""Tests for Claude cost control: model tiers, the token tally, the daily limit, and how chat.py uses them.   python tests/test_claude_cost.py"""
import datetime as dt
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="zz-cost-"))
os.environ["HQ_CLAUDE_USAGE_FILE"] = str(TMP / "usage.json")      # a throwaway file: the real tally is never touched


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


C = load("claude_cost", ROOT / "chat" / "claude_cost.py")
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- which model
check("the default is Sonnet (balanced), not the most expensive", C.DEFAULT_TIER == "sonnet" and C.resolve("claude") == ("sonnet", "claude-sonnet-5-5"))
check("each tier maps to its model", C.resolve("claude:haiku") == ("haiku", "claude-haiku-5-5") and C.resolve("claude:opus") == ("opus", "claude-opus-5-5") and C.resolve("claude:sonnet")[0] == "sonnet")
check("the PC's default can be a tier name or a model id", C.resolve("claude", "haiku") == ("haiku", "claude-haiku-5-5") and C.resolve("claude", "claude-opus-5-5")[0] == "opus" and C.resolve("claude", "Haiku")[0] == "haiku")
check("your own model id is passed through only if it is plain", C.resolve("claude", "claude-future-9") == ("custom", "claude-future-9") and C.resolve("claude", "claude-x; rm -rf") == ("sonnet", "claude-sonnet-5-5") and C.resolve("claude", "gpt-4")[0] == "sonnet")
check("a per-question choice beats the PC's default", C.resolve("claude:haiku", "opus")[0] == "haiku")
check("valid modes", all(C.valid_mode(m) for m in ("claude", "claude:haiku", "claude:sonnet", "claude:opus")) and not C.valid_mode("claude:gpt") and not C.valid_mode("ollama:x") and not C.valid_mode("claude:"))
check("every tier says what it is, in words and not invented prices", all(len(v[2]) > 10 and "$" not in v[2] for v in C.TIERS.values()))

# ---------------------------------------------------------------- the tally
d = dt.date(2026, 11, 16)
check("nothing used yet", C.used_today(d) == 0 and C.limit() == 0 and not C.over_limit(d))
C.record("claude-sonnet-5-5", 900, 300, d)
C.record("claude-sonnet-5-5", 100, 50, d)
C.record("claude-haiku-5-5", 10, 5, d)
check("tokens add up by day, in and out, across models", C.used_today(d) == 1365)
check("another day is separate", C.used_today(d + dt.timedelta(days=1)) == 0)
check("negative or odd numbers do not corrupt the tally", (C.record("m", -5, None, d), C.used_today(d))[1] == 1365)
for k in range(70):
    C.record("claude-sonnet-5-5", 1, 1, d - dt.timedelta(days=k + 1))
check("only the last 60 days are kept", len(C._load()["days"]) <= C.KEEP_DAYS)
rep = C.report(7, d)
check("the report shows tokens by model and says money is not computed here", "claude-sonnet-5-5" in rep and "tokens" in rep and "console.anthropic.com" in rep and "$" not in rep, rep)

# ---------------------------------------------------------------- the daily limit
check("setting a limit", C.set_limit(2000) == 2000 and C.limit() == 2000)
check("under the limit is fine, at the limit it rests", not C.over_limit(d) and (C.record("claude-sonnet-5-5", 700, 0, d) or C.over_limit(d)))
check("tomorrow starts fresh", not C.over_limit(d + dt.timedelta(days=1)))
check("0 removes the limit", C.set_limit(0) == 0 and not C.over_limit(d))
check("a limit is capped and never negative", C.set_limit(-5) == 0 and C.set_limit(10 ** 12) == C.MAX_LIMIT)
C.set_limit(0)

# ---------------------------------------------------------------- how chat.py uses it (with a fake Anthropic)
chat = load("hq_chat", ROOT / "chat" / "chat.py")
calls = []


class FakeMessages:
    def create(self, **kw):
        calls.append(kw)
        return types.SimpleNamespace(stop_reason="end_turn", model=kw["model"], content=[types.SimpleNamespace(type="text", text="A Claude answer.")], usage=types.SimpleNamespace(input_tokens=1000, output_tokens=200))


fake = types.ModuleType("anthropic")
fake.Anthropic = lambda: types.SimpleNamespace(beta=types.SimpleNamespace(messages=FakeMessages()))
sys.modules["anthropic"] = fake
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-" + "x" * 30
chat.CLAUDE_MODEL = ""
before = C.used_today()
txt, note = chat.claude("how do I follow up", "claude")
check("the default question goes to Sonnet, with a cap on the answer's length", calls[-1]["model"] == "claude-sonnet-5-5" and calls[-1]["max_tokens"] <= 2000, str(calls[-1].get("model")))
check("the footer shows the tokens and today's total", "1,200 tokens (in 1,000, out 200)" in note and "today" in note, note)
check("the answer's tokens were added to today's tally", C.used_today() - before == 1200)
chat.claude("x question here", "claude:haiku")
check("a per-question choice picks that model", calls[-1]["model"] == "claude-haiku-5-5")
chat.claude("x question here", "claude:opus")
check("Opus only when asked for", calls[-1]["model"] == "claude-opus-5-5")
chat.CLAUDE_MODEL = "haiku"
chat.claude("x question here", "claude")
check("the PC's default setting is honoured for plain Claude", calls[-1]["model"] == "claude-haiku-5-5")
chat.CLAUDE_MODEL = ""
n = len(calls)
C.set_limit(1000)
txt, note = chat.claude("x question here", "claude")
check("over the daily limit Claude is not called, and the note says what to do", txt == "" and len(calls) == n and "limit" in note and "claude limit" in note, note)
c = chat.reply("how do I follow up a quiet lead", None, "claude")
check("explicitly choosing Claude over the limit gives the library answer with the reason (no money spent)", len(calls) == n and "limit" in c, c[-200:])
C.set_limit(0)
check("an unknown Claude tier is refused politely", "I do not know the model choice" in chat.reply("a question here", None, "claude:gpt"))
src = (ROOT / "chat" / "claude_cost.py").read_text(encoding="utf-8")
check("no em dash, and the module talks to no network", chr(0x2014) not in src and "urllib" not in src and "requests" not in src)
check("the tool copy in _tools is identical", (ROOT.parent / "_tools" / "chat" / "claude_cost.py").read_text(encoding="utf-8") == src and (ROOT.parent / "_tools" / "chat" / "chat.py").read_text(encoding="utf-8") == (ROOT / "chat" / "chat.py").read_text(encoding="utf-8"))
sys.modules.pop("anthropic", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
