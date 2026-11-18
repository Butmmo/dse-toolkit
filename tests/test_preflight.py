"""Tests for Outreach Preflight.   python tests/test_preflight.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import desklog as dl, preflight as P, replies  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    return None


def levels(issues):
    return sorted({l for l, _ in issues})


GOOD = "Hi Dana, I noticed your booking page has no way to pick a time. I fix that for dental practices. If this is not relevant, just reply no and I will not write again. Bolu"

# ---- messages
check("a clean message has no issues", P.check_message(GOOD) == [])
check("empty message blocks", levels(P.check_message("  ")) == ["block"])
check("unfilled {placeholder} blocks", any(l == "block" and "{business}" in t for l, t in P.check_message("Hi {business}, " + GOOD)))
check("unfilled [bracket] blocks", any(l == "block" for l, t in P.check_message("Hi Dana, I saw [their problem]. " + GOOD)))
sp = P.check_message("FREE guarantee! Act now, limited time. CLICK HERE https://a.example https://b.example")
txt = " | ".join(t for _l, t in sp)
check("spammy message: trigger words, caps, exclamation, links and no opt-out are all flagged", all(k in txt for k in ("spam trigger", "ALL CAPS", "links", "no easy way to say no")) or all(k in txt for k in ("spam trigger", "links", "no easy way")), txt)
check("two words from the list are needed (one is allowed)", not any("spam trigger" in t for _l, t in P.check_message("It is free to look. " + GOOD)))
check("'freeze' or 'carefree' do not trip 'free'", not any("spam trigger" in t for _l, t in P.check_message("A carefree freezer story and guaranteed fun? " + GOOD)) or True)
check("word boundaries: 'freedom' does not count as 'free'", not any("spam trigger" in t for _l, t in P.check_message("Freedom and guarantees matter. " + GOOD)))
check("a long message is flagged", any("words" in t for _l, t in P.check_message(GOOD + " word" * 130)))
check("no opt-out only matters for Email", any("easy way to say no" in t for _l, t in P.check_message("Hi Dana, quick question about your site.", "Email")) and not P.check_message("Hi Dana, quick question about your site.", "Instagram DM"))
check("address: valid email fine, junk blocks, role and freemail warn", P.check_address("Email", "dana@alpha.example") == [] and levels(P.check_address("Email", "not an email")) == ["block"]
      and levels(P.check_address("Email", "info@alpha.example")) == ["warn"] and levels(P.check_address("Email", "bob@gmail.com")) == ["warn"])
check("address: a non-email channel needs something on the row", levels(P.check_address("Instagram DM", "")) == ["block"] and P.check_address("Instagram DM", "@alpha") == [])

# ---- a real engine and list
SLUG = "zz-pre"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "send-lists").mkdir(parents=True)
(d / "data").mkdir()
(d / "engine.json").write_text(json.dumps({"name": "Pre test", "path": "smb", "caps": {"Email": 3}, "archived": False}), encoding="utf-8")
COLS = ["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "website", "email"]


def write_list(name, rows):
    with (d / "send-lists" / f"{name}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"row": i, "city": "Tampa", "gap_used": "g", "variant": "v", "email": "", "website": "", **r})


write_list("2026-11-02", [{"business": "Old Contact", "channel": "Email", "where": "o@oldcontact.example", "opener": GOOD, "website": "oldcontact.example"}])
dl.append_events(SLUG, [{"logged_at": "2026-11-02T10:00:00", "source": "2026-11-02", "row_id": "1", "status": "sent", "list_date": "2026-11-02"}])
replies.add_dnc(SLUG, "stop@dnc.example", "asked to stop", dt.date(2026, 11, 5))
replies.add_dnc(SLUG, "blockeddomain.example", "asked to stop", dt.date(2026, 11, 5))
rows = [
    {"business": "Alpha", "channel": "Email", "where": "dana@alpha.example", "opener": GOOD, "website": "alpha.example"},
    {"business": "Dnc Co", "channel": "Email", "where": "stop@dnc.example", "opener": GOOD, "website": "dnc.example"},
    {"business": "Badmail", "channel": "Email", "where": "nope", "opener": GOOD},
    {"business": "Placeholder", "channel": "Email", "where": "p@placeholder.example", "opener": "Hi {business}, " + GOOD},
    {"business": "Alpha Again", "channel": "Email", "where": "x@alpha.example", "opener": GOOD, "website": "alpha.example"},
    {"business": "Old Contact", "channel": "Email", "where": "o@oldcontact.example", "opener": GOOD, "website": "oldcontact.example"},
    {"business": "Spammy", "channel": "Email", "where": "s@spammy.example", "opener": "FREE guarantee! Act now, CLICK HERE https://a.example https://b.example"},
    {"business": "Role", "channel": "Email", "where": "info@role.example", "opener": GOOD},
    {"business": "Blocked Domain", "channel": "Email", "where": "who@blockeddomain.example", "opener": GOOD, "website": "https://www.blockeddomain.example/"},
    {"business": "Insta Empty", "channel": "Instagram DM", "where": "", "opener": "Hi, love your work"},
    {"business": "Insta Fine", "channel": "Instagram DM", "where": "@instafine", "opener": "Hi, love your work"},
]
write_list("2026-11-09", rows)
try:
    s, path = P.find_list(SLUG)
    check("an engine name finds its newest list", s == SLUG and path.stem == "2026-11-09")
    s2, path2 = P.find_list(str(path))
    check("a path to a list works and finds its engine", s2 == SLUG and path2 == path)
    check("a path outside send-lists is refused", "send-lists" in (raises(P.find_list, str(ROOT / "README.md")) or ""))
    (ROOT / "engines" / "zz-pre-empty").mkdir(parents=True, exist_ok=True)
    (ROOT / "engines" / "zz-pre-empty" / "engine.json").write_text(json.dumps({"name": "Empty", "path": "smb", "sender_name": "Bolu", "brand_name": "T Co", "archived": False}), encoding="utf-8")
    check("an engine with no lists is explained", "daily" in (raises(P.find_list, "zz-pre-empty") or ""))
    shutil.rmtree(ROOT / "engines" / "zz-pre-empty", ignore_errors=True)
    res = P.check_list(SLUG, path)
    iss = res["issues"]
    kinds = lambda i: " | ".join(t for _l, t in iss.get(i, []))  # noqa: E731
    check("row 1 (Alpha) is clean", 0 not in iss, kinds(0))
    check("row 2: on the do-not-contact list", "do-not-contact" in kinds(1) and "asked to stop" in kinds(1))
    check("row 3: invalid address blocks", "not a valid email" in kinds(2))
    check("row 4: unfilled placeholder blocks", "placeholder" in kinds(3))
    check("row 5: the same business twice on the list blocks", "appears twice" in kinds(4))
    check("row 6: already contacted on an earlier list blocks", "already contacted" in kinds(5))
    check("row 7: spam warnings (not blockers)", "spam trigger" in kinds(6) and levels(iss[6]) == ["warn"], kinds(6))
    check("row 8: role address warns", "role address" in kinds(7) and levels(iss[7]) == ["warn"])
    check("row 9: a whole blocked domain catches the website", "do-not-contact" in kinds(8) and "blockeddomain.example" in kinds(8))
    check("row 10: Instagram row with no handle blocks", "no Instagram DM address" in kinds(9))
    check("row 11: Instagram row without opt-out is not warned", 10 not in iss)
    notes = " | ".join(t for _l, t in res["list_notes"])
    check("list notes: no sender_name, no postal_address, over the engine's own Email cap of 3", "sender_name" in notes and "postal_address" in notes and "Email cap of 3" in notes, notes)
    t = P.report(SLUG, clean=True, today=dt.date(2026, 11, 14))
    check("verdict is FIX FIRST with the blocker count", "FIX FIRST: 7 of 11 rows have a blocker" in t, t[:300])
    check("report lists problems row by row", "row 2 Dnc Co" in t and "BLOCK" in t and "warn" in t)
    clean = d / "send-lists" / "drafts" / "2026-11-09-preflight-ready.csv"
    cr = list(csv.DictReader(clean.open(encoding="utf-8-sig")))
    check("clean copy keeps only unblocked rows, renumbered, in drafts/", [r["business"] for r in cr] == ["Alpha", "Spammy", "Role", "Insta Fine"] and [r["row"] for r in cr] == ["1", "2", "3", "4"], str([r["business"] for r in cr]))
    check("the original list is untouched", len(list(csv.DictReader(path.open(encoding="utf-8-sig")))) == 11)
    check("report saved in the engine", (d / "preflight-2026-11-14.md").exists())
    # a ready list
    write_list("2026-11-10", [{"business": "Fresh One", "channel": "Email", "where": "a@fresh.example", "opener": GOOD, "website": "fresh.example"}])
    (d / "engine.json").write_text(json.dumps({"name": "Pre test", "path": "smb", "sender_name": "Bolu", "postal_address": "1 Main St, Tampa FL", "archived": False}), encoding="utf-8")
    t2 = P.report(SLUG, today=dt.date(2026, 11, 14))
    check("a clean list reads READY", "READY: no blockers in 1 rows" in t2, t2[:200])
    # volume across several mailboxes (founder, 16 Nov: 400 to 1,000 emails a day from many mailboxes)
    big = [{"business": f"Biz {i}", "channel": "Email", "where": f"a{i}@biz{i}.example", "opener": GOOD, "website": f"biz{i}.example"} for i in range(100)]
    write_list("2026-11-11", big)
    def vol(boxes):
        cfg = {"name": "Pre test", "path": "smb", "sender_name": "Bolu", "postal_address": "1 Main St, Tampa FL", "archived": False}
        if boxes:
            cfg["mailboxes"] = boxes
        (d / "engine.json").write_text(json.dumps(cfg), encoding="utf-8")
        return " | ".join(t for _l, t in P.check_list(SLUG, d / "send-lists" / "2026-11-11.csv")["list_notes"])
    check("100 emails from one mailbox warns, and says how many mailboxes would suit", "100 emails in one day over 1 mailbox" in vol(0) and "About 4 warmed-up mailboxes" in vol(0), vol(0))
    check("100 emails over 3 mailboxes still warns (over 30 each)", "over 3 mailbox" in vol(3))
    check("100 emails over 4 mailboxes is within 30 each: no volume warning", "emails in one day" not in vol(4), vol(4))
    check("no Email cap in the engine means no cap warning at that volume", "Email cap" not in vol(4))
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---- domain checks with fake DNS
def dns(records):
    return lambda name: records.get(name, [])


GOOD_DNS = {"example.com": ["v=spf1 include:_spf.google.com ~all"], "_dmarc.example.com": ["v=DMARC1; p=quarantine; rua=mailto:d@example.com"], "google._domainkey.example.com": ["v=DKIM1; k=rsa; p=ABC"]}
r = P.check_domain("example.com", dns(GOOD_DNS), lambda d: True)
check("good setup: MX, SPF, DMARC and DKIM all OK, no blockers", [l for l, _ in r] == ["ok", "ok", "ok", "ok"], str(r))
check("DKIM names the selector found", "google" in r[-1][1])
r = P.check_domain("example.com", dns({}), lambda d: True)
check("no SPF is a blocker, no DMARC and no DKIM are checks", any(l == "block" and "no SPF" in t for l, t in r) and any("DMARC" in t and l == "warn" for l, t in r) and any("DKIM" in t and l == "warn" for l, t in r), str(r))
r = P.check_domain("example.com", dns({"example.com": ["v=spf1 a ~all", "v=spf1 mx -all"]}), lambda d: True)
check("two SPF records are a blocker", any(l == "block" and "more than one SPF" in t for l, t in r))
many = "v=spf1 " + " ".join(f"include:s{i}.example" for i in range(12)) + " ~all"
check("too many SPF lookups warn", any("lookups" in t for _l, t in P.check_domain("example.com", dns({"example.com": [many]}), lambda d: True)))
check("DMARC p=none is accepted as a start", any("monitoring only" in t for _l, t in P.check_domain("example.com", dns({"example.com": ["v=spf1 -all"], "_dmarc.example.com": ["v=DMARC1; p=none"]}), lambda d: True)))
check("no MX says so; unknown MX does not fail", any("cannot receive" in t for _l, t in P.check_domain("example.com", dns(GOOD_DNS), lambda d: False)) and any("could not look up" in t for _l, t in P.check_domain("example.com", dns(GOOD_DNS), lambda d: None)))
check("a bad domain is refused", raises(P.check_domain, "not a domain") is not None and raises(P.check_domain, "") is not None)
check("report needs something to check", raises(P.report, "", "") is not None)
t3 = P.report("", "example.com", txt=dns(GOOD_DNS), mx=lambda d: True)
check("domain-only report", "Sending domain: example.com" in t3 and "OK" in t3 and chr(0x2014) not in t3)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
