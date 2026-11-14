"""Simple chat helper: selling, freelancing, planning, simple thinking, plus the how-to recipes.

    python _tools/chat/chat.py "a client says it is too expensive"
    python _tools/chat/chat.py            (talk until you type bye)
Free word matching, no AI. Add talks to guides.json.
"""
import json, re, sys
from pathlib import Path
H = Path(__file__).parent
G = json.loads((H / "guides.json").read_text(encoding="utf-8"))["guides"]
R = json.loads((H.parent / "howto" / "recipes.json").read_text(encoding="utf-8"))["recipes"]
STOP = {"the","a","an","and","to","in","on","of","my","me","i","how","do","is","it","what","can","for","with","you"}
w = lambda s: {x for x in re.findall(r"[a-z]+", s.lower()) if x not in STOP}

def answer(q):
    ws = w(q)
    best = max(((len(ws & w(g["keywords"] + " " + g["title"])), g) for g in G), key=lambda x: x[0])
    rec = max(((len(ws & w(r["keywords"] + " " + r["title"])), r) for r in R), key=lambda x: x[0])
    if best[0] == 0 and rec[0] == 0:
        return "I don't have a talk on that yet. Try: selling, objections, freelancing, planning your day, or a tool question."
    if best[0] >= rec[0]:
        return best[1]["title"] + ":\n" + "\n".join("- " + s for s in best[1]["say"])
    return rec[1]["title"] + ":\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(rec[1]["steps"], 1))

import base64, os, urllib.request
MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:1b")   # light, text only; gemma3:4b also reads images


def ollama(q, image=None):
    """Free local AI through Ollama (localhost:11434). Returns None if Ollama isn't running."""
    msg = {"role": "user", "content": q}
    if image:
        msg["images"] = [base64.b64encode(Path(image).read_bytes()).decode()]
    sys_txt = "You are HQ chat for a DBI student: short, practical answers on selling, freelancing, tools and simple thinking."
    body = json.dumps({"model": MODEL, "stream": False, "messages": [{"role": "system", "content": sys_txt}, msg]}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=300).read())["message"]["content"]
    except Exception:
        return None


def reply(q, image=None):
    return ollama(q, image) or answer(q) + "\n\n(Built-in answer. For full AI chat, install Ollama: see the tool's help.)"


if __name__ == "__main__":
    args = sys.argv[1:]
    img = None
    if "--image" in args:
        i = args.index("--image"); img = args[i + 1]; del args[i:i + 2]
    if args:
        print(reply(" ".join(args), img))
    else:
        while (q := input("You: ").strip()).lower() not in ("bye", "exit", ""):
            print(reply(q), "\n")
