"""Background helper (the runner starts it every few hours): writes a suggested monthly goal for each engine that has none for the month ahead.

    python bridge/goal_sync.py

It only writes engines/<slug>/next-goal.md (the suggestion with the working shown). It never changes a goal: you apply one with
python dse.py goal <engine> --apply. Prints nothing when there is nothing new, so the runner stays quiet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dse import goals  # noqa: E402

if __name__ == "__main__":
    for slug in goals.write_all():
        pass
