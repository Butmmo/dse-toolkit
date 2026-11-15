"""One-off generator: adds the Referral and Testimonial Desk tools to catalog.json. Safe to re-run (replaces the dse.proof_* entries)."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith("dse.proof")]:
    del T[k]
ENG = {"name": "engine", "label": "Engine", "type": "choice", "required": True, "choices_from": "engines", "choices": []}
ID = lambda label, pre: {"name": "item", "label": label, "type": "text", "required": True, "max": 12, "pattern": rf"^{pre}-\d{{3,4}}$"}  # noqa: E731
NAME = {"name": "who", "label": "Their name", "type": "text", "required": True, "max": 60, "pattern": r"^[A-Za-z][A-Za-z .'-]{1,59}$"}
NOTE = "Nothing is sent: you send every message yourself."


def tool(label, help_, args, fields):
    return {"label": label, "group": "My engines", "help": help_ + " " + NOTE, "script": "dse.py", "args": args, "fields": fields, "timeout_min": 1, "outputs": []}


T["dse.proof_due"] = tool("Proof Desk: who to ask, follow up or thank", "Shows who is at a good moment to ask for a testimonial and a referral (a client whose work is delivered, a DFY student at 6 and at 12 qualified months), who needs one gentle follow-up, and which referrals have not been thanked, each with the command to run.",
                          [{"lit": "proof"}, {"lit": "due"}, {"field": "engine"}], [ENG])
T["dse.proof_ask"] = tool("Proof Desk: draft a testimonial or referral request", "Writes a kind, optional request in your name: three easy questions for a testimonial and a referral ask, with how they would like their name shown and whether numbers may be used. A DFY student's request says it is separate from their DFY and that no changes nothing.",
                          [{"lit": "proof"}, {"lit": "ask"}, {"field": "engine"}, {"opt": "--who", "field": "who"}, {"opt": "--source", "field": "source"}, {"opt": "--kind", "field": "kind"}, {"flag": "--sent", "field": "sent"}],
                          [ENG, NAME, {"name": "source", "label": "About (client:acme-dental, student:ada-obi or manual)", "type": "text", "required": False, "max": 60, "pattern": r"^(manual|(client|student):[a-z0-9-]{1,40})$"},
                           {"name": "kind", "label": "Ask for", "type": "choice", "required": False, "default": "both", "choices": [{"value": "both", "label": "Testimonial and referral"}, {"value": "testimonial", "label": "Testimonial only"}, {"value": "referral", "label": "Referral only"}]},
                           {"name": "sent", "label": "I have already sent it", "type": "bool", "default": False}])
T["dse.proof_mark"] = tool("Proof Desk: mark an ask sent, answered, declined or closed", "Keeps the record straight so the desk knows who still needs a follow-up.",
                           [{"lit": "proof"}, {"lit": "mark"}, {"field": "engine"}, {"field": "item"}, {"opt": "--to", "field": "to"}],
                           [ENG, ID("Ask number (like ASK-001)", "ASK"), {"name": "to", "label": "Now", "type": "choice", "required": True, "default": "sent", "choices": [{"value": v, "label": v} for v in ("sent", "answered", "declined", "no-reply")]}])
T["dse.proof_quote"] = tool("Proof Desk: record what someone said, and what they agreed to", "Keeps their EXACT words and exactly what they agreed to: that you may use the text, how their name is shown (full, first or anonymous), whether the company and any numbers may be shown, and where (proposals, website, social, outreach). Without recorded consent the quote cannot be used anywhere, and you get the message to send them showing exactly how it would appear.",
                            [{"lit": "proof"}, {"lit": "quote"}, {"field": "engine"}, {"opt": "--who", "field": "who"}, {"opt": "--text", "field": "text"}, {"opt": "--role", "field": "role"}, {"opt": "--channel", "field": "channel"}, {"opt": "--ask", "field": "ask"},
                             {"opt": "--consent", "field": "consent"}, {"opt": "--consent-how", "field": "consent_how"}, {"opt": "--name", "field": "name"}, {"opt": "--company", "field": "company"}, {"opt": "--numbers", "field": "numbers"}, {"opt": "--scope", "field": "scope"}],
                            [ENG, NAME, {"name": "text", "label": "Their exact words (paste them)", "type": "text", "required": True, "max": 1200},
                             {"name": "role", "label": "Their role and business (optional)", "type": "text", "required": False, "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,.&'()/-]{0,79}$"},
                             {"name": "channel", "label": "Where you got it (for your records)", "type": "text", "required": False, "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ,.&'()/:-]{0,79}$"},
                             {"name": "ask", "label": "The ask it answers (optional, like ASK-001)", "type": "text", "required": False, "max": 12, "pattern": r"^ASK-\d{3,4}$"},
                             {"name": "consent", "label": "They agreed to my using it", "type": "choice", "required": False, "default": "no", "choices": [{"value": "yes", "label": "Yes, they agreed"}, {"value": "no", "label": "Not yet"}]},
                             {"name": "consent_how", "label": "How they agreed (for example: replied yes on WhatsApp, 15 Nov)", "type": "text", "required": False, "max": 160},
                             {"name": "name", "label": "How their name is shown", "type": "choice", "required": False, "default": "anonymous", "choices": [{"value": "full", "label": "Full name"}, {"value": "first", "label": "First name only"}, {"value": "anonymous", "label": "Anonymous"}]},
                             {"name": "company", "label": "May their role and business be shown", "type": "choice", "required": False, "default": "no", "choices": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
                             {"name": "numbers", "label": "May numbers they mention be used", "type": "choice", "required": False, "default": "no", "choices": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
                             {"name": "scope", "label": "Where it may be used (comma list: proposals,website,social,outreach)", "type": "text", "required": False, "max": 60, "pattern": r"^(proposals|website|social|outreach)(,(proposals|website|social|outreach)){0,3}$"}])
T["dse.proof_quotes"] = tool("Proof Desk: the quotes I may use", "Only approved, consented and not-withdrawn quotes, word for word, with the attribution THEY chose, and only the numbers that are in their own words or match your records. Everything else is listed with the reason it cannot be used.",
                             [{"lit": "proof"}, {"lit": "quotes"}, {"field": "engine"}, {"opt": "--scope", "field": "scope"}],
                             [ENG, {"name": "scope", "label": "For", "type": "choice", "required": False, "choices": [{"value": v, "label": v} for v in ("proposals", "website", "social", "outreach")]}])
T["dse.proof_withdraw"] = tool("Proof Desk: someone withdrew their quote", "Takes effect at once: the quote is never usable again, and Outreach Preflight blocks any message that still contains it. Remove it from anything already published or sent.",
                               [{"lit": "proof"}, {"lit": "withdraw"}, {"field": "engine"}, {"field": "item"}, {"opt": "--reason", "field": "reason"}],
                               [ENG, ID("Quote number (like Q-001)", "Q"), {"name": "reason", "label": "Why (optional)", "type": "text", "required": False, "max": 120}])
T["dse.proof_refer"] = tool("Proof Desk: record a referral", "Records who introduced whom, so you can write to them this week, mention who suggested you, and thank the referrer (a thank-you draft is shown).",
                            [{"lit": "proof"}, {"lit": "refer"}, {"field": "engine"}, {"opt": "--from", "field": "from_who"}, {"opt": "--referred", "field": "referred"}, {"opt": "--contact", "field": "contact"}],
                            [ENG, {"name": "from_who", "label": "Who referred them", "type": "text", "required": True, "max": 60, "pattern": r"^[A-Za-z][A-Za-z .'-]{1,59}$"},
                             {"name": "referred", "label": "Who they referred (name or business)", "type": "text", "required": True, "max": 80, "pattern": r"^[A-Za-z0-9][A-Za-z0-9 .,&'()-]{1,79}$"},
                             {"name": "contact", "label": "Their contact (optional)", "type": "text", "required": False, "max": 120}])
T["dse.proof_thanked"] = tool("Proof Desk: I thanked the referrer", "Takes the referral off the thank-you list.", [{"lit": "proof"}, {"lit": "thanked"}, {"field": "engine"}, {"field": "item"}], [ENG, ID("Referral number (like REF-001)", "REF")])
T["dse.proof_list"] = tool("Proof Desk: everything at a glance", "Every ask, quote (usable or not, and why) and referral for this engine.", [{"lit": "proof"}, {"lit": "list"}, {"field": "engine"}], [ENG])

p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len([k for k in T if k.startswith("dse.proof")]), "proof tools,", len(T), "in all")
