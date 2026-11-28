"""One-off generator: the My tools and Tool Studio tools, and the sync helper, in catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in [k for k in T if k.startswith(("dse.mytool_", "dse.studio_"))]:
    T.pop(k)
c["periodic"] = [x for x in c.get("periodic", []) if x.get("script") != "bridge/mytools_sync.py"]
c["periodic"].append({"script": "bridge/mytools_sync.py", "every_s": 60, "what": "My tools: the tools you made in Citadel, and the ones DBI shared, onto this PC"})
c["periodic"] = [x for x in c["periodic"] if x.get("script") not in ("bridge/schedule_sync.py", "bridge/setup_sync.py", "bridge/digest_sync.py")]
c["periodic"].append({"script": "bridge/digest_sync.py", "every_s": 1800, "what": "Weekly digest: your week in numbers, sent to your Dashboard and phone once a week"})
c["periodic"].append({"script": "bridge/setup_sync.py", "every_s": 300, "what": "Setup checklist: your System check, sent to your Dashboard so you can see what is left to set up"})
c["periodic"].append({"script": "bridge/schedule_sync.py", "every_s": 60, "what": "Schedules: run your scheduled tools when they are due (an ordinary job in your Jobs list)"})

SLUG = {"name": "slug", "label": "A short name (lowercase letters, digits and -)", "type": "text", "required": True, "max": 41, "pattern": "[a-z0-9][a-z0-9-]{1,40}", "placeholder": "my-tool"}
PICK = {"name": "studio", "label": "Which of your Studio tools", "type": "choice", "required": True, "choices_from": "studio_tools", "choices": []}
TEXT = r"[A-Za-z0-9][A-Za-z0-9 ,.'?&/()!:;\"%+=#@_*$-]{2,1499}"


def tool(label, group, help_, args, fields, minutes=5, outputs=None):
    t = {"label": label, "group": group, "help": help_, "script": "dse.py", "args": args, "fields": fields, "timeout_min": minutes}
    t["outputs"] = outputs or []
    return t


T["dse.mytool_check"] = tool("My tools: check them", "My tools", "Checks every tool you made (and the ones DBI shared) against the tools on this PC and says which are ready and what to fix in the others. It changes nothing. A tool with a problem is simply not offered until it is fixed.",
                             [{"lit": "mytool"}, {"lit": "check"}], [], 2)
T["dse.mytool_list"] = tool("My tools: the list", "My tools", "Your own tools and the ones DBI shared, with whether each is ready. Make a new one in HQ Tools, My tools.", [{"lit": "mytool"}, {"lit": "list"}], [], 2)

S = "Studio"
CODE_OUT = [{"glob": "studio/*/tool.py", "upload": True, "label": "the code"}, {"glob": "studio/*/tool.json", "upload": True, "label": "the form"}]
T["dse.studio_draft"] = tool("Studio: draft a new tool with AI", S, "Describe a tool in plain words and an AI writes it (Claude with your own key, else your Ollama model). The code is checked by the guard, saved as a DRAFT and shown to you: it is not switched on. Next you test it, read it and approve it.",
                             [{"lit": "studio"}, {"lit": "draft"}, {"field": "slug"}, {"field": "describe"}],
                             [SLUG, {"name": "describe", "label": "What should the tool do? (up to 1,500 characters)", "type": "text", "required": True, "max": 1500, "pattern": TEXT,
                                     "placeholder": "read a lead list and write a CSV of the ones with no website"}], 15, CODE_OUT)
T["dse.studio_revise"] = tool("Studio: change a tool with AI", S, "Tell the AI what to change in one of your tools. The tool is switched off until the new code is tested and approved again.",
                              [{"lit": "studio"}, {"lit": "revise"}, {"field": "studio"}, {"field": "instruction"}],
                              [PICK, {"name": "instruction", "label": "What to change (up to 1,500 characters)", "type": "text", "required": True, "max": 1500, "pattern": TEXT}], 15, CODE_OUT)
T["dse.studio_show"] = tool("Studio: read a tool's code", S, "Shows the form, the code and the approval code of one of your tools, so you can read exactly what you are about to approve.",
                            [{"lit": "studio"}, {"lit": "show"}, {"field": "studio"}], [PICK], 2)
T["dse.studio_test"] = tool("Studio: test a tool", S, "Runs the tool once on its sample values, inside the guard, and shows its output and the files it made. A passing test gives the approval code for that exact code.",
                            [{"lit": "studio"}, {"lit": "test"}, {"field": "studio"}], [PICK], 10)
T["dse.studio_enable"] = tool("Studio: approve and switch on", S, "Switches a tested tool on for you only (it then appears in HQ Tools, group Studio). You must type the approval code of the exact code you read; if the code changes later the tool switches itself off.",
                              [{"lit": "studio"}, {"lit": "enable"}, {"field": "studio"}, {"opt": "--approve", "field": "approve"}],
                              [PICK, {"name": "approve", "label": "Approval code (8 characters, from the test)", "type": "text", "required": True, "max": 8, "pattern": "[0-9a-f]{8}"}], 2)
T["dse.studio_disable"] = tool("Studio: switch a tool off", S, "Stops one of your Studio tools being offered. Its files stay.", [{"lit": "studio"}, {"lit": "disable"}, {"field": "studio"}], [PICK], 2)
T["dse.studio_publish"] = tool("Studio: publish for everyone (through the repository)", S, "Copies an approved tool into the toolkit's extras folder and tells you the commit to make. Nothing is sent to anyone: code never travels through Citadel. After you review and commit it, every student gets it with the next toolkit update, under the same guard.",
                               [{"lit": "studio"}, {"lit": "publish"}, {"field": "studio"}], [PICK], 2)
T["dse.studio_list"] = tool("Studio: my tools", S, "Your Studio tools and whether each is a draft, tested or enabled, and the extra tools that came with the toolkit.", [{"lit": "studio"}, {"lit": "list"}], [], 2)
for k in ("dse.claude_status", "dse.claude_sdk"):
    T.pop(k, None)
T["dse.claude_status"] = tool("Claude: is my key connected?", "Setup", "Says whether your own Claude key is saved on this PC and whether the package is installed, and asks Anthropic whether it accepts the key (a free check). The key is never shown or sent here: type it on your PC with python dse.py claude setup.",
                              [{"lit": "claude"}, {"lit": "status"}, {"flag": "--test", "field": "test"}], [{"name": "test", "label": "Ask Anthropic if the key works", "type": "bool", "default": True}], 2)
T["dse.claude_sdk"] = tool("Claude: install the package it needs", "Setup", "Installs the official `anthropic` Python package on this PC (pip install anthropic), which DBI-AI needs to use your Claude key. Safe to run again.",
                           [{"lit": "claude"}, {"lit": "sdk"}], [], 10)
T["dse.openai_status"] = tool("ChatGPT: is my key connected?", "Setup", "Says whether your own OpenAI key is saved on this PC, and asks OpenAI whether it accepts the key (a free check). The key is never shown or sent here: type it on your PC with python dse.py openai setup.",
                              [{"lit": "openai"}, {"lit": "status"}, {"flag": "--test", "field": "test"}], [{"name": "test", "label": "Ask OpenAI if the key works", "type": "bool", "default": True}], 2)
T["dse.gemini_status"] = tool("Gemini: is my key connected?", "Setup", "Says whether your own Google AI Studio key is saved on this PC, and asks Google whether it accepts the key (a free check). The key is never shown or sent here: type it on your PC with python dse.py gemini setup.",
                              [{"lit": "gemini"}, {"lit": "status"}, {"flag": "--test", "field": "test"}], [{"name": "test", "label": "Ask Google if the key works", "type": "bool", "default": True}], 2)
T["dse.paystack_status"] = tool("Paystack: is my key connected?", "Setup", "Says whether your own Paystack key is saved on this PC, and asks Paystack whether it accepts the key (a free check). The key is never shown or sent here: type it on your PC with python dse.py paystack setup.",
                              [{"lit": "paystack"}, {"lit": "status"}, {"flag": "--test", "field": "test"}], [{"name": "test", "label": "Ask Paystack if the key works", "type": "bool", "default": True}], 2)
T["dse.pay_link_create"] = tool("Get paid: create a payment link", "Get paid", "Creates ONE payment page at Paystack with your own key, the amount fixed on it, and prints its link. Citadel saves the link onto the client or quote you started from. The key never leaves this PC except to Paystack itself.",
                              [{"lit": "paylink"}, {"lit": "create"}, {"opt": "--name", "field": "name"}, {"opt": "--amount", "field": "amount"}, {"opt": "--currency", "field": "currency"}],
                              [{"name": "name", "label": "Name on the payment page (the client or the work)", "type": "text", "required": True, "max": 120, "pattern": TEXT},
                               {"name": "amount", "label": "Amount (a plain number, for example 500 or 99.50)", "type": "text", "required": True, "max": 12, "pattern": "[0-9]+(\\.[0-9]{1,2})?"},
                               {"name": "currency", "label": "Currency", "type": "choice", "required": True, "choices": ["NGN", "USD", "GBP", "GHS", "KES", "ZAR"], "default": "NGN"}], 3)
T["dse.pay_recent"] = tool("Get paid: recent payments", "Get paid", "Lists your latest successful payments at Paystack, newest first, with amounts and references, so you can match them to unpaid invoices in Citadel and mark them paid there. It changes nothing at Paystack.",
                              [{"lit": "paylink"}, {"lit": "recent"}], [], 3)
T.pop("dse.setup_push", None)
T["dse.setup_push"] = {"label": "Setup checklist: check now", "group": "Setup", "script": "bridge/setup_sync.py", "args": [], "fields": [], "timeout_min": 3, "outputs": [],
                       "help": "Runs the System check now and sends the result to the Setup checklist on your Dashboard (it also does this by itself every 5 minutes while the runner is on). It sends only the check's own lines: what works, what needs a fix and the fix. No files, data or keys."}
for k in ("dse.claude_usage", "dse.claude_limit"):
    T.pop(k, None)
T["dse.claude_usage"] = tool("Claude: how many tokens did I use?", "Setup", "Shows the tokens your Claude answers used today and over the last days, by model. Tokens, not money: prices change, so see what you spent, and set a monthly limit, at console.anthropic.com.",
                             [{"lit": "claude"}, {"lit": "usage"}, {"field": "days"}], [{"name": "days", "label": "How many days", "type": "int", "min": 1, "max": 60, "default": 7}], 2)
T["dse.claude_limit"] = tool("Claude: set a daily limit", "Setup", "Sets a daily limit in tokens (0 means no limit). Once today's Claude answers reach it, Claude rests until tomorrow and your local model answers instead, so a small credit is not used up by accident.",
                             [{"lit": "claude"}, {"lit": "limit"}, {"field": "tokens"}], [{"name": "tokens", "label": "Tokens per day (0 = no limit)", "type": "int", "required": True, "min": 0, "max": 100000000, "default": 200000}], 2)
chat = T["chat.ask"]
for f in chat["fields"]:
    if f["name"] == "model":
        f["pattern"] = "^(auto|library|claude|claude:(haiku|sonnet|opus)|ollama:[A-Za-z0-9][A-Za-z0-9._:/-]{0,59})$"
        f["label"] = "Model (optional: auto, library, claude, claude:haiku, claude:sonnet, claude:opus or ollama:NAME)"
T.pop("dse.digest", None)
T["dse.digest"] = {"label": "Weekly digest: send it to me now", "group": "My engines", "script": "bridge/digest_sync.py", "args": [{"lit": "--now"}], "fields": [], "timeout_min": 3, "outputs": [],
                   "help": "Builds your digest for the last full week now (the taps, calls and payments you logged, and what to do first this week) and sends it to your Dashboard and phone. It also arrives by itself every Monday morning while the runner is on. It sends nothing to anyone but you."}
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(T), "tools in all")
