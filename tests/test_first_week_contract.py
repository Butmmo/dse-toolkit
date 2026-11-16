"""The numbers Citadel's First 7 days card reads are really what the engines sync reports.   python tests/test_first_week_contract.py
Citadel (src/lib/first-week.ts) reads member_engines.pc_status: lists, and results.sent / replied / booked / won. This keeps that true."""
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import outcomes  # noqa: E402

spec = importlib.util.spec_from_file_location("engines_sync", ROOT / "bridge" / "engines_sync.py")
ES = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ES)
fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra else "" if cond else ""))
    if not cond:
        fails.append(name)


today = "2026-11-10"
rows = [{"sent": True, "replied": True, "booked": True, "won": True, "lost": False, "value": 450.0, "touch": 1, "_date": today, "skipped": False, "channel": "email"},
        {"sent": True, "replied": False, "booked": False, "won": False, "lost": False, "value": 0.0, "touch": 1, "_date": today, "skipped": False, "channel": "email"},
        {"sent": False, "replied": False, "booked": False, "won": False, "lost": False, "value": 0.0, "touch": 1, "_date": today, "skipped": False, "channel": "email"}]
outcomes.rows_with_flags = lambda slug: rows
s = outcomes.summary("x")
check("the results carry the four numbers the card counts, as whole numbers", all(isinstance(s[k], int) for k in ("sent", "replied", "booked", "won")) and (s["sent"], s["replied"], s["booked"], s["won"]) == (2, 1, 1, 1), str(s))

tmp = Path(tempfile.mkdtemp(prefix="zz-fw-"))
(tmp / "e1" / "send-lists").mkdir(parents=True)
(tmp / "e1" / "send-lists" / "2026-11-10.csv").write_text("name,website\nA,https://a.example\nB,https://b.example\n", encoding="utf-8")
import json  # noqa: E402
from dse import desklog, engines  # noqa: E402
(tmp / "e1" / "engine.json").write_text(json.dumps({"name": "E1", "path": "smb"}), encoding="utf-8")
for mod in (ES, desklog, engines):      # every module that looks for an engine folder points at the throwaway one
    mod.ENGINES = tmp
outcomes.rows_with_flags = lambda slug: []       # no taps yet: a brand new engine
st = ES.status_of("e1")
check("the status carries the number of send lists built, as a whole number", st["lists"] == 1 and isinstance(st["lists"], int) and st["rows"] == 2, str(st))
check("the status carries the results beside it", isinstance(st.get("results"), dict) and {"sent", "replied", "booked", "won"} <= set(st["results"]), str(st.get("results")))
check("a brand new engine reports zero taps, not nothing", st["results"]["sent"] == 0 and st["results"]["replied"] == 0)
src = (ROOT / "bridge" / "engines_sync.py").read_text(encoding="utf-8")
check("the status is written to the engine's own row through the token function", 'api.rpc("hq_engines_status"' in src)
print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
