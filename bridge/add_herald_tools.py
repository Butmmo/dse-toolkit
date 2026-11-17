"""One-off generator: adds the Herald tools and its background sync to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.herald_list", "dse.herald_test"):
    T.pop(k, None)

NEVER = ("It sends nothing and reads nothing: it only tries to log in. The mailbox password is never shown, never logged and never leaves this PC; it is typed in a terminal "
         "(python dse.py herald secret <address>) and kept under Windows' own protection.")
T["dse.herald_list"] = {
    "label": "Herald: my mailboxes on this PC", "group": "My engines",
    "help": "Lists the mailboxes you connected in Citadel (Herald > Mailboxes) and whether a password is set for each on this PC. " + NEVER,
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "list"}], "fields": [], "timeout_min": 3, "outputs": []}
T["dse.herald_test"] = {
    "label": "Herald: test a mailbox connection", "group": "My engines",
    "help": "Tries the sending (SMTP) and reading (IMAP) logins for one mailbox, or all of them, and tells Citadel the result so the mailbox shows Ready or what to fix. Set the password first in a terminal: python dse.py herald secret <address>. " + NEVER,
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "test"}, {"field": "mailbox"}],
    "fields": [{"name": "mailbox", "label": "Mailbox address (or all)", "type": "text", "required": True, "default": "all", "max": 254}],
    "timeout_min": 3, "outputs": []}

per = c.setdefault("periodic", [])
if not any(x.get("script") == "bridge/herald_sync.py" for x in per):
    per.append({"script": "bridge/herald_sync.py", "every_s": 60, "what": "Herald: your mailbox settings from Citadel onto this PC, each mailbox's status back (never a password)"})
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("herald tools:", sum(1 for k in T if k.startswith("dse.herald")), "tools:", len(T))
