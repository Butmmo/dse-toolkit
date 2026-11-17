"""Herald sync: your mailbox settings from Citadel onto this PC, and each mailbox's status back.

    python bridge/herald_sync.py          pull mailbox settings into data/herald/mailboxes.json, report status back
    python bridge/herald_sync.py --dry    show what would change

The runner runs this every minute in the background (catalog.json "periodic"). Only SETTINGS come from Citadel (address, mail servers, limits): a mailbox's password is never in
Citadel and is never sent anywhere. What goes back is only: is a password set on this PC, and did the last test work. Stdlib only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _api():
    r = _runner()
    return r.Api(r.load_env())


def push_status(api=None) -> int:
    from dse import herald
    from dse import herald_graph
    api = api or _api()
    status = herald.status_payload(signed=herald_graph.signed_in_ids(api))
    if not status:
        return 0
    return int(api.rpc("hq_herald_status", {"p_status": status}) or 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    from dse import herald
    api = _api()
    rows = api.rpc("hq_herald_pull", {}) or []
    old = herald.load_mailboxes()
    changed = json.dumps(rows, sort_keys=True) != json.dumps(old, sort_keys=True)
    if a.dry:
        print(f"{len(rows)} mailbox(es) in Citadel, settings {'would change' if changed else 'unchanged'}")
        return
    if changed:
        herald.save_mailboxes(rows)
    pushed = push_status(api)
    if changed:
        print(f"herald sync: {len(rows)} mailbox(es) from Citadel; status sent for {pushed}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"herald sync: {e}")
