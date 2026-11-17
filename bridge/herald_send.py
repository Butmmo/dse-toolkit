"""Herald sender: one pass of the sending engine (see dse/herald_send.py).

The runner runs this every minute in the background (catalog.json "periodic"). It sends only emails of campaigns you STARTED in Citadel, inside their windows and limits, and reads your
mailboxes for replies, bounces and unsubscribes from your own leads. Stop it any time with: python dse.py herald pause. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))


def main():
    import herald_sync
    from dse import herald_send
    s = herald_send.run_pass(herald_sync._api(), out=lambda *a: print(*a))
    if s["sent"] or s["events"] or s.get("answers"):
        print(f"herald send: sent {s['sent']}, answers {s.get('answers', 0)}, events {s['events']}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"herald send: {e}")
