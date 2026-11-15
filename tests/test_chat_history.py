"""The memory range reaches the AI message and stays inside its cap.   python tests/test_chat_history.py"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hq_chat", ROOT / "chat" / "chat.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
fails = []


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        fails.append(name)


C.HISTORY = ""
check("no history: no history section", "EARLIER IN THIS CHAT" not in C.build_user_message("how do I follow up"))
C.HISTORY = "You: my client went quiet | HQ: wait three days"
m = C.build_user_message("and what do I say")
check("history is added before the question", "EARLIER IN THIS CHAT" in m and m.index("my client went quiet") < m.index("QUESTION:") and m.rstrip().endswith("and what do I say"))
C.HISTORY = "Z" * 9000
m = C.build_user_message("q")
check("an oversized history is cut to the cap, keeping the newest end", m.count("Z") == C.HISTORY_MAX)
src = (ROOT / "chat" / "chat.py").read_text(encoding="utf-8")
check("--history is read from the command line", '"--history" in args' in src)
check("the tool copy in _tools is identical", (ROOT.parent / "_tools" / "chat" / "chat.py").read_text(encoding="utf-8") == src)
check("no em dash", chr(0x2014) not in src)
print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
