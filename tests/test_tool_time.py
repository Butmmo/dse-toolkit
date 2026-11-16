"""Every tool gets at least 30 minutes to run.   python tests/test_tool_time.py"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runner", ROOT / "bridge" / "runner.py")
R = importlib.util.module_from_spec(spec)
sys.modules["runner"] = R
spec.loader.exec_module(R)

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


check("the floor is 30 minutes", R.MIN_TOOL_MINUTES == 30)
check("a short limit is raised to 30", R.tool_minutes({"timeout_min": 1}) == 30 and R.tool_minutes({"timeout_min": 5}) == 30 and R.tool_minutes({"timeout_min": 29}) == 30)
check("no limit given means 30", R.tool_minutes({}) == 30 and R.tool_minutes({"timeout_min": None}) == 30 and R.tool_minutes({"timeout_min": "x"}) == 30)
check("a longer limit is kept", R.tool_minutes({"timeout_min": 90}) == 90 and R.tool_minutes({"timeout_min": 180}) == 180)
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
pub = R.public_catalog(cat)
check("what Citadel is told is never under 30 for any tool", pub["tools"] and all(t["timeout_min"] >= 30 for t in pub["tools"].values()), str([k for k, t in pub["tools"].items() if t["timeout_min"] < 30][:5]))
src = (ROOT / "bridge" / "runner.py").read_text(encoding="utf-8")
check("the stop-time uses the floor, not the raw number", "limit = tool_minutes(tool) * 60" in src and "tool.get('timeout_min', 30)" not in src)
check("no em dash", chr(0x2014) not in src + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
