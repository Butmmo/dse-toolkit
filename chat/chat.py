"""HQ chat: ask anything about selling, freelancing, planning, thinking, or any tool in the stack.

    python chat/chat.py "a client says it is too expensive"
    python chat/chat.py "how do I warm up my instantly inboxes" --engine engine-a-outbound
    python chat/chat.py                         (talk until you type bye)

How it answers (best available, in this order):
  1. Claude, if you set your own ANTHROPIC_API_KEY (and `pip install anthropic`): the strongest answers. Your question
     and the matching library material are sent to Anthropic; your progress files are sent only if you ask about them.
  2. Your own free Ollama model on this PC (OLLAMA_MODEL, else the best model installed, gemma3:4b before gemma3:1b).
  3. The built-in library alone (guides.json and ../howto/recipes.json), shown in full.
In every case the answer is grounded in the library: researched guides and step-by-step recipes with sources.
"""
import base64, importlib.util, json, os, re, sys, urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent
NL = chr(10)
def _pick_model():
    """Which Ollama model to use and why (ollama_model.py): the OLLAMA_MODEL setting, even one set after the runner started, else the best installed."""
    try:
        spec = importlib.util.spec_from_file_location("hq_ollama_model", H / "ollama_model.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.pick()
    except Exception:
        return os.environ.get("OLLAMA_MODEL", "gemma3:1b"), "the default"


OLLAMA_MODEL, MODEL_WHY = _pick_model()
CLAUDE_MODEL = os.environ.get("HQ_CHAT_CLAUDE_MODEL", "claude-opus-5-5")
ENGINE = ""   # set by --engine: an HQ engine folder or one of your own engines (HQ Tools > My engines)


def _load_howto():
    spec = importlib.util.spec_from_file_location("hq_howto", H.parent / "howto" / "howto.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOW = _load_howto()
RECIPES = HOW.load()
GUIDES = json.loads((H / "guides.json").read_text(encoding="utf-8"))["guides"]


# ------------------------------------------------------------------ the library

def render_guide(g, brief=False):
    L = [g["title"], g.get("summary", "")]
    if g.get("principles"):
        L.append(NL + "Core ideas:" + "".join(NL + "  - " + x for x in g["principles"]))
    if g.get("steps"):
        L.append(NL + "Steps:" + "".join(f"{NL}  {i}. {x}" for i, x in enumerate(g["steps"], 1)))
    say = g.get("say") or []
    if say:
        L.append(NL + "What to say:" + "".join(NL + "  - " + x for x in say))
    if g.get("example") and not brief:
        L.append(NL + "Example: " + g["example"])
    if g.get("mistakes"):
        L.append(NL + "Mistakes to avoid:" + "".join(NL + "  - " + x for x in g["mistakes"]))
    if g.get("practice") and not brief:
        L.append(NL + "Practice today: " + g["practice"])
    if g.get("sources") and not brief:
        L.append(NL + "Based on: " + "; ".join(g["sources"]))
    return NL.join(x for x in L if x)


MIN_SCORE = 4.0


def retrieve(q, n_guides=2, n_recipes=2):
    """Best matching guides and recipes for the question, with their scores."""
    app = HOW.detect_app(q)
    g, r = HOW.rank(q, GUIDES, None, n_guides), HOW.rank(q, RECIPES, app, n_recipes)
    r = [x for x in r if app or x[0] >= 22]                   # a tool recipe must be named or clearly relevant
    top = max([x[0] for x in g + r] or [0])
    keep = lambda lst: [x for x in lst if x[0] >= max(MIN_SCORE, 0.4 * top)]  # drop weak matches next to a strong one
    return keep(g), keep(r)


def material(q, limit=7000):
    """Reference text for the model: the strongest matches first, trimmed to fit."""
    g, r = retrieve(q)
    parts, used = [], 0
    for score, d in sorted(g + r, key=lambda x: -x[0]):
        if score < MIN_SCORE or used >= limit:
            continue
        text = HOW.render(d, brief=True) if "app" in d else render_guide(d, brief=True)
        text = text[: limit - used]
        parts.append(("RECIPE" if "app" in d else "GUIDE") + ": " + text)
        used += len(text)
    return (NL * 2).join(parts)


# ------------------------------------------------------------------ context about the student

def progress():
    """The member's own progress summary: the same files progress_push.py sends to Citadel."""
    for root in (H.parents[1], H.parents[0]):
        f = root / "_memory-vault" / "DAILY-CONTEXT.md"
        if f.exists():
            return f.read_text(encoding="utf-8")[:12000]
    return ""


STATUS_WORDS = {"next", "doing", "progress", "where", "today", "blocker", "blockers", "stuck", "summary", "status", "working", "priority", "priorities"}


def asks_about_status(q):
    return bool(set(re.findall(r"[a-z]+", q.lower())) & STATUS_WORDS)


def from_progress(q):
    md = progress()
    if not md or not asks_about_status(q):
        return None
    lines = [l.strip() for l in md.splitlines() if l.strip().startswith(("-", "|", "**", "###"))]
    keep = [l for l in lines if l.startswith(("###", "**", "-"))][:30]
    return "Where you are (from your HQ progress):" + NL + NL.join(keep)


def engine_context(folder):
    """A member's own engine (Citadel: HQ Tools > My engines) or an HQ engine folder: its settings, README and latest note."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", folder or ""):
        return ""
    root = H.parents[1]
    out = []
    for tk in (H.parent, H.parents[1] / "dse-toolkit"):
        cfg = tk / "engines" / folder / "engine.json"
        if cfg.is_file():
            raw_cfg = cfg.read_text(encoding="utf-8", errors="ignore")
            try:
                c = json.loads(raw_cfg)
            except ValueError:
                c = {}
            if c.get("purpose") or c.get("ai_context"):      # a custom engine: its purpose and the student's instructions come first
                out.append("This is a custom engine. Its purpose: " + str(c.get("purpose", "")) + NL
                           + "How the student wants you to help with it: " + str(c.get("ai_context", "(no special instructions)")))
            out.append("Engine settings (" + folder + "):" + NL + raw_cfg[:3000])
            sl = tk / "engines" / folder / "send-lists"
            lists = sorted(sl.glob("*.csv")) if sl.is_dir() else []
            out.append(str(len(lists)) + " send lists built so far" + (", newest " + lists[-1].name if lists else "") + ".")
            return (NL * 2).join(out)
    rd = root / folder / "README.md"
    if rd.is_file():
        out.append("Engine README (" + folder + "):" + NL + rd.read_text(encoding="utf-8", errors="ignore")[:3500])
    notes = root / "_collected-copies" / "session-handover-notes"
    key = folder.split("-", 2)[-1] if folder.startswith("engine-") else folder
    hits = sorted((f for f in notes.glob("*.md") if key in f.name), reverse=True) if notes.is_dir() else []
    if hits:
        out.append("Latest handover (" + hits[0].name + "):" + NL + hits[0].read_text(encoding="utf-8", errors="ignore")[:2500])
    return (NL * 2).join(out)


# ------------------------------------------------------------------ the prompt

SYSTEM = """You are HQ, the senior mentor inside D'Famocious Business Incubator. Your students are mostly Nigeria-based beginners building service businesses for US and UK clients, with little money and big ambition. Answer as the best expert in the world on their exact question would, while staying warm, plain and practical.

How to think before you answer (silently): work out what the student is really trying to achieve and what is blocking them; decide the single best approach for a beginner; check it against the reference material you are given; check it for honesty and risk. Then answer.

How to answer:
- Start with the direct answer or recommendation in one or two sentences.
- Then the exact steps, or the exact words to say (put scripts in quotes), in order. Be concrete: numbers, examples, names of things to click or look for only when the reference material or you are certain.
- Name the most common mistake, and what to do instead.
- End with ONE next action they can do today in under 30 minutes.
- Short paragraphs, plain English, no jargon without a one-line explanation, no filler, no emojis. Use a numbered list for steps. About 150 to 350 words unless the task truly needs more.

Rules you never break:
- Use the reference material first and add your own expert knowledge where it helps. If the reference material conflicts with what you know, prefer the material for tool menus and plans, and say what to double-check.
- Never invent a menu name, button, price, plan limit or feature of any tool. If you are not sure, describe what to look for and point to the tool's official help page.
- Be honest and ethical: no fake urgency, deception, spam, ghosting, income promises or shortcuts that break a platform's rules. For outreach, mention consent, a real sender identity and an easy opt-out when relevant.
- No legal, medical or personal financial advice beyond general information; say when a professional is needed.
- If the question is unclear, give your best answer for the most likely meaning and ask one short clarifying question at the end.
- Never use the long dash character. Use a colon or a hyphen."""


HISTORY = ""            # the earlier messages of this chat (the "context range" Citadel sends: the newest few, about 2,400 characters at most)
HISTORY_MAX = 2400


def build_user_message(q, limit=7000):
    ctx = engine_context(ENGINE)
    mat = material(q, limit)
    parts = []
    if mat:
        parts.append("REFERENCE MATERIAL (researched guides and recipes from the HQ library):" + NL + mat)
    if ctx:
        parts.append("THE STUDENT'S ENGINE:" + NL + ctx)
    if asks_about_status(q) and progress():
        parts.append("THE STUDENT'S HQ PROGRESS SUMMARY:" + NL + progress()[:5000])
    if HISTORY.strip():
        parts.append("EARLIER IN THIS CHAT (newest last; context only, so you can follow what the student means by 'it' or 'that'. Do not answer these again):" + NL + HISTORY.strip()[-HISTORY_MAX:])
    parts.append("QUESTION:" + NL + q)
    return (NL * 2).join(parts)


# ------------------------------------------------------------------ brains

def claude(q):
    """The strongest answer: Claude, only if the student set their own API key. Returns (text, note) or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:        # a key saved in Windows after this runner started: read it from there (no restart needed)
            spec = importlib.util.spec_from_file_location("hq_ollama_model", H / "ollama_model.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            saved = mod.user_setting("ANTHROPIC_API_KEY")
            if saved:
                os.environ["ANTHROPIC_API_KEY"] = saved
        except Exception:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return ("", "To use Claude here, run: pip install anthropic  (then ask again). Answering with the local model for now.")
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=CLAUDE_MODEL, max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",     # re-runs on a fallback model if a safety filter declines
            output_config={"effort": "high"},
            system=SYSTEM + NL + "You may use up to about 600 words when the question needs depth.",
            messages=[{"role": "user", "content": build_user_message(q)}])
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return (text, f"Answered with Claude ({resp.model}) using your own API key.") if text else None
    except Exception as e:      # wrong key, no credit, offline: fall through to the local model
        return ("", f"Claude was not available ({type(e).__name__}); answering with the local model.")


LAST = {"error": "", "partial": False, "seconds": 0}      # how the last local-model call went, for the answer's footer
OLLAMA_BUDGET_S = 420        # the page waits 7 minutes and the job limit is 10: stay inside both


def ollama(q, image=None, budget_s=None):
    """Free local AI through Ollama, streamed so that a slow PC still returns what was written when time runs out (marked as cut short).
    Returns the text, or None if Ollama gave nothing (LAST says why). Small CPUs get a smaller job: 4096 tokens of context, at most 500 new tokens."""
    import time
    LAST.update(error="", partial=False, seconds=0)
    budget = budget_s or OLLAMA_BUDGET_S
    msg = {"role": "user", "content": build_user_message(q, 3500)}
    if image:
        msg["images"] = [base64.b64encode(Path(image).read_bytes()).decode()]
    body = json.dumps({"model": OLLAMA_MODEL, "stream": True, "keep_alive": "30m", "options": {"num_ctx": 4096, "num_predict": 500, "temperature": 0.4},
                       "messages": [{"role": "system", "content": SYSTEM}, msg]}).encode()
    start, parts = time.time(), []
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=150) as r:
            for line in r:
                if time.time() - start > budget:
                    LAST["partial"] = True
                    break
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    LAST["error"] = str(obj["error"])[:120]
                    break
                parts.append((obj.get("message") or {}).get("content", ""))
                if obj.get("done"):
                    break
    except Exception as e:
        LAST["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    LAST["seconds"] = int(time.time() - start)
    text = "".join(parts).strip()
    if text:
        return text
    if not LAST["error"]:
        LAST["error"] = f"no answer within {int(budget)} seconds" if LAST["partial"] else "an empty answer"
    return None


def library_answer(q):
    """No AI available: show the best guide or recipe in full."""
    g, r = retrieve(q, 1, 1)
    best = max(g + r, key=lambda x: x[0], default=None)
    if not best or best[0] < MIN_SCORE:
        return ("I don't have a researched answer for that yet. Try asking about: selling and discovery calls, objections, cold messages, "
                "follow-ups, pricing and proposals, freelancing, international clients, planning your day, focus, or a specific tool "
                "(clay, hubspot, instantly, n8n ...). Install Ollama so HQ can reason about any question: see the tool's help.")
    d = best[1]
    return HOW.render(d) if "app" in d else render_guide(d)


def fetch_citadel_image(image_id):
    """A picture sent from the DBI-AI page: fetched once from Citadel with this PC's runner token, saved to a temp file."""
    import tempfile
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


def _guard(q):
    """A request to DO something this chat cannot do (see files, build, commit, push, send) gets a direct, honest answer before any model is asked."""
    try:
        spec = importlib.util.spec_from_file_location("hq_chat_guard", H / "guard.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.guard(q)
    except Exception:
        return None


MODES = ("auto", "library", "claude")


def installed_models():
    try:
        spec = importlib.util.spec_from_file_location("hq_ollama_model", H / "ollama_model.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.installed()
    except Exception:
        return []


def local_footer(chosen=False):
    where = "you chose it in DBI-AI" if chosen else f"chosen from {MODEL_WHY}"
    cut = f" It was cut short after {LAST['seconds']} seconds because this PC is slow with this model: pick a smaller model for faster answers, or ask a shorter question." if LAST["partial"] else ""
    took = f" Took {LAST['seconds']} seconds." if LAST["seconds"] >= 20 and not LAST["partial"] else ""
    return f"(Answered with your local model {OLLAMA_MODEL} ({where}), grounded in the HQ library.{took}{cut} A bigger model or your own Claude key gives deeper answers.)"


def library_reply(q, why):
    return (from_progress(q) or library_answer(q)) + NL * 2 + f"({why})"


def _answer(q, image=None, mode="auto"):
    """mode: auto (best available), library (the built-in guides and recipes only, no AI model), claude (your Anthropic key), or ollama:<model> (one installed model)."""
    global OLLAMA_MODEL, MODEL_WHY
    if not image:
        g = _guard(q)
        if g:
            return g + NL * 2 + "(Answered instantly by HQ's built-in rules: this chat only answers questions. It cannot see files, build, commit, push or send. No AI model was used.)"
    mode = (mode or "auto").strip()
    chosen = mode != "auto"
    if mode.startswith("ollama:"):
        want = mode[7:]
        have = installed_models()
        if want not in have:
            return (f"The model '{want}' is not installed on this PC (installed: {', '.join(have) or 'none found: is Ollama running?'}). Pick another in the model menu, or run: ollama pull {want}")
        OLLAMA_MODEL, MODEL_WHY = want, "you chose it in DBI-AI"
    elif mode not in MODES:
        return f"I do not know the model choice '{mode}'. Use the model menu in DBI-AI."
    if mode == "library":
        if image:
            return "Pictures need a model that can read them. Choose a local model that can (marked 'reads pictures' in the menu) or Automatic."
        return library_reply(q, "Answered from the built-in library because you chose that: the guides and recipes with sources, no AI model.")
    if image:     # pictures need a vision model on this PC
        if mode == "claude":
            return "Pictures are read by a local model in this version. Choose Automatic or a local model that reads pictures."
        out = ollama(q, image)
        return (out + NL * 2 + local_footer(chosen)) if out else ("I could not read the picture" + (f" ({LAST['error']})" if LAST["error"] else "") + ". Your Ollama model must support images: install gemma3:4b "
                                                                      "(ollama pull gemma3:4b), choose it in the model menu and try again.")
    note = ""
    if mode == "claude" or (mode == "auto" and not mode.startswith("ollama:")):
        c = claude(q)
        if c and c[0]:
            return c[0] + NL * 2 + "(" + c[1] + ")"
        if mode == "claude":
            why = c[1] if c else "Claude did not answer (it needs ANTHROPIC_API_KEY on this PC and: pip install anthropic)."
            return library_reply(q, why + " Here is the built-in library answer instead.")
        if c:
            note = NL * 2 + "(" + c[1] + ")"
    out = ollama(q)
    if out:
        return out + NL * 2 + local_footer(chosen) + note
    why = f"Ollama did not give an answer with {OLLAMA_MODEL} ({LAST['error'] or 'it is not running'}). This is the built-in library answer instead. Try a smaller model from the model menu, or a shorter question."
    return library_reply(q, why) + note


MENTORS = ("auto", "off", "only")


def _voices():
    """The Voices library (dse/voices.py), found next to this folder or in the DSE Toolkit; None when this install does not have it."""
    for root in (H.parent, H.parents[1] / "dse-toolkit"):
        if (root / "dse" / "voices.py").is_file():
            try:
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from dse import voices
                return voices
            except Exception:
                return None
    return None


def mentor_text(q, mentors):
    """Real passages from the Voices library beside the answer: when you ask for a mentor or a quote, or name someone ('what did Seneca say about anger'); 'only' is a pure
    mentor answer (no AI); 'off' never. Matching is by words, so it is never added to an ordinary answer unasked."""
    if mentors == "off":
        return ""
    v = _voices()
    if not v:
        return "The Voices library is not on this PC (it comes with the DSE Toolkit)." if mentors == "only" else ""
    try:
        if mentors == "only":
            return v.mentor_block(q, 3, only=True)
        return v.mentor_block(q, 2) if v.wants_mentor(q) else ""
    except Exception:
        return ""


def reply(q, image=None, mode="auto", mentors="auto"):
    """The answer (see _answer) plus, when wanted, mentor passages from the Voices library. mentors: auto (only if you ask for a mentor or name one), only (library passages, no AI), off."""
    mentors = mentors if mentors in MENTORS else "auto"
    if mentors == "only" and not image:
        return mentor_text(q, "only") + NL * 2 + "(Answered from the Voices library: no AI model was used.)"
    out = _answer(q, image, mode)
    if image or out.endswith("this chat only answers questions. It cannot see files, build, commit, push or send. No AI model was used.)"):
        return out
    blk = mentor_text(q, mentors)
    return out + NL * 2 + blk if blk else out


if __name__ == "__main__":
    args = sys.argv[1:]
    img = None
    mode = "auto"
    mentors = "auto"
    if "--history" in args:
        i = args.index("--history"); HISTORY = args[i + 1][:HISTORY_MAX]; del args[i:i + 2]
    if "--mentors" in args:
        i = args.index("--mentors"); mentors = args[i + 1]; del args[i:i + 2]
    if "--model" in args:
        i = args.index("--model"); mode = args[i + 1]; del args[i:i + 2]
    if "--engine" in args:
        i = args.index("--engine"); ENGINE = args[i + 1]; del args[i:i + 2]
    if "--image-id" in args:
        i = args.index("--image-id"); img = fetch_citadel_image(args[i + 1]); del args[i:i + 2]
    if "--image" in args:
        i = args.index("--image"); img = args[i + 1]; del args[i:i + 2]
    if args:
        try:
            print(reply(" ".join(args), img, mode, mentors))
        finally:
            if img and Path(img).name.startswith("dbi-ai-"):
                Path(img).unlink(missing_ok=True)
    else:
        while (q := input("You: ").strip()).lower() not in ("bye", "exit", ""):
            print(reply(q, None, mode, mentors), NL)
