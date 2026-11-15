"""One-off generator: adds the Voices library tools to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dse.voices_")]:
    T.pop(k)

STRATA = [("any", "All"), ("wisdom", "Wisdom and philosophy"), ("empowerment", "Human empowerment and psychology"), ("structure", "Structure, systems and thinking"), ("sales", "Sales and persuasion"), ("finance", "Financial development")]
PATHS = [("any", "All"), ("smb", "SMB Marketing and Optimization"), ("ascent", "High-ticket sales (The Ascent)"), ("revenue", "Revenue and customer growth"), ("broadcast", "Broadcast"), ("authority", "Authority and personal brand"),
         ("gtm", "GTM engineering"), ("voiceai", "AI voice receptionist"), ("automation", "AI automation"), ("ministry", "Ministry")]
ch = lambda xs: [{"value": a, "label": b} for a, b in xs]  # noqa: E731
FIG_ANY = {"name": "figure", "label": "Whose words", "type": "choice", "required": True, "default": "any", "choices_from": "figures", "choices": []}
FIG = {"name": "figure", "label": "Figure", "type": "choice", "required": True, "choices_from": "figure_ids", "choices": []}
STR = {"name": "stratum", "label": "Area", "type": "choice", "required": True, "default": "any", "choices": ch(STRATA)}
PTH = {"name": "path", "label": "Path", "type": "choice", "required": True, "default": "any", "choices": ch(PATHS)}


def tool(label, help_, args, fields, outputs=None, minutes=1):
    t = {"label": label, "group": "Voices", "help": help_, "script": "dse.py", "args": [{"lit": "voices"}] + args, "fields": fields, "timeout_min": minutes}
    if outputs:
        t["outputs"] = outputs
    return t


T["dse.voices_ask"] = tool("Voices: ask the library", "Type a question or a topic and get the passages that answer it best, each with who said it and where (the book and section, or the Wikiquote source). Choose one figure, or an area, or a path, or everyone. Real words with real sources found by matching your own: no AI model writes or changes them, and nothing is made up. If a figure has not been fetched yet it says so. Nothing is sent.",
                           [{"lit": "ask"}, {"field": "question"}, {"opt": "--figure", "field": "figure"}, {"opt": "--stratum", "field": "stratum"}, {"opt": "--path", "field": "path"}, {"opt": "--n", "field": "n"}],
                           [{"name": "question", "label": "Your question or topic", "type": "text", "required": True, "max": 200}, FIG_ANY, STR, PTH,
                            {"name": "n", "label": "How many passages", "type": "int", "required": False, "min": 1, "max": 8, "default": 3}])
T["dse.voices_today"] = tool("Voices: a passage for today", "One passage for today from the library, chosen by the date and the area you pick, with its source. The same passage all day, a different one tomorrow. No AI model.",
                             [{"lit": "today"}, {"opt": "--stratum", "field": "stratum"}], [{**STR, "default": "wisdom", "choices": ch(STRATA[1:])}])
T["dse.voices_list"] = tool("Voices: the roster", "The figures in the library: 10 for each area (wisdom, empowerment, structure, sales, financial) and 7 for each path, with what each is known for and how many of their sources are checked and fetched. Filter by area or path.",
                            [{"lit": "list"}, {"opt": "--stratum", "field": "stratum"}, {"opt": "--path", "field": "path"}], [STR, PTH])
T["dse.voices_show"] = tool("Voices: one figure", "Who they are, what they are known for, each source and whether it has been checked, how much of their library is fetched, your own notes, and the latest from their own feeds. Social profiles are shown as links only.",
                            [{"lit": "show"}, {"field": "figure"}], [FIG])
T["dse.voices_verify"] = tool("Voices: check a figure's sources", "Checks each source for a figure live (the book is on Project Gutenberg, the Wikiquote page exists, the feed answers, the books are real) and records the result. Nothing is fetched or used until its source is checked here. A failed source can be fixed in the roster and checked again.",
                              [{"lit": "verify"}, {"field": "figure"}], [FIG], minutes=3)
T["dse.voices_fetch"] = tool("Voices: fetch a figure's library", "Downloads and indexes the figure's checked public-domain books (Project Gutenberg) and sourced quotations (Wikiquote, CC BY-SA), so Ask can find them. Books still in copyright are not copied: only their titles are listed. Run Check sources first.",
                             [{"lit": "fetch"}, {"field": "figure"}], [FIG], minutes=5)
T["dse.voices_update"] = tool("Voices: what is new from the living", "For living figures with a checked feed (their blog or newsletter, their official YouTube channel, their podcast): lists what they have published since the last time, with the date, the link and a short description. You follow the link to read or watch it. Leave the figure on Everyone to check them all. Social networks are never fetched.",
                              [{"lit": "update"}, {"field": "figure"}], [{**FIG_ANY}], minutes=5)
T["dse.voices_note"] = tool("Voices: add your own note", "Add a line you read or heard (from a book in copyright, a talk, a video) to a figure's library, with where it comes from. It is marked as your note wherever it appears, never as their words, and a note without a source is not kept.",
                            [{"lit": "note"}, {"field": "figure"}, {"opt": "--text", "field": "text"}, {"opt": "--source", "field": "source"}],
                            [FIG, {"name": "text", "label": "The line or idea (8 to 1,200 characters)", "type": "text", "required": True, "max": 1200},
                             {"name": "source", "label": "Where from (book and page, video and time, talk and date)", "type": "text", "required": True, "max": 160}])
T["dse.voices_setup"] = tool("Voices: set up the library", "Makes the library work with one click. For every figure it checks each source, repairs what can be repaired (another feed address, the right Project Gutenberg book, a simpler book title), downloads the public-domain texts and sourced quotations, and reads what the living have published. It can be run again and again: it skips what is up to date and carries on where it stopped. It tells you plainly what it could not fix and what to do. Only lawful public sources are used; no social network is read.",
                            [{"lit": "setup"}, {"field": "figure"}, {"opt": "--minutes", "field": "minutes"}],
                            [{**FIG_ANY}, {"name": "minutes", "label": "Stop after (minutes)", "type": "int", "required": False, "min": 1, "max": 28, "default": 25}], minutes=30)
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
