"""Daily Brief sync (the runner starts it every 15 minutes): builds your brief and sends it to the Citadel Dashboard.

    python bridge/brief_sync.py          build the brief, send it if it changed (or is older than 6 hours)
    python bridge/brief_sync.py --dry    show it, send nothing

The brief is what to do first today, with the tool and the values for each (dse/brief.py). Only your own engines are read. Nothing is sent to anyone
but your own Citadel account, and nothing here sends a message. Prints nothing when there is nothing new, so the runner stays quiet.
Needs the one-time database update 20261119090000_hq_brief.sql (the sync says so if it is missing).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import brief  # noqa: E402
from dse.common import DATA  # noqa: E402

STATE = DATA / "brief-sync.json"
MAX_AGE_S = 6 * 3600


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def digest(b: dict) -> str:
    """What the member would notice changing: the moves and the money lines, not the time it was made."""
    core = {"d": b["date"], "m": [(m["engine"], m["do"], m["tool"], m["values"]) for m in b["moves"]], "e": [(e["slug"], e["received"], e["target"], e["sent_week"]) for e in b["engines"]]}
    return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()


def main(dry: bool = False) -> int:
    b = brief.build(top=5)
    brief.write(b)
    if dry:
        print(brief.render(b))
        return 0
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    d = digest(b)
    if st.get("digest") == d and time.time() - st.get("at", 0) < MAX_AGE_S:
        return 0
    r = _runner()
    try:
        r.Api(r.load_env()).rpc("hq_brief_push", {"p_brief": b}, tries=1)
    except RuntimeError as e:
        msg = str(e)
        print("brief sync: " + ("the database update 20261119090000_hq_brief.sql has not been run yet (ask the super admin)" if "hq_brief_push" in msg else msg[:160]))
        return 1
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"digest": d, "at": time.time()}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main("--dry" in sys.argv))
