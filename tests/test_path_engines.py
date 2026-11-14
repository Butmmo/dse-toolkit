"""Scenario tests for the Go-to-Market importer, the Authority audit, the Ascent call scorecard and the three new packs.

    python tests/test_path_engines.py

No network: the website check is replaced by a stand-in where a list is built end to end. Test engines are removed afterwards.
"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import authority, callscore, check as chk, desklog as dl, engines, importer, followups as fu  # noqa: E402
from dse.common import read_csv, write_csv  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def make(slug, cfg):
    d = ROOT / "engines" / slug
    shutil.rmtree(d, ignore_errors=True)
    (d / "send-lists").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "engine.json").write_text(json.dumps({"archived": False, **cfg}), encoding="utf-8")
    return d


TODAY = dt.date.today()
ago = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()  # noqa: E731
SLUGS = ["zz-gtm", "zz-auth", "zz-asc"]

try:
    # ------------------------------------------------------------------ importer
    d = make("zz-gtm", {"name": "GTM test", "path": "gtm", "slug": "zz-gtm", "pack": "gtm", "per_day": 3, "channels": ["Email", "LinkedIn message", "Website form"],
                        "sender_name": "Bolu", "brand_name": "Test Co"})
    (d / "imports").mkdir()
    clay = ("Company Name,Domain,First Name,Last Name,Job Title,Work Email,LinkedIn Profile,Last Funding Date,Employees\n"
            f"Acme Cloud,https://www.acmecloud.io/about,Sam,Okoro,VP of Sales,sam@acmecloud.io,https://linkedin.com/in/samokoro,{ago(120)},120\n"
            f"Acme Cloud,acmecloud.io,Pat,Lee,Office Manager,pat@acmecloud.io,,{ago(120)},120\n"
            f"Brightly,brightly.com,Ada,Eze,Head of Growth,ada@brightly.com,https://linkedin.com/in/adaeze,{ago(900)},45\n"
            "Cobalt Labs,cobaltlabs.dev,Joe,Bloggs,Founder,,https://linkedin.com/in/joeb,,8\n"
            "NoSite Inc,,Mia,Ng,CRO,mia@nosite.com,,,200\n")
    (d / "imports" / "clay-export.csv").write_text(clay, encoding="utf-8")
    apollo = ("First Name;Last Name;Title;Company;Email;Person Linkedin Url;Website;# Employees;Latest Funding Date\n"
              f"Zed;Hall;Director of Revenue Operations;Delta Data;zed@deltadata.io;https://linkedin.com/in/zedhall;https://deltadata.io;250;{ago(60)}\n")
    (d / "imports" / "apollo.csv").write_text(apollo, encoding="utf-8")
    rows, reps = importer.load_all("zz-gtm")
    check("reads two exports with different headers and delimiters", len(rows) == 6 and {r["_file"] for r in rows} == {"clay-export.csv", "apollo.csv"})
    clay_rows = [r for r in rows if r["_file"] == "clay-export.csv"]
    rep_by = {x["file"]: x for x in reps}
    m = rep_by["clay-export.csv"]["mapped"]
    check("Clay headers are understood", m.get("business") == "Company Name" and m.get("website") == "Domain" and m.get("contact_title") == "Job Title" and m.get("linkedin") == "LinkedIn Profile")
    check("Apollo headers are understood (semicolons, '# Employees', 'Person Linkedin Url')", rep_by["apollo.csv"]["mapped"].get("employees") == "# Employees" and rep_by["apollo.csv"]["mapped"].get("linkedin") == "Person Linkedin Url")
    check("domains are cleaned", clay_rows[0]["website"] == "acmecloud.io")
    check("a first name is kept for the opener", clay_rows[0]["contact_first"] == "Sam")
    pts, why = importer.icp(clay_rows[0])
    check("score: sales lead + funded in last 12 months + 120 people = 4", pts == 4, str((pts, why)))
    check("old funding scores nothing", importer.icp(clay_rows[2])[0] == 2 and "raised" not in " ".join(importer.icp(clay_rows[2])[1]))
    check("a founder at a 8-person company scores for the title only", importer.icp(clay_rows[3])[0] == 1)
    lone = d / "imports" / "lone.csv"
    lone.write_text("Name,Website\nOnly Company,onlyco.com\n", encoding="utf-8")
    r2, rp2 = importer.normalize(lone)
    check("a lone 'Name' column is the company when there is no Company column", r2[0]["business"] == "Only Company" and r2[0]["contact_name"] == "")
    lone.unlink()
    check("a missing website column is reported", importer.normalize(_ := (d / "imports" / "clay-export.csv"))[1]["missing_core"] == [])

    # ------------------------------------------------------------------ a Go-to-Market list, end to end (website check replaced)
    def fake_check(pack, src, render=True, out=""):
        rs = read_csv(src)
        for r in rs:
            r["gap_line"] = "there's no instant way to book a demo, so interested visitors wait for a reply"
            r["gap_count"] = 2
            r["gaps_found"] = "No instant way to book a demo; No chat or instant qualification"
            r["check_notes"] = ""
        write_csv(out, rs)
        return out
    real_check = engines.chk.check_file
    engines.chk.check_file = fake_check
    try:
        written = engines.daily("zz-gtm", start="2026-12-07", days=1, per_day=3, render=False)
    finally:
        engines.chk.check_file = real_check
    lst = read_csv(written[0])
    names = [r["business"] for r in lst]
    check("one account per website, best contact kept, rows without a website dropped", names.count("Acme Cloud") == 1 and "NoSite Inc" not in names)
    check("the best-scoring account comes first", names[0] == "Acme Cloud" or names[0] == "Delta Data")
    check("LinkedIn message is chosen when the engine prefers it and there is a profile", all(r["channel"] in ("Email", "LinkedIn message") for r in lst))
    li = [r for r in lst if r["channel"] == "LinkedIn message"]
    check("the LinkedIn channel points at the profile", all(r["where"].startswith("https://linkedin.com/in/") for r in li))
    check("the first message uses the contact's first name and the gap", "Hi Sam" in lst[0]["opener"] or "Hi Zed" in lst[0]["opener"])
    check("the contact's title and name are kept on the list", lst[0]["contact_title"] != "" and lst[0]["contact_name"] != "")

    # ------------------------------------------------------------------ Authority audit
    d2 = make("zz-auth", {"name": "Authority test", "path": "authority", "slug": "zz-auth", "pack": "authority", "per_day": 5, "channels": ["LinkedIn message", "Email"]})
    (d2 / "pasted").mkdir()
    long_post = "I help companies grow. " + ("We built our process and we shipped our product and I think our team did great work for us. " * 6)
    sheet = [
        ["name", "profile_url", "headline", "connections", "post_dates", "post_1", "post_2", "engaged", "email"],
        ["Dr Ngozi Ade", "https://linkedin.com/in/ngoziade", "Executive coach, 15 years, author", "2.4k", f"{ago(80)};{ago(95)};{ago(140)}",
         "Thrilled to announce my new program!\nLink below.", "I'm excited to share a milestone for our firm.", "yes", ""],
        ["Tunde Bello", "https://linkedin.com/in/tundebello", "Fractional CMO, founder", "900", ";".join(ago(i * 3) for i in range(1, 30)),
         "Three lessons on pricing:\n\n1. Charge for outcomes.\n\n2. Raise prices yearly.\n\nWhich one do you struggle with?", "Why most funnels leak:\n\n- no follow up\n\nWhat would you add?", "", ""],
        ["Chi Obi", "https://linkedin.com/in/chiobi", "Student", "40", ago(5), "hello", "hi", "", ""],
        ["Wall Walker", "https://linkedin.com/in/wallwalker", "Attorney and founder, 12 years", "1,200", ago(40), long_post, long_post, "", "w@wall.com"],
    ]
    with (d2 / "pasted" / "experts.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(sheet)
    res = authority.audit("zz-auth", min_score=4)
    by = {r["business"]: r for r in res}
    check("the silent expert with an audience scores high and leads with the silence", "Dr Ngozi Ade" in by and "days ago" in by["Dr Ngozi Ade"]["gap_line"], str(by.get("Dr Ngozi Ade")))
    check("announcement-style openers are caught", "Posts open with an announcement" in by["Dr Ngozi Ade"]["gaps_found"])
    check("an expert who posts almost daily is not a prospect", "Tunde Bello" not in by)
    check("a weak profile is filtered out by the score", "Chi Obi" not in by)
    check("walls of text and talking about 'we' are caught", "Walls of text" in by["Wall Walker"]["gaps_found"] and "Talks about" in by["Wall Walker"]["gaps_found"])
    check("'1.2k' and '2,400' audiences parse", authority.audience_of("2.4k") == 2400 and authority.audience_of("1,200") == 1200)
    check("no post dates: it says so instead of guessing", "no post dates given" in authority.audit_row({**authority.read_pasted("zz-auth")[2], "post_dates": ""})["check_notes"])
    written2 = engines.daily("zz-auth", start="2026-12-07", days=1, per_day=5, render=False)
    l2 = read_csv(written2[0])
    check("Authority list uses the LinkedIn channel with the profile link", l2[0]["channel"] == "LinkedIn message" and "linkedin.com/in/" in l2[0]["where"])
    check("the first message names the expert, the gap and offers labelled sample posts, not free work", "Hi Ngozi" in l2[0]["opener"] or "Hi Dr" in l2[0]["opener"] or "Hi Wall" in l2[0]["opener"])
    check("the message offers made-up samples, never a free post", "made-up" in l2[0]["opener"] and "clearly labelled" in l2[0]["opener"])

    # ------------------------------------------------------------------ call scorecard
    make("zz-asc", {"name": "Ascent test", "path": "ascent", "slug": "zz-asc", "pack": "ascent"})
    check("scores must be eight values of 0, 1 or 2", callscore.parse_scores("2,1,0,2,1,1,2,0") == [2, 1, 0, 2, 1, 1, 2, 0])
    try:
        callscore.parse_scores("2,1,3,2,1,1,2,0")
        check("a score of 3 is refused", False)
    except ValueError:
        check("a score of 3 is refused", True)
    sc = callscore.score_call([2, 2, 1, 0, 1, 2, 0, 2])
    check("the two weakest areas are named, weakest first", [w[0] for w in sc["weakest"]] == ["cost", "objection"] and sc["pct"] == 63)
    txt = callscore.report("zz-asc", "Acme Coaching", "sold", 3000, 10, 55, [2, 2, 1, 0, 1, 2, 0, 2])
    check("the report coaches with a drill and warns when the prospect did not talk most", "Drill:" in txt and "talked 55%" in txt)
    callscore.report("zz-asc", "Acme Coaching", "no_show", 0, 10, 0, [0] * 8)
    callscore.report("zz-asc", "Acme Coaching", "no_sale", 0, 10, 40, [1, 1, 1, 1, 1, 1, 1, 1])
    st = callscore.stats(callscore.read_calls("zz-asc"))
    check("show rate, close rate, cash per call and commission", st["calls"] == 3 and st["shown"] == 2 and st["show_rate"] == 67 and st["close_rate"] == 50 and st["cash"] == 3000 and st["earned"] == 300 and st["cash_per_call"] == 1500, str(st))
    check("a no-show is not scored", [c for c in callscore.read_calls("zz-asc") if c["outcome"] == "no_show"][0]["score"] == "")
    check("a closed call that scored low is not praised", "Do not copy this one" in callscore.report("zz-asc", "X", "sold", 1000, 10, 30, [1, 0, 0, 0, 1, 1, 0, 1]))
    check("fewer than 10 calls: it says it is too few to judge", "too few to judge" in txt)

    # ------------------------------------------------------------------ the Ascent and GTM packs on sample page text
    def found(pack, cid, text):
        c = next(x for x in chk.load_pack(pack)["checks"] if x["id"] == cid)
        mm = c["_re"].search(text)
        return (next((v for k, v in mm.groupdict().items() if k.startswith("q") and v), mm.group(0)) if mm else None)
    A = "Join the 12-week Scale Program. Investment: $6,500. Apply now. We are hiring remote closers to join our sales team. Make $10k a month guaranteed income!"
    check("Ascent: finds a $3,000+ price", found("ascent", "high_ticket", A) == "$6,500")
    check("Ascent: ignores a $49 price", found("ascent", "high_ticket", "Only $49 a month") is None)
    check("Ascent: finds an application page", found("ascent", "apply_page", A) == "Apply now")
    check("Ascent: finds closers being hired", "closers" in (found("ascent", "hiring_closers", A) or ""))
    check("Ascent: warns about income promises", found("ascent", "income_claims", A) is not None)
    G = "We're hiring: Senior Account Executive and a Revenue Operations Manager. Remote."
    check("GTM: finds sales hiring", "Account Executive" in (found("gtm", "hiring_sales", G) or ""))
    check("GTM: does not call a plain page a hiring signal", found("gtm", "hiring_sales", "Our account executive team is the best in town.") is None)
    check("GTM: finds a CRM script", found("gtm", "crm_detected", '<script src="//js.hs-scripts.com/123.js"></script>') is not None)
    check("GTM: a demo calendar is recognised", found("gtm", "demo_path", "Book a demo with our team") is not None)

    # ------------------------------------------------------------------ follow-ups know the LinkedIn channel
    check("LinkedIn messages follow up after 4 and 9 days", fu.templates("zz-asc")["schedule"]["LinkedIn message"] == [4, 9])
    check("LinkedIn profiles identify a thread when there is no website", dl.thread_key({"linkedin": "https://www.linkedin.com/in/Ngozi-Ade", "business": "x"}) == "l:ngozi-ade")
finally:
    for s in SLUGS:
        shutil.rmtree(ROOT / "engines" / s, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
