"""The chat guardrail: this chat only ANSWERS. It cannot see files, build, commit, push, run or send anything.

A small local AI model (gemma3:1b) will happily pretend it did such a thing, which is worse than saying no. So before any model is asked,
a few plain rules spot a request for an ACTION and answer it directly (instantly, no model, nothing invented) with the HQ Tools that really do it.

    guard(question) -> the direct answer, or None when the question should go on to the AI

It only triggers when the person is telling the chat to DO something ("now build number 1 and commit it", "can you see my folder",
"send this email"), never on a question about how to do it ("how do I build an app?") or on a request to write or explain.
"""
from __future__ import annotations

import re

NL = chr(10)

# polite or lead-in words that may come before the real verb
LEAD = (r"(?:ok(?:ay)?|so|now|then|and|also|please|kindly|first|next|just|go ahead and|can you|could you|would you|will you|are you able to|"
        r"i want you to|i need you to|i would like you to|i'd like you to|i wish you would|you should|you must|let's|lets)")
VERBS = {
    "git": r"commit|push|merge|deploy|publish|ship|upload",
    "build": r"build|create|make|write|code|program|develop|implement|generate|scaffold|install|run|execute|set up|setup|fix|edit|change|update|delete|add|refactor|test",
    "send": r"send|email|e-mail|dm|text|message|post|tweet|share|reply to",
}
OBJECT = {
    "build": r"app|application|website|site|page|tool|dashboard|script|code|feature|bot|program|project|system|function|api|component|module|database|workflow|automation|number \d+|option \d+|item \d+",
    "pronoun": r"^\s*(?:it|this|that|them|everything)\s*(?:for me|now|today|please|out|up|too)?\s*[.!?]?\s*$",
}


def lead_then(verb_group: str) -> re.Pattern:
    return re.compile(rf"^\W*(?:{LEAD}\b[\s,:-]*)*({verb_group})\b(.*)$", re.I | re.S)


GIT_WORDS = re.compile(r"\b(commit|push|pull request|merge request|merge|github|repo|repository|branch|git)\b", re.I)
SEE = re.compile(r"\b(?:can|could|do|are)\s+you\s+(?:actually\s+|really\s+|even\s+)?(?:see|access|open|read|view|browse|look\s+(?:in|at|inside)|check|find)\b.{0,80}?"
                 r"\b(?:folder|folders|directory|file|files|repo|repository|pc|computer|laptop|drive|project|workspace|desktop|app|code)\b", re.I | re.S)
SEE2 = re.compile(r"\b(?:confirm|verify|check|tell me|make sure)\b[^.?!]{0,40}\byou\s+can\s+(?:see|access|open|read|view|find)\b", re.I)
SEE3 = re.compile(r"^\W*(?:" + LEAD + r"\b[\s,:-]*)*(?:look|check|open|read|find|go)\s+(?:in|at|inside|into|through|for)?\s*(?:the\s+|my\s+|our\s+)?(?:folder|file|files|repo|repository|directory|desktop|project)\b", re.I)
FILEISH = re.compile(r"\b(folder|directory|file|files|repo|repository|project|code|pc|computer|workspace)\b", re.I)
QUESTION_START = re.compile(r"^\W*(?:how|what|why|which|when|where|who|is|are|does|do|should|explain|tell me how|show me how|teach|help me understand)\b", re.I)


def reply_for(kind: str) -> str:
    if kind == "git":
        return ("I can't commit, push or merge anything from this chat. I can only answer questions: I have no access to your files or to GitHub, "
                "so if I said I had done it, it would not be true." + NL + NL +
                "These HQ Tools really do it (HQ Tools, group Dev):" + NL +
                "1. Dev: let the AI make a change: an AI engineer edits the project on its own new branch, runs the tests and commits. It never pushes." + NL +
                "2. Dev: show the changes (git diff): read what changed before you keep it." + NL +
                "3. Dev: save a commit, then Dev: push to GitHub. Pushing is off until you switch it on at your PC once: python dse.py dev setup --github-user YOURNAME." + NL + NL +
                "Next action today: open HQ Tools, choose Dev: my workspaces, and see whether the project is there. If it is not, Dev: copy a GitHub repository here brings it in.")
    if kind == "build":
        return ("I can't build, write into a project or run code from this chat: I only answer questions, so I won't pretend to have made it." + NL + NL +
                "These HQ Tools really do it:" + NL +
                "1. App Builder: build any website or app (HQ Tools, group Build) for a new website or app from a starting point." + NL +
                "2. Dev: start a new project: a starter in JavaScript, TypeScript, Python, Java, Kotlin, C#, C, C++, Dart, Flutter, Go, Rust or PowerShell, with a test and git." + NL +
                "3. Dev: let the AI make a change: describe the change in a sentence or two and an AI engineer edits the code on a new branch and runs the tests." + NL + NL +
                "I can help you plan it first: tell me what it should do and who it is for, and I will help you write the one-sentence instruction to give the AI engineer." + NL +
                "Next action today: write that one sentence (what it should do, for whom, how you will know it works).")
    if kind == "files":
        return ("No. I can't see your folders, files or PC. I only see what you type here, plus the HQ library and a summary of your engine." + NL + NL +
                "These HQ Tools show what is really there (group Dev): Dev: my workspaces lists your project folders, Dev: show the files lists one, "
                "Dev: read a file opens a file, and Dev: search the code finds a word in it." + NL + NL +
                "Next action today: run Dev: my workspaces, and tell me what it lists if you want help with it.")
    if kind == "send":
        return ("I can't send, post or email anything for you, and I never will: you press send yourself, which keeps your accounts safe." + NL + NL +
                "What I can do: write the message here, make it shorter, warmer or clearer, and prepare the follow-up. For an engine's messages, "
                "the Send Desk shows each one ready to copy; you send it and tap Sent so your results stay true." + NL + NL +
                "Next action today: paste the message you plan to send and ask me to tighten it.")
    return ""


def guard(q: str) -> str | None:
    """The direct answer for a request to DO something this chat cannot do, else None (let the AI answer)."""
    text = (q or "").strip()
    if not text:
        return None
    low = text.lower()
    # can you see / access my files
    if SEE.search(low) or SEE2.search(low) or SEE3.match(low):
        return reply_for("files")
    if QUESTION_START.match(low) and not re.match(r"^\W*(?:" + LEAD + r"\b[\s,:-]*)+", low):
        return None            # "how do I build an app?" is a question for the AI, not a request to do it
    # an instruction: lead-in words, then an action verb. Look at each sentence and clause ("... build number 1 and commit it to our repo").
    parts = re.split(r"(?:[.!?;]\s+|\s+and\s+|\s+then\s+|,\s+)", low)
    kinds = []
    for part in [low] + parts:
        for kind in ("git", "build", "send"):
            m = lead_then(VERBS[kind]).match(part.strip())
            if not m:
                continue
            rest = m.group(2)
            if kind == "git" and not (GIT_WORDS.search(rest) or re.search(r"\b(it|them|this|that|changes|work|everything|number \d+)\b", rest)):
                continue
            if kind == "build" and not (re.search(OBJECT["build"], rest) or FILEISH.search(rest) or re.match(OBJECT["pronoun"], rest)):
                continue
            if kind == "send" and not re.search(r"\b(this|that|it|them|him|her|my|the|a|an|to|on|via)\b", rest):
                continue
            kinds.append(kind)
    # a plain instruction to the chat itself is fine: "write me a script for a call", "write a message to...", "draft", "explain"
    if kinds:
        asks_for_text = re.match(r"^\W*(?:" + LEAD + r"\b[\s,:-]*)*(?:write|draft|make|create|generate|give)\s+(?:me\s+|us\s+)?(?:a|an|the|some|my)?\s*"
                                 r"(?:\w+\s+){0,3}?(?:script|message|email|reply|response|answer|list|plan|outline|template|summary|checklist|pitch|proposal|post|caption|bio|headline|subject line|offer)\b", low)
        if asks_for_text and "git" not in kinds and not GIT_WORDS.search(low):
            return None
        for k in ("git", "build", "send"):          # the most specific first: committing beats building
            if k in kinds:
                return reply_for(k)
    return None
