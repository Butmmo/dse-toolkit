"""DSE Toolkit: one command for every path's lead finder and website problem check.

Run these in PowerShell opened inside the dse-toolkit folder (README: "Where to type the commands").

  python dse.py engines                                 your engines (made in Citadel: HQ Tools → My engines)
  python dse.py daily tampa-dentists [--days 3]         next dated send lists for one engine (find, check, dedupe, draft)
  python dse.py followups tampa-dentists                plan tomorrow's follow-ups (touch 2 and 3) for everyone marked Sent
  python dse.py outcomes tampa-dentists                 what the engine is producing: sent, replies, calls, clients
  python dse.py log tampa-dentists 2026-11-16 3 sent    mark a row by hand (the Send Desk on your phone does this for you)
  python dse.py import acme-gtm                         check the CSV exports (Go-to-Market) or pasted profiles (Authority) before building a list
  python dse.py callscore the-ascent --outcome sold ... rate a sales call and see what to practise (The Ascent); python dse.py calls <engine>
  python dse.py kinds                                   business types the lead finder knows, by path
  python dse.py packs                                   website-check packs (one per path)
  python dse.py build dentist,plumber                   once per business type: download its US business data
  python dse.py find dentist "Tampa FL; Orlando FL"     lead list (independent businesses with a live website)
  python dse.py check smb my-lists/<file>.csv           what each website is missing + a ready opener
  python dse.py check smb https://example.com           one website, printed
  python dse.py list smb dentist "Tampa FL"             find + check in one go (the usual daily command)
  python dse.py podcasts "marketing; startup"           Broadcast Engine: active business podcasts with gaps
  python dse.py mystery new my-lists/<file>.csv         CareBridge: mystery-shop tracker
  python dse.py mystery score my-lists/<file>.csv       CareBridge: score agencies by reply time

Every result is a CSV in my-lists/. In DBI Citadel, HQ Tools runs these from your phone, and "Add to my CRM"
puts a list into BPS → CRM. Nothing here sends a message: you send every message yourself.
"""
from __future__ import annotations

import argparse
import sys

from dse import VERSION
from dse import check as chk
from dse import authority, callscore, desklog, engines, followups, importer, mystery, outcomes, places, podcasts

PACK_KINDS = {
    "smb": ["dentist", "chiropractor", "physical-therapy", "optometrist", "veterinarian", "hvac", "plumber", "roofer",
            "electrician", "landscaper", "cleaning", "pest-control", "general-contractor", "hair-salon", "barbershop",
            "spa", "law-office", "insurance", "real-estate", "gym", "movers", "interior-design"],
    "voiceai": ["hvac", "plumber", "roofer", "electrician", "pest-control", "landscaper", "cleaning", "general-contractor",
                "dentist", "chiropractor", "veterinarian", "law-office"],
    "carebridge": ["home-care", "assisted-living", "nursing-home", "senior-services"],
    "ministry": [],
    "revenue": [],
}


def main():
    ap = argparse.ArgumentParser(prog="dse.py", description=f"DSE Toolkit {VERSION}", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("kinds")
    sub.add_parser("packs")
    b = sub.add_parser("build"); b.add_argument("kinds", help="comma-separated business types, e.g. dentist,plumber")
    f = sub.add_parser("find"); f.add_argument("kind"); f.add_argument("cities")
    for p in (f,):
        p.add_argument("--miles", type=float, default=25.0); p.add_argument("--max", type=int, default=100)
        p.add_argument("--all", action="store_true", help="keep national chains"); p.add_argument("--out", default="")
    c = sub.add_parser("check"); c.add_argument("pack"); c.add_argument("target", help="a CSV with a website column, or one web address")
    c.add_argument("--fast", action="store_true", help="skip the hidden browser (quicker, misses JavaScript-built sites)")
    c.add_argument("--out", default="")
    l = sub.add_parser("list"); l.add_argument("pack"); l.add_argument("kind"); l.add_argument("cities")
    l.add_argument("--miles", type=float, default=25.0); l.add_argument("--max", type=int, default=40)
    l.add_argument("--fast", action="store_true"); l.add_argument("--all", action="store_true")
    pc = sub.add_parser("podcasts"); pc.add_argument("terms"); pc.add_argument("--genre", default="business")
    pc.add_argument("--max", type=int, default=60); pc.add_argument("--max-silent", type=int, default=180); pc.add_argument("--out", default="")
    m = sub.add_parser("mystery"); m.add_argument("action", choices=["new", "score"]); m.add_argument("csv")
    sub.add_parser("engines")
    dl = sub.add_parser("daily"); dl.add_argument("engine"); dl.add_argument("--start"); dl.add_argument("--days", type=int, default=1)
    dl.add_argument("--per-day", type=int); dl.add_argument("--fast", action="store_true")
    fu = sub.add_parser("followups"); fu.add_argument("engine"); fu.add_argument("--start"); fu.add_argument("--days", type=int, default=1)
    fu.add_argument("--preview", action="store_true", help="show them, save nothing")
    oc = sub.add_parser("outcomes"); oc.add_argument("engine")
    im = sub.add_parser("import"); im.add_argument("engine")
    cs = sub.add_parser("callscore"); cs.add_argument("engine"); cs.add_argument("--offer", required=True)
    cs.add_argument("--outcome", required=True, choices=list(callscore.OUTCOMES)); cs.add_argument("--cash", type=float, default=0)
    cs.add_argument("--commission", type=float, default=0); cs.add_argument("--talk", type=int, default=0, help="percent of the call you talked")
    cs.add_argument("--scores", default="", help="8 scores 0-2, comma separated, in the order of the areas (see python dse.py callscore --help)")
    for i in range(1, 9):
        cs.add_argument(f"--a{i}", type=int, choices=[0, 1, 2], default=None, help=argparse.SUPPRESS)
    ch = sub.add_parser("calls"); ch.add_argument("engine")
    lg = sub.add_parser("log"); lg.add_argument("engine"); lg.add_argument("source", help="the list name, e.g. 2026-11-16 or 2026-11-17-followups")
    lg.add_argument("row", help="the row number on that list"); lg.add_argument("status", choices=list(desklog.STATUSES))
    lg.add_argument("--reply", default=""); lg.add_argument("--value", default="")
    a = ap.parse_args()

    if a.cmd == "import":
        cfg = engines.load(a.engine)
        (authority.preview if cfg.get("path") == "authority" or cfg.get("source") == "pasted" else importer.preview)(a.engine)
    elif a.cmd == "callscore":
        engines.load(a.engine)
        try:
            given = [getattr(a, f"a{i}") for i in range(1, 9)]
            sc = ([0] * len(callscore.AREAS) if a.outcome == "no_show"
                  else callscore.parse_scores(given) if all(x is not None for x in given) else callscore.parse_scores(a.scores))
        except ValueError as e:
            sys.exit(f"{e}\nAreas in order: " + "; ".join(f"{i + 1} {x[1]}" for i, x in enumerate(callscore.AREAS)))
        print(callscore.report(a.engine, a.offer, a.outcome, a.cash, a.commission, a.talk, sc))
    elif a.cmd == "calls":
        engines.load(a.engine)
        print(callscore.history(a.engine))
    elif a.cmd == "followups":
        followups.report(a.engine, a.start, a.days, write=not a.preview)
    elif a.cmd == "outcomes":
        print(outcomes.report(a.engine))
    elif a.cmd == "log":
        engines.load(a.engine)
        desklog.append_events(a.engine, [{"logged_at": desklog.local_now(), "source": a.source, "row_id": a.row, "status": a.status,
                                          "reply": a.reply, "value": a.value, "list_date": a.source[:10]}])
        print(f"logged: {a.source} row {a.row} is now '{a.status}'")
    elif a.cmd == "kinds":
        for pack, kinds in PACK_KINDS.items():
            if kinds:
                print(f"{pack}:")
                for k in kinds:
                    have = "ready" if places.extract_path(k).exists() else "run: python dse.py build " + k
                    print(f"  {k:<20} {places.KINDS[k][0]:<28} {have}")
    elif a.cmd == "packs":
        for p in sorted(chk.PACKS.glob("*.json")):
            pk = chk.load_pack(p.stem)
            print(f"{p.stem:<11} {pk['label']}: {pk.get('about', '')}")
        print("podcasts    The Broadcast Engine: python dse.py podcasts \"<topics>\"")
    elif a.cmd == "build":
        places.build([k.strip() for k in a.kinds.split(",") if k.strip()])
    elif a.cmd == "find":
        places.find(a.kind, a.cities, a.miles, a.max, a.all, a.out)
    elif a.cmd == "check":
        if a.target.lower().startswith(("http://", "https://", "www.")) or (a.target.count(".") and not a.target.lower().endswith(".csv")):
            chk.check_one(a.pack, a.target, render=not a.fast)
        else:
            chk.check_file(a.pack, a.target, render=not a.fast, out=a.out)
    elif a.cmd == "list":
        if a.pack in PACK_KINDS and PACK_KINDS[a.pack] and a.kind not in PACK_KINDS[a.pack]:
            print(f"Note: '{a.kind}' isn't one of the {a.pack} business types ({', '.join(PACK_KINDS[a.pack])}).", file=sys.stderr)
        src = places.find(a.kind, a.cities, a.miles, a.max, a.all)
        chk.check_file(a.pack, src, render=not a.fast)
    elif a.cmd == "podcasts":
        podcasts.find(a.terms, a.genre, a.max, a.max_silent, a.out)
    elif a.cmd == "engines":
        engines.list_engines()
    elif a.cmd == "daily":
        engines.daily(a.engine, a.start, a.days, a.per_day, render=not a.fast)
    elif a.cmd == "mystery":
        (mystery.new if a.action == "new" else mystery.score)(a.csv)


if __name__ == "__main__":
    main()
