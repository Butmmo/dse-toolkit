"""CRM sync helper (the runner starts it every 5 minutes): sends the changed leads of the engines that have CRM sync ON to your BPS CRM.

    python bridge/crm_sync.py

Only engines you turned on (python dse.py crm on <engine>) are read. A stage only moves forward and your own notes and fields are never overwritten. Nothing is sent
to anyone but your own Citadel account. Prints nothing when there is nothing new. Needs the one-time database update 20261119100000_crm_sync.sql.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import crmsync  # noqa: E402

if __name__ == "__main__":
    try:
        out = crmsync.sync()
    except RuntimeError as e:
        msg = str(e)
        print("crm sync: " + ("the database update 20261119100000_crm_sync.sql has not been run yet (ask the super admin)" if "hq_crm_push" in msg else msg[:160]))
        sys.exit(1)
    if not out.startswith(("Your CRM is up to date", "No engine has CRM sync")):
        print(out.strip())
