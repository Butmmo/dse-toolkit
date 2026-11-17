"""One-off generator: adds the Herald tools and its background sync to catalog.json. Safe to re-run."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "catalog.json"
c = json.loads(p.read_text(encoding="utf-8"))
T = c["tools"]
for k in ("dse.herald_password", "dse.herald_list", "dse.herald_test", "dse.herald_sendstatus", "dse.herald_sendtest", "dse.herald_pause", "dse.herald_resume"):
    T.pop(k, None)

NEVER = ("It sends nothing and reads nothing: it only tries to log in. The mailbox password is never shown, never logged and never leaves this PC; it is typed in a terminal "
         "(python dse.py herald secret <address>) and kept under Windows' own protection.")
T["dse.herald_password"] = {
    "label": "Herald: type a mailbox password on this PC", "group": "My engines",
    "help": "Opens a window on THIS PC that asks for the mailbox's password (an app password for Gmail). You type it in that window: nothing shows while you type, and it is saved on this PC only, under Windows' own protection. It never goes through Citadel, this runner or a log. Then press Test connection.",
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "password"}, {"field": "mailbox"}],
    "fields": [{"name": "mailbox", "label": "Mailbox address", "type": "text", "required": True, "max": 254}], "timeout_min": 2, "outputs": []}
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

SEND = ("Sends only emails of campaigns you started in Citadel, inside their send window and limits, never more than a mailbox's daily limit. ")
T["dse.herald_sendstatus"] = {
    "label": "Herald: what would send right now (a dry run)", "group": "My engines",
    "help": "Shows which scheduled emails are due on this PC right now and why the others are held (outside the window, daily limit reached, waiting for a delay ...). It sends nothing. " + SEND,
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "send"}, {"lit": "--dry"}], "fields": [], "timeout_min": 3, "outputs": []}
T["dse.herald_sendtest"] = {
    "label": "Herald: send one test email", "group": "My engines",
    "help": "Sends ONE email from a mailbox to an address you type (your own, to see that sending works and how it looks). It is not a campaign email and uses no lead. The password stays on this PC.",
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "sendtest"}, {"field": "mailbox"}, {"field": "to"}],
    "fields": [{"name": "mailbox", "label": "Send from this mailbox (address)", "type": "text", "required": True, "max": 254},
               {"name": "to", "label": "Send the test to this address", "type": "text", "required": True, "max": 254}], "timeout_min": 3, "outputs": []}
T["dse.herald_pause"] = {
    "label": "Herald: pause all sending on this PC", "group": "My engines",
    "help": "The stop switch: nothing is sent from this PC until you resume. Campaigns keep their place and catch up when sending resumes (inside their daily limits).",
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "pause"}], "fields": [], "timeout_min": 3, "outputs": []}
T["dse.herald_resume"] = {
    "label": "Herald: resume sending on this PC", "group": "My engines",
    "help": "Turns sending on again after a pause.",
    "script": "dse.py", "args": [{"lit": "herald"}, {"lit": "resume"}], "fields": [], "timeout_min": 3, "outputs": []}

per = c.setdefault("periodic", [])
if not any(x.get("script") == "bridge/herald_sync.py" for x in per):
    per.append({"script": "bridge/herald_sync.py", "every_s": 60, "what": "Herald: your mailbox settings from Citadel onto this PC, each mailbox's status back (never a password)"})
if not any(x.get("script") == "bridge/herald_send.py" for x in per):
    per.append({"script": "bridge/herald_send.py", "every_s": 60, "what": "Herald: sends the due emails of campaigns you started (inside their windows and limits) and reads your inboxes for replies, bounces and unsubscribes"})
p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("herald tools:", sum(1 for k in T if k.startswith("dse.herald")), "tools:", len(T))
