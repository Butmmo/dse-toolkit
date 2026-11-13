"""DSE Toolkit: one command for every path's lead finder and website problem check.

Run these in PowerShell opened inside the dse-toolkit folder (README: "Where to type the commands").

  python dse.py engines                                 your engines (made in Citadel: HQ Tools → My engines)
  python dse.py daily tampa-dentists [--days 3]         next dated send lists for one engine (find, check, dedupe, draft)
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
from dse import engines, mystery, places, podcasts

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
    a = ap.parse_args()

    if a.cmd == "kinds":
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
