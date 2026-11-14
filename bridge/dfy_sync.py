"""Background helper (the runner starts it every ten minutes): pulls the students' filed DFY months from Citadel into the Cut Desk.

    python bridge/dfy_sync.py

Only runs when you turned it on: python dse.py cut sync <engine> --auto on  (the engine is saved in data/dfy-sync.json). It needs an admin runner
and the SQL file 20261118140000_dfy_bridge_payout_accounts.sql. It never sends anything. Prints nothing when there is nothing new, so the runner stays quiet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import dfysync  # noqa: E402

if __name__ == "__main__":
    slug = dfysync.auto_engine()
    if slug:
        try:
            out = dfysync.run(slug)
        except ValueError as e:
            print(f"DFY sync: {str(e)[:160]}")
            sys.exit(0)
        if "Nothing new" not in out:
            lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
            print("DFY sync: " + " | ".join(lines[:3])[:300])
