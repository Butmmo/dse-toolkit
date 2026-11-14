"""How-to guide for the GTM stack: Clay, HubSpot, Sales Navigator, Apollo, Instantly, n8n, Lemlist, and the whole GTM system.

    python howto/howto.py "enrich my list with emails in clay"
    python howto/howto.py "import contacts into hubspot"
    python howto/howto.py --list            every recipe

Recipes live in recipes.json next to this file: add or fix one any time (short steps, one action each).
Free: plain word matching, no AI. Also runs from Citadel (HQ Tools, How to do it).
"""
import json
import re
import sys
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "recipes.json").read_text(encoding="utf-8"))
STOP = {"the", "a", "an", "and", "to", "in", "on", "of", "my", "me", "i", "how", "do", "want", "can", "with", "for", "into", "it"}


def words(s):
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP}


def main():
    q = " ".join(sys.argv[1:]).strip()
    if not q or q == "--list":
        for r in DATA["recipes"]:
            print(f"[{r['app']}] {r['title']}")
        return
    ws = words(q)
    aliases = {"navigator": "salesnav", "linkedin": "salesnav", "salesnav": "salesnav", "clay": "clay", "hubspot": "hubspot",
               "apollo": "apollo", "instantly": "instantly", "n": "n8n", "lemlist": "lemlist", "gtm": "gtm"}
    if "n8n" in q.lower():
        ws.add("n8n")
    aliases.update({"ghl": "gohighlevel", "gohighlevel": "gohighlevel", "klaviyo": "klaviyo", "descript": "descript", "capcut": "capcut", "vapi": "vapi"})
    app = next((aliases[w] for w in ("navigator", "salesnav", "clay", "hubspot", "apollo", "instantly", "lemlist", "ghl", "gohighlevel",
                                     "klaviyo", "descript", "capcut", "vapi") if w in ws), None)
    if "n8n" in q.lower():
        app = "n8n"
    scored = []
    for r in DATA["recipes"]:
        if app and r["app"] != app:
            continue
        kw = words(r["keywords"] + " " + r["title"])
        score = len(ws & kw) + 2 * len(ws & words(r["title"]))
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        print("No recipe matches that yet. Try other words, or add a recipe to howto/recipes.json.")
        return
    for score, r in scored[:2]:
        print(f"\n{r['app'].upper()}: {r['title']}  (steps last checked {r['checked']})")
        for i, s in enumerate(r["steps"], 1):
            print(f"  {i}. {s}")
        for t in r.get("tips", []):
            print(f"  Tip: {t}")
    print("\nMenus move: if a step doesn't match your screen, tell HQ and the recipe gets updated.")


if __name__ == "__main__":
    main()
