"""Tests for the Voices setup time budget, entirely offline (the network and the clock are replaced).   python tests/test_voices_budget.py"""
import shutil
import sys
import tempfile
import time as real_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import voices as V  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


TMP = Path(tempfile.mkdtemp(prefix="zz-voices-budget-"))
real_roster, real_verify, real_update = V.roster, V.verify_source, V.update
V.PAUSE = 0

FIGS = [
    {
        "id": f"fig{i}",
        "name": f"Figure {i}",
        "era": "dead",
        "sources": [
            {"type": "feed", "url": f"https://example{i}a.invalid/feed"},
            {"type": "feed", "url": f"https://example{i}b.invalid/feed"},
        ],
    }
    for i in range(3)
]
V.roster = lambda: FIGS


def scenario(verify_seconds):
    clock = FakeTime()
    V.time = clock
    V.STORE = TMP / f"store-{verify_seconds}"
    updates = []

    def fake_verify(f, s):
        clock.now += verify_seconds
        return {"ok": True, "detail": "fine", "url": s.get("url")}

    V.verify_source = fake_verify
    V.update = lambda fid="": updates.append(fid) or ""
    out = V.setup("", 1)  # a one minute budget, like the background helper's four scaled down
    return out, len(V.load_state()["verified"]), updates


# Slow sources: one check eats most of the budget. Setup must stop starting new
# checks, carry the rest over to next time, and skip the closing feed read, so
# the runner never has to kill the helper at its 5 minute limit.
out, verified, updates = scenario(40)
check("a slow run verifies only what fits inside the budget", verified == 1, f"got {verified}")
check("a slow run reports every figure as left for next time", "Time ran out before: Figure 0, Figure 1, Figure 2" in out)
check("a slow run skips the closing feed read", updates == [])

# Fast sources: the whole roster is checked, nothing is left over, and the
# closing feed read runs as before.
out, verified, updates = scenario(1)
check("a fast run verifies every source", verified == 6, f"got {verified}")
check("a fast run leaves nothing for next time", "Time ran out before" not in out)
check("a fast run still does the closing feed read", len(updates) == 1)

V.roster, V.verify_source, V.update = real_roster, real_verify, real_update
V.time = real_time
shutil.rmtree(TMP, ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
