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

def progress():
    """The member's own progress summary: the same files progress_push.py sends to Citadel."""
    for root in (H.parents[1], H.parents[0]):
        f = root / "_memory-vault" / "DAILY-CONTEXT.md"
        if f.exists():
            return f.read_text(encoding="utf-8")[:12000]
    return ""


def from_progress(q):
    """Answer 'what am I doing / next move / blockers' and match other words against the progress lines."""
    md, ws = progress(), w(q)
    if not md:
        return None
    lines = [l.strip() for l in md.splitlines() if l.strip().startswith(("-", "|", "**", "###"))]
    if ws & {"next", "doing", "progress", "where", "today", "blocker", "blockers", "stuck", "summary", "status"}:
        keep = [l for l in lines if l.startswith(("###", "**", "-"))][:30]
        return "Where you are (from your HQ progress):\n" + "\n".join(keep)
    return None


import base64, os, urllib.request
MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:1b")   # light, text only; gemma3:4b also reads images


PREFIX = chr(10) * 2 + "My HQ progress summary:" + chr(10)
ENGINE = ""   # set by --engine: an engine folder name, its README and latest handover note are added as context


def engine_context(folder):
    """README and newest handover note of one HQ engine folder (plain folder names only)."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", folder or ""):
        return ""
    root = H.parents[1]
    out = []
    # A member's own engine (made in Citadel: HQ Tools > My engines) lives in the toolkit's engines/<slug>/.
    for tk in (H.parent, H.parents[1] / "dse-toolkit"):
        cfg = tk / "engines" / folder / "engine.json"
        if cfg.is_file():
            out.append("Engine settings (" + folder + "):" + chr(10) + cfg.read_text(encoding="utf-8", errors="ignore")[:3000])
            lists = sorted((tk / "engines" / folder / "send-lists").glob("*.csv")) if (tk / "engines" / folder / "send-lists").is_dir() else []
            out.append(str(len(lists)) + " send lists built so far" + (", newest " + lists[-1].name if lists else "") + ".")
            return (chr(10) * 2).join(out)
    rd = root / folder / "README.md"
    if rd.is_file():
        out.append("Engine README (" + folder + "):" + chr(10) + rd.read_text(encoding="utf-8", errors="ignore")[:3500])
    notes = root / "_collected-copies" / "session-handover-notes"
    key = folder.split("-", 2)[-1] if folder.startswith("engine-") else folder
    hits = sorted((f for f in notes.glob("*.md") if key in f.name), reverse=True) if notes.is_dir() else []
    if hits:
        out.append("Latest handover (" + hits[0].name + "):" + chr(10) + hits[0].read_text(encoding="utf-8", errors="ignore")[:2500])
    return (chr(10) * 2).join(out)


def ollama(q, image=None):
    """Free local AI through Ollama (localhost:11434). Returns None if Ollama isn't running."""
    ctx = engine_context(ENGINE)
    msg = {"role": "user", "content": q + (chr(10) * 2 + ctx if ctx else "") + (PREFIX + progress()[:6000] if progress() else "")}
    if image:
        msg["images"] = [base64.b64encode(Path(image).read_bytes()).decode()]
    sys_txt = "You are HQ chat for a DBI student: short, practical answers on selling, freelancing, tools and simple thinking."
    body = json.dumps({"model": MODEL, "stream": False, "messages": [{"role": "system", "content": sys_txt}, msg]}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=300).read())["message"]["content"]
    except Exception:
        return None


def fetch_citadel_image(image_id):
    """A picture sent from the DBI-AI page: fetched once from Citadel with this PC's runner token, saved to a temp file."""
    import importlib.util, tempfile
    if not re.fullmatch(r"[0-9a-f-]{36}", image_id or ""):
        return None
    for runner in (H.parent / "bridge" / "runner.py", H.parents[1] / "bridge" / "runner.py"):
        if runner.exists():
            spec = importlib.util.spec_from_file_location("hq_runner", runner)
            r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
            b64 = r.Api(r.load_env()).rpc("hq_chat_image_get", {"p_id": image_id})
            if not b64:
                return None
            f = Path(tempfile.gettempdir()) / ("dbi-ai-" + image_id + ".jpg")
            f.write_bytes(base64.b64decode(b64))
            return str(f)
    return None


def reply(q, image=None):
    if image:
        out = ollama(q, image)
        return out or ("I could not read the picture. Your Ollama model must support images: install gemma3:4b "
                       "(ollama pull gemma3:4b), set OLLAMA_MODEL=gemma3:4b and restart the runner.")
    return ollama(q, image) or from_progress(q) or answer(q) + "\n\n(Built-in answer. For full AI chat, install Ollama: see the tool's help.)"


if __name__ == "__main__":
    args = sys.argv[1:]
    img = None
    if "--engine" in args:
        i = args.index("--engine"); ENGINE = args[i + 1]; del args[i:i + 2]
    if "--image-id" in args:
        i = args.index("--image-id"); img = fetch_citadel_image(args[i + 1]); del args[i:i + 2]
    if "--image" in args:
        i = args.index("--image"); img = args[i + 1]; del args[i:i + 2]
    if args:
        try:
            print(reply(" ".join(args), img))
        finally:
            if img and Path(img).name.startswith("dbi-ai-"):
                Path(img).unlink(missing_ok=True)
    else:
        while (q := input("You: ").strip()).lower() not in ("bye", "exit", ""):
            print(reply(q), "\n")
