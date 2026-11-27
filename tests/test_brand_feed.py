"""Brand kit feed checks: the App Builder's colour field must be able to start empty, so the
Presence brand colour (filled in by Citadel) can flow in, with a typed colour as the override.
Run: python tests/test_brand_feed.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
catalog = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
fails = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


tool = catalog["tools"]["app.build"]
color = next(f for f in tool["fields"] if f["name"] == "color")
check("the App Builder colour field is optional, so it can be left to the brand kit", color.get("required") is False)
check("the colour field carries no fixed default, so defaults never mask the brand colour", "default" not in color)
check("the colour field still validates a typed colour as hex", color.get("pattern") == "^#[0-9a-fA-F]{6}$")
check("the colour field explains the brand feed and the override", "brand kit" in str(color.get("help", "")).lower() and "override" in str(color.get("help", "")).lower())
check("the colour still reaches the builder as --color", any(a.get("opt") == "--color" and a.get("field") == "color" for a in tool["args"]))

print("FAILED: " + str(len(fails))) if fails else print("ALL PASS")
sys.exit(1 if fails else 0)
