"""Voices background helper (the runner starts it every 6 hours): keeps the thinkers library filled and current.

    python bridge/voices_sync.py

Runs `voices setup` for up to 4 minutes each time (the runner stops a helper at 5): it checks the sources not checked lately, repairs what it can, downloads the public-domain texts and sourced
quotations not downloaded yet, and reads what the living have published. It skips everything that is up to date, so most runs finish in seconds.
Only lawful, public sources are read (Project Gutenberg, Wikiquote, the figures' own feeds, Open Library); no social network is ever touched. Prints nothing when all is well.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import voices  # noqa: E402

if __name__ == "__main__":
    try:
        voices.setup("", 4)
    except Exception as e:          # the library is a nice-to-have: never let it make the runner noisy
        print(f"voices sync: {type(e).__name__}: {str(e)[:100]}")
