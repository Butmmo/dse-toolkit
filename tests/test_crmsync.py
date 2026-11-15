"""Scenario tests for the CRM sync (what goes to the BPS CRM and when).   python tests/test_crmsync.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import crmsync as C, desklog as dl  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def write_csv(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def row(n, name, **kw):
    return {"row": n, "business": name, "city": "Tampa", "state": "FL", "category": "Dentists", "channel": "Email", "where": f"{name.lower()}@x.example.com", "gap_used": f"{name} never asks for reviews",
            "variant": "smb-v1", "opener": f"Hi {name}", "website": f"https://www.{name.lower()}.example.com/about", "email": f"{name.lower()}@x.example.com", "phone": "555-0100", "instagram": "", "facebook": "", **kw}


def tap(slug, source, row_id, status, day, **kw):
    dl.append_events(slug, [{"logged_at": f"{day}T10:00:00", "source": source, "row_id": str(row_id), "status": status, "list_date": source[:10], **kw}])


SLUG = "zz-crm"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "proposals").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "CRM test", "path": "smb", "sender_name": "Bolu", "brand_name": "T Co", "archived": False}), encoding="utf-8")
state_file, C.STATE = C.STATE, ROOT / "data" / "zz-crm-sync.json"
C.STATE.unlink(missing_ok=True)
today = dt.date.today()
iso = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
try:
    L1 = iso(10)
    FU = iso(5) + "-followups"
    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf"]
    write_csv(d / "send-lists" / f"{L1}.csv", [row(i, n) for i, n in enumerate(names, 1)])
    write_csv(d / "send-lists" / f"{FU}.csv", [dict(row(1, "Alpha"), touch=2)])       # Alpha's follow-up: still ONE lead
    tap(SLUG, L1, 1, "sent", iso(9)); tap(SLUG, FU, 1, "sent", iso(5))
    tap(SLUG, L1, 2, "sent", iso(9)); tap(SLUG, L1, 2, "replied", iso(8), reply="Yes, interested, can we talk Tuesday?", category="interested")
    tap(SLUG, L1, 3, "sent", iso(9)); tap(SLUG, L1, 3, "replied", iso(8), reply="Not interested, thanks", category="not interested")
    tap(SLUG, L1, 4, "sent", iso(9)); tap(SLUG, L1, 4, "booked", iso(7))
    tap(SLUG, L1, 5, "sent", iso(9)); tap(SLUG, L1, 5, "booked", iso(7)); tap(SLUG, L1, 5, "won", iso(2), value="1500")
    tap(SLUG, L1, 6, "sent", iso(9)); tap(SLUG, L1, 6, "replied", iso(8), reply="I am out of the office until Monday", category="out of office")
    (d / "proposals" / f"{iso(1)}-delta.json").write_text(json.dumps({"client": "Delta"}), encoding="utf-8")     # a saved proposal for Delta

    leads = {r["name"]: r for r in C.leads_for(SLUG)}
    check("one CRM lead per business, even with a follow-up list", len(leads) == 7 and set(leads) == set(names), str(sorted(leads)))
    check("a sent message is Contacted, with the touches that were sent", leads["Alpha"]["stage"] == "contacted" and leads["Alpha"]["email_1_sent"] and leads["Alpha"]["email_2_sent"] and not leads["Alpha"]["email_3_sent"], str(leads["Alpha"]))
    check("an interested reply is Replied Positively, with their words in the notes", leads["Bravo"]["stage"] == "replied_positively" and "interested, can we talk Tuesday" in leads["Bravo"]["notes_hq"])
    check("not interested is Replied Negatively", leads["Charlie"]["stage"] == "replied_negatively")
    check("a saved proposal makes a booked lead Proposal Sent", leads["Delta"]["stage"] == "proposal_sent" and "proposal" in leads["Delta"]["notes_hq"])
    check("a won call is Closed, with the value in the notes", leads["Echo"]["stage"] == "closed" and "won (1500)" in leads["Echo"]["notes_hq"])
    check("an out-of-office reply is NOT a stage: still Contacted, the reply is in the notes", leads["Foxtrot"]["stage"] == "contacted" and "out of the office" in leads["Foxtrot"]["notes_hq"])
    check("a lead never touched is Not Contacted with no date", leads["Golf"]["stage"] == "not_contacted" and leads["Golf"]["last_contacted_at"] is None and leads["Golf"]["notes_hq"] == "")
    a = leads["Alpha"]
    check("the lead carries what the engine found: gap, opener, email, phone, city, where, source",
          a["the_gap"] == "Alpha never asks for reviews" and a["opener"] == "Hi Alpha" and a["contact_email"] == "alpha@x.example.com" and a["contact_phone"] == "555-0100"
          and a["city"] == "Tampa" and a["outreach_where"] and a["lead_source"] == "My PC: CRM test" and a["path_key"] == "smb" and a["niche"] == "Dentists", str(a))
    check("the key is stable and names the engine and the business", a["hq_key"].startswith(f"{SLUG}|") and a["hq_engine"] == SLUG)
    check("the last contact date is the newest touch", a["last_contacted_at"] == iso(5), str(a["last_contacted_at"]))
    check("a plain 'not interested' is not marked terminal", leads["Charlie"]["terminal"] is False)
    tap(SLUG, L1, 7, "sent", iso(6)); tap(SLUG, L1, 7, "booked", iso(5)); tap(SLUG, L1, 7, "lost", iso(1), value="price")
    g = {r["name"]: r for r in C.leads_for(SLUG)}["Golf"]
    check("a lost call is Replied Negatively and terminal, so the CRM can close it out", g["stage"] == "replied_negatively" and g["terminal"] is True and "lost (price)" in g["notes_hq"], str(g))

    # off until turned on
    check("sync is OFF until you turn it on", not C.enabled(SLUG) and "off for" in C.sync(SLUG))
    C.set_enabled(SLUG, True)
    check("turning it on is remembered", C.enabled(SLUG) and "ON" in C.status(SLUG))

    class Api:
        def __init__(self):
            self.calls = []

        def rpc(self, name, body, tries=1):
            self.calls.append((name, body))
            return {"inserted": len(body["p_rows"]), "updated": 0, "unchanged": 0}

    api = Api()
    out = C.sync(SLUG, api=api)
    check("sync sends every lead to the CRM function", len(api.calls) == 1 and api.calls[0][0] == "hq_crm_push" and len(api.calls[0][1]["p_rows"]) == 7 and "7 new lead" in out, out)
    api2 = Api()
    out2 = C.sync(SLUG, api=api2)
    check("run again with nothing changed: nothing is sent", not api2.calls and "up to date" in out2, out2)
    tap(SLUG, L1, 1, "replied", iso(0), reply="Sounds good, what does it cost?", category="price")
    api3 = Api()
    C.sync(SLUG, api=api3)
    sent = [r["name"] for r in api3.calls[0][1]["p_rows"]] if api3.calls else []
    check("only the lead that changed is sent again", sent == ["Alpha"], str(sent))
    check("a price question is Replied Positively", api3.calls and api3.calls[0][1]["p_rows"][0]["stage"] == "replied_positively")
    allowed = {"hq_key", "hq_engine", "name", "city", "website_url", "contact_email", "contact_phone", "niche", "path_key", "lead_source", "the_gap", "gaps_found", "opener",
               "outreach_channel", "outreach_where", "stage", "terminal", "last_contacted_at", "email_1_sent", "email_2_sent", "email_3_sent", "notes_hq", "lead_score"}
    check("what is sent has only plain CRM fields, no file paths and no engine settings", all(set(r) <= allowed for r in api.calls[0][1]["p_rows"]))
    many = [row(i, f"Biz{i}") for i in range(1, 251)]
    write_csv(d / "send-lists" / f"{iso(3)}.csv", many)
    api4 = Api()
    C.sync(SLUG, api=api4)
    check("many leads go in chunks of 100", [len(c[1]["p_rows"]) for c in api4.calls] == [100, 100, 50], str([len(c[1]["p_rows"]) for c in api4.calls]))

    p = C.preview(SLUG)
    check("the preview shows the stages and sends nothing", "By stage" in p and "Alpha" in p and "Nothing was sent" in p)
    C.set_enabled(SLUG, False)
    check("turning it off stops the sync", "off for" in C.sync(SLUG))
    check("no em dash in the module or its notes", chr(0x2014) not in (ROOT / "dse" / "crmsync.py").read_text(encoding="utf-8") and all(chr(0x2014) not in r["notes_hq"] for r in C.leads_for(SLUG)))
finally:
    shutil.rmtree(d, ignore_errors=True)
    C.STATE.unlink(missing_ok=True)
    C.STATE = state_file

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
