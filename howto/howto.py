"""How to do it: step-by-step recipes for the GTM stack and the DSE paths (Clay, HubSpot, Sales Navigator, Apollo,
Instantly, Lemlist, n8n, Vapi, Cal.com, GoHighLevel, Klaviyo, Descript, CapCut, LinkedIn, sales calls, the whole GTM system).

    python howto/howto.py "enrich my list with emails in clay"
    python howto/howto.py --id clay-find-local-businesses       open one recipe by its id
    python howto/howto.py --list [app]                          every recipe (or one app)
    python howto/howto.py --apps                                the apps covered

Every recipe has: the goal, what you need first, steps (each with why it matters and what you should see),
mistakes to avoid, a "you are done when" check, and the official pages it was written from with the date it
was last checked. Menus and plans change: if a button differs on your screen, open the source link.
Free: plain word matching, no AI. The ask-anything chat also uses this file to ground its answers.
Recipes live in recipes.json next to this file (premium v2 format; the old one-line-step format still works).
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STOP = {"the", "a", "an", "and", "to", "in", "on", "of", "my", "me", "i", "how", "do", "want", "can", "with", "for", "into", "it",
        "is", "are", "what", "when", "where", "which", "this", "that", "from", "up", "set", "get", "use", "using", "make", "new", "or", "be", "we", "you", "your"}
SYN = {
    "csv": ["spreadsheet", "excel", "sheet", "file"], "spreadsheet": ["csv", "sheet", "excel"], "email": ["mail", "emails", "inbox"],
    "text": ["sms", "message"], "sms": ["text"], "lead": ["prospect", "contact"], "leads": ["prospects", "contacts"], "contact": ["lead", "person", "people"],
    "campaign": ["sequence", "outreach"], "sequence": ["campaign", "cadence"], "warmup": ["warm", "reputation", "deliverability"],
    "inbox": ["mailbox", "sender", "account"], "reply": ["response", "answer"], "price": ["pricing", "cost", "fee"], "automate": ["automation", "workflow"],
    "automation": ["workflow", "automate"], "workflow": ["automation", "flow"], "call": ["phone", "voice", "meeting"], "review": ["reviews", "reputation", "rating"],
    "booking": ["appointment", "calendar", "schedule"], "calendar": ["booking", "schedule"], "enrich": ["find", "fill", "lookup", "verify"],
    "import": ["upload", "bring", "load"], "export": ["download", "save"], "deal": ["opportunity", "pipeline"], "pipeline": ["deals", "stages", "board"],
    "podcast": ["episode", "audio"], "clip": ["short", "reel", "shorts"], "dns": ["spf", "dkim", "dmarc", "domain"], "spam": ["deliverability", "inbox", "spf", "dkim", "dmarc", "junk", "warmup"], "junk": ["spam", "deliverability"], "bounce": ["deliverability", "verify", "bounced"], "reject": ["rejection", "discouraged", "quit", "silence"],
    "procrastinate": ["focus", "distraction", "avoid", "delay", "start"], "procrastinat": ["focus", "distraction", "deep", "avoid", "delay", "start", "phone"], "focus": ["distraction", "deep", "concentrate"], "quit": ["discouraged", "rejection", "give"], "client": ["customer"],
    "free": ["unpaid", "scope"], "extra": ["scope", "change"], "paid": ["payment", "invoice", "payout"], "pay": ["payment", "invoice", "paid"],
}
ALIASES = {
    "clay": "clay", "hubspot": "hubspot", "apollo": "apollo", "instantly": "instantly", "lemlist": "lemlist", "n8n": "n8n", "vapi": "vapi",
    "cal": "cal.com", "calcom": "cal.com", "ghl": "gohighlevel", "gohighlevel": "gohighlevel", "highlevel": "gohighlevel", "klaviyo": "klaviyo",
    "descript": "descript", "capcut": "capcut", "linkedin": "linkedin", "navigator": "salesnav", "salesnav": "salesnav", "gtm": "gtm",
}


def stem(w: str) -> str:
    for suf in ("ations", "ation", "ions", "ion", "ing", "ness", "ly", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(s: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 1]


SYN_STEMMED: dict[str, list[str]] = {}
for _k, _v in SYN.items():
    SYN_STEMMED.setdefault(stem(_k), []).extend(_v)


def expand(ws: list[str]) -> set[str]:
    out = set(ws)
    for w in ws:
        out.update(stem(x) for x in SYN_STEMMED.get(w, SYN.get(w, [])))
    return out


def load() -> list[dict]:
    return json.loads((HERE / "recipes.json").read_text(encoding="utf-8"))["recipes"]


def step_text(s) -> str:
    return s if isinstance(s, str) else " ".join(str(s.get(k, "")) for k in ("do", "why", "check"))


def doc_fields(r: dict) -> list[tuple[str, float]]:
    """(text, weight) pairs for ranking: title and keywords count most, the body least."""
    return [(r.get("title", ""), 4.0), (r.get("keywords", ""), 3.0), (r.get("goal", "") + " " + r.get("summary", ""), 2.0), (r.get("app", ""), 2.0),
            (" ".join(step_text(s) for s in r.get("steps", [])), 1.0), (" ".join(r.get("principles", [])), 0.8)]


def rank(query: str, docs: list[dict], app: str | None = None, n: int = 3) -> list[tuple[float, dict]]:
    qw = tokens(query)
    if not qw:
        return []
    qset = expand(qw)
    pool = [d for d in docs if not app or d.get("app") == app] or docs
    fields = [[(set(tokens(t)), w) for t, w in doc_fields(d)] for d in pool]
    df: dict[str, int] = {}
    for fl in fields:
        seen = set().union(*(s for s, _ in fl))
        for w in seen:
            df[w] = df.get(w, 0) + 1
    out = []
    for d, fl in zip(pool, fields):
        score = 0.0
        for w in qset:
            idf = math.log(1 + len(pool) / (1 + df.get(w, 0)))
            direct = 1.0 if w in qw else 0.6                      # an exact word counts more than a synonym
            for s, wt in fl:
                if w in s:
                    score += wt * idf * direct
        if score:
            out.append((score, d))
    out.sort(key=lambda x: -x[0])
    return out[:n]


def detect_app(q: str) -> str | None:
    for w in re.findall(r"[a-z0-9.]+", q.lower()):
        if w in ALIASES:
            return ALIASES[w]
    return None


def render(r: dict, brief: bool = False) -> str:
    """The recipe as plain text. brief=True is the short form handed to the chat model as reference material."""
    L = [f"{r['app'].upper()}: {r['title']}"]
    if r.get("goal"):
        L.append(f"Goal: {r['goal']}")
    meta = [x for x in (r.get("level"), r.get("time")) if x]
    if meta:
        L.append("Level and time: " + ", ".join(meta))
    if r.get("plan_needed") and not brief:
        L.append("Plan or cost: " + r["plan_needed"])
    if r.get("before"):
        L.append("\nBefore you start:" + "".join(f"\n  - {b}" for b in r["before"]))
    L.append("\nSteps:")
    for i, s in enumerate(r["steps"], 1):
        if isinstance(s, str):
            L.append(f"  {i}. {s}")
            continue
        L.append(f"  {i}. {s['do']}")
        if s.get("why") and not brief:
            L.append(f"     Why: {s['why']}")
        if s.get("check"):
            L.append(f"     You should see: {s['check']}")
    for t in r.get("tips", []):
        L.append(f"  Tip: {t}")
    if r.get("mistakes"):
        L.append("\nMistakes to avoid:" + "".join(f"\n  - {m}" for m in r["mistakes"]))
    if r.get("done_when"):
        L.append("\nYou are done when:" + "".join(f"\n  [ ] {m}" for m in r["done_when"]))
    if r.get("free_alternative"):
        L.append(f"\nFree alternative: {r['free_alternative']}")
    if not brief:
        if r.get("related"):
            L.append("Related: " + ", ".join(r["related"]) + "  (open with: howto.py --id <id>)")
        if r.get("unverified"):
            L.append("\nNot confirmed on the official page (check these on your screen): " + "; ".join(r["unverified"]))
        src = r.get("sources") or []
        L.append((f"\nWritten from official pages, last checked {r.get('checked', '?')}" if src else f"\nSteps last checked {r.get('checked', '?')}")
                 + (f" (confidence: {r['confidence']})" if r.get("confidence") else "") + ".")
        for u in src:
            L.append(f"  Source: {u}")
        L.append("Menus and plans move. If a step does not match your screen, open the source page above or tell HQ so the recipe is updated.")
    return "\n".join(L)


def main() -> None:
    args = sys.argv[1:]
    R = load()
    if not args or args[0] == "--apps":
        apps: dict[str, int] = {}
        for r in R:
            apps[r["app"]] = apps.get(r["app"], 0) + 1
        print("Apps covered: " + ", ".join(f"{a} ({n})" for a, n in sorted(apps.items())))
        print('Ask like: "enrich my list with emails in clay" or "set up a deal pipeline in hubspot".')
        return
    if args[0] == "--list":
        for r in R:
            if len(args) < 2 or r["app"] == args[1]:
                print(f"[{r['app']}] {r.get('id', '')}  {r['title']}")
        return
    if args[0] == "--id" and len(args) > 1:
        hit = next((r for r in R if r.get("id") == args[1]), None)
        print(render(hit) if hit else f"No recipe with id {args[1]}. Run --list to see them.")
        return
    q = " ".join(args).strip()
    app = detect_app(q)
    hits = rank(q, R, app, 4)
    if not hits:
        print("No recipe matches that yet. Try other words, or name the tool (clay, hubspot, instantly, n8n ...). Run --list to see every recipe.")
        return
    print(render(hits[0][1]))
    rest = [r for s, r in hits[1:] if s >= hits[0][0] * 0.45]
    if rest:
        print("\nAlso relevant:")
        for r in rest[:3]:
            print(f"  - {r['title']}  (open: howto.py --id {r.get('id', '?')})")


if __name__ == "__main__":
    main()
