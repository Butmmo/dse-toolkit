"""DSE Toolkit: one command for every path's lead finder and website problem check.

Run these in PowerShell opened inside the dse-toolkit folder (README: "Where to type the commands").

  python dse.py engines                                 your engines (made in Citadel: HQ Tools → My engines)
  python dse.py daily tampa-dentists [--days 3]         next dated send lists for one engine (find, check, dedupe, draft)
  python dse.py followups tampa-dentists                plan tomorrow's follow-ups (touch 2 and 3) for everyone marked Sent
  python dse.py outcomes tampa-dentists                 what the engine is producing: sent, replies, calls, clients
  python dse.py log tampa-dentists 2026-11-16 3 sent    mark a row by hand (the Send Desk on your phone does this for you)
  python dse.py import acme-gtm                         check the CSV exports (Go-to-Market) or pasted profiles (Authority) before building a list
  python dse.py callscore the-ascent --outcome sold ... rate a sales call and see what to practise (The Ascent); python dse.py calls <engine>
  python dse.py cash <engine|all> [--month 2026-11] [--target 3000]  the Cash Desk: this month against your target; python dse.py cashin <engine> --amount 450 --kind commission logs money you received
  python dse.py digest [--week YYYY-MM-DD]                   your week in numbers (sent, replies, calls, won, money) and what to do first; the runner sends it every Monday
  python dse.py claude setup|status|sdk|remove               connect your own Claude key for the strongest DBI-AI answers (the key stays on this PC)
  python dse.py mytool list|check|save|run                  your own tools made by chaining the toolkit's tools, no code (HQ Tools, My tools)
  python dse.py studio config|draft|test|enable|publish     write your own Python tools with an AI, behind a guard and your approval (admin; off until you turn it on)
  python dse.py enrich leads.csv [--icp "words"] [--engine x] [--provider NAME]  free lead enrichment from each lead's own website (a paid provider is optional, with your own key)
  python dse.py enrichment-profile list|show|preview|export <path>  inspect a versioned path-specific research plan before enrichment
  python dse.py signals leads.csv [--engine x] [--max 25] [--profile saas] [--decision-maker functional_leader] [--decision-role signal_based] [--custom-role "VP of Sales"] [--legal-form us_c_corp] [--no-ai]  Herald research with signal-based role discovery
  python dse.py presence-signals leads.csv [--engine x] [--max 25]             separate public professional/social evidence for Presence
  python dse.py reply <engine> --text "their reply" [--source LIST --row N --log]   the Reply Desk: what kind of reply it is, a draft answer, the follow-up date; python dse.py dnc <engine>
  python dse.py preflight <engine|list> [--domain yourdomain.com] [--clean]  check a send list and your sending domain before anything goes out
  python dse.py context <engine> [--add FOLDER] [--label L] [--scan] [--show] [--remove FOLDER] [--suggest] [--adopt LIST [--apply]]  read a folder of earlier work into the engine
  python dse.py presence insights <list.csv>   Presence: what to talk about, from a checked list (counts only)
  python dse.py herald list|secret <address>|test <address|all>|forget <address>   Herald: your sending mailboxes (the password is typed here and stays on this PC)
  python dse.py grid list|push <csv> <grid>   HQ Tools into grids: send a list or a tool's result into a grid of your Ledgers (see dse/gridpush.py)
  python dse.py outreach <engine|list> [--door review|inquiry] [--start DATE] [--name N] [--address A]  14-day touch plan and a mail-merge file (sends nothing)
  python dse.py proposal <engine> --client "Acme" --problem "..." --offer "..." --price 1500 --deliverables "a; b"  a one-page proposal, cover email and follow-up (it sends nothing)
  python dse.py client won <engine> --proposal NAME   the Client Desk: from a won proposal to onboarding, invoices, delivery and payments (client list|show|done|invoice|paid)
  python dse.py cut add <engine> --name "Ada" --percent 10   the Cut Desk: the percentage your students owe you (cut report|paid|list|show|status)
  python dse.py match <engine> statement.csv [--apply]   the Statement Matcher: match Grey, Payoneer or bank credits to your open invoices (only SURE matches are ever applied)
  python dse.py success <engine>   the Student Success Desk: DFY progress, who needs a check-in (with draft messages) and the expected DFY income
  python dse.py books <engine> [--month 2026-11]   the Books Desk: a monthly pack for your accountant (received, invoiced, owed, ageing, rates); python dse.py fx add <engine> --from GBP --to USD --rate 1.27 enters an exchange rate
  python dse.py proof due <engine>   the Referral and Testimonial Desk: who to ask, exactly what they agreed to, only approved and true quotes (proof ask|mark|quote|claim|quotes|withdraw|refer|thanked|list)
  python dse.py call prep <engine> --source LIST --row N   the Call Desk: a one-page brief before a booked call, and (call after) the recap, scorecard and proposal commands once it ends
  python dse.py review <engine|all>                    the Weekly Review: the 5 things to do first this week; python dse.py goal <engine> suggests next month's goal from your history
  python dse.py vet the-ascent --offer "Name" --d_pay no ... check a commission-only offer for red flags BEFORE you work for it; python dse.py offers <engine>
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
from dse import brief, crmsync, herald, presence, doctor, custom, voices, authority, books, callscore, calls, proof, cashdesk, clients, cuts, desklog, dfysync, fx, matcher, success, enrich, enrich_providers, signal_enrichment, context_folder, goals, outreach, preflight, proposal, replies, review, vetting, engines, followups, importer, mystery, outcomes, places, podcasts, countries, cities, registers, niches, tech, audit

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
    if len(sys.argv) > 1 and sys.argv[1] == "dev":      # the Dev workspace has its own commands: python dse.py dev --help
        from dev import cli
        sys.exit(cli.main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "digest":      # your week in numbers: python dse.py digest [--week YYYY-MM-DD]
        from dse import digest
        sys.exit(digest.run_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "formula-assist":
        from dse.formula_assist import main as formula_assist_main
        sys.exit(formula_assist_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "eval-enrichment":
        from dse.enrichment_eval import main as enrichment_eval_main
        sys.exit(enrichment_eval_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "enrichment-profile":
        from dse.enrichment_profiles import main as enrichment_profiles_main
        sys.exit(enrichment_profiles_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "claude":      # connect your own Claude key (kept on this PC only): python dse.py claude --help
        from dse import claudekey
        sys.exit(claudekey.run_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("mytool", "studio"):      # My tools and Tool Studio take their own words, e.g. --in-city Tampa: python dse.py mytool --help
        from dse import cli_tools
        sys.exit(cli_tools.main(sys.argv[1], sys.argv[2:]))
    ap = argparse.ArgumentParser(prog="dse.py", description=f"DSE Toolkit {VERSION}", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    sub = ap.add_subparsers(dest="cmd", required=True)
    kd = sub.add_parser("kinds", help="the business types you can search for"); kd.add_argument("--all", action="store_true", help="also list every one of the app's 512 niches")
    sub.add_parser("packs")
    b = sub.add_parser("build"); b.add_argument("kinds", help="comma-separated business types, e.g. dentist,plumber")
    b.add_argument("--country", default="US", help="a country code (GB) or a group (eu, gulf, ...): python dse.py countries")
    b.add_argument("--source", default="foursquare", help="foursquare (needs the free HF_TOKEN), overture (open data, no token) or both")
    sub.add_parser("countries", help="the countries and groups the lead finder covers")
    th = sub.add_parser("tech", help="what a website is built with and what it is missing (our own free BuiltWith)")
    th.add_argument("target", help="one web address, or a CSV with a website column")
    th.add_argument("--max", type=int, default=100); th.add_argument("--fast", action="store_true", help="skip the hidden browser (quicker, misses JavaScript-built sites)"); th.add_argument("--out", default="")
    au = sub.add_parser("audit", help="is a lead list really the business type? a sample sheet you label, then a score")
    au.add_argument("target", help="a lead list (makes the sample sheet), or the sheet with --score")
    au.add_argument("--sample", type=int, default=20); au.add_argument("--seed", type=int, default=1); au.add_argument("--score", action="store_true", help="score a sheet you labelled (y or n in is_right)")
    au.add_argument("--out", default="")
    rs = sub.add_parser("research", help="one research run (find, read each site once, tech, enrich, score) with a lead database and history")
    rs.add_argument("action", choices=["run", "history", "leads"])
    rs.add_argument("kind", nargs="?", default="", help="run: the business type"); rs.add_argument("cities", nargs="?", default="", help="run: cities separated by ;  (or --cities-file)")
    rs.add_argument("--country", default="", help="run: the country (default US); leads: only this country"); rs.add_argument("--cities-file", default=""); rs.add_argument("--tiers", default=""); rs.add_argument("--source", default="foursquare")
    rs.add_argument("--cap", type=int, default=100); rs.add_argument("--max", type=int, default=100); rs.add_argument("--strict", action="store_true"); rs.add_argument("--new-only", action="store_true", help="keep only leads not in the database yet")
    rs.add_argument("--no-enrich", action="store_true"); rs.add_argument("--owners", action="store_true"); rs.add_argument("--icp", default=""); rs.add_argument("--words", default=""); rs.add_argument("--skip", default="")
    rs.add_argument("--min-score", type=int, default=0, help="leads: only this score or higher"); rs.add_argument("--csv", default="", help="leads: save to a CSV instead of printing")
    dr = sub.add_parser("directors", help="UK: the director's first and last name for each business of a list, from Companies House (needs your free API key)")
    dr.add_argument("source", help="a CSV list with a business name column"); dr.add_argument("--company-column", default=""); dr.add_argument("--city-column", default="")
    dr.add_argument("--max", type=int, default=200); dr.add_argument("--out", default="")
    sub.add_parser("directories", help="every lead source, how we may use it, and whether it is built")
    rg = sub.add_parser("registry", help="UK company register (Companies House): build, then find companies by town")
    rg.add_argument("action", choices=["build", "find"]); rg.add_argument("kind", help="build: types separated by commas. find: one type")
    rg.add_argument("towns", nargs="?", default="", help="find: towns separated by ;")
    rg.add_argument("--file", default="", help="build: a Companies House zip you already downloaded")
    rg.add_argument("--sic", default="", help="build: trade codes of your own, like 74100,43320 (added for every type named)")
    rg.add_argument("--min-age", type=float, default=1.0, dest="min_age", help="find: only companies at least this many years old")
    rg.add_argument("--max", type=int, default=100); rg.add_argument("--all", action="store_true", help="keep national chains"); rg.add_argument("--out", default="")
    ct = sub.add_parser("cities", help="rate the towns of a country in 7 to 10 tiers by how many prospects of one business type they hold, and save an editable list")
    ct.add_argument("kind"); ct.add_argument("--country", required=True, help="one country code, like GB")
    ct.add_argument("--source", default="foursquare", help="foursquare, overture or both")
    ct.add_argument("--levels", type=int, default=0, help="number of tiers, 7 to 10 (default: chosen from the size of the pool)")
    ct.add_argument("--cover", type=float, default=cities.DEFAULT_COVER_MILES, help="miles: a town this close to a bigger one is folded into it")
    ct.add_argument("--min-pool", type=int, default=cities.DEFAULT_MIN_POOL, dest="min_pool", help="leave out towns with fewer prospects than this")
    ct.add_argument("--refresh", action="store_true", help="rebuild the list even if you already have one (your edits are replaced)")
    sub.add_parser("categories").add_argument("search", nargs="?", default="", help="words to find among Foursquare's business categories")
    mp = sub.add_parser("mypack", help="make your own website check for any kind of business"); mp.add_argument("name")
    mp.add_argument("--sells", required=True); mp.add_argument("--checks", action="append", required=True, help="words to look for, comma separated => what to say if they are missing (repeat or one per line)")
    mp.add_argument("--opener", default=""); mp.add_argument("--pages", default="")
    f = sub.add_parser("find"); f.add_argument("kind", nargs="?", default="", help="a business type from the list, or type your own (like 'wedding photographers'); optional with --cities-file, which names its own"); f.add_argument("cities", nargs="?", default="", help="cities separated by ;  (or use --cities-file)")
    for p in (f,):
        p.add_argument("--miles", type=float, default=25.0); p.add_argument("--max", type=int, default=100)
        p.add_argument("--country", default=None, help="one country code, like GB or AE (python dse.py countries); a group of several is refused (default US, or the country in the cities file's name)")
        p.add_argument("--source", default="foursquare", help="foursquare, overture (open data, no token) or both")
        p.add_argument("--cities-file", default="", dest="cities_file", help="a cities file made by: python dse.py cities (towns marked include = Y are searched)")
        p.add_argument("--tiers", default="", help="with --cities-file: search the towns in these tiers instead, like 1-3")
        p.add_argument("--all", action="store_true", help="keep national chains"); p.add_argument("--out", default="")
        p.add_argument("--strict", action="store_true", help="keep only sites that say the trade in their title or headings, or repeat it (drops 'mentioned once' and 'too short to tell')")
        p.add_argument("--words", default="", help="your own words the website must use, comma separated (replaces the built-in ones)")
        p.add_argument("--skip", default="", help="your own words that put a business out when they are in its name")
    c = sub.add_parser("check"); c.add_argument("pack"); c.add_argument("target", help="a CSV with a website column, or one web address")
    c.add_argument("--fast", action="store_true", help="skip the hidden browser (quicker, misses JavaScript-built sites)")
    c.add_argument("--result-line", action="store_true", dest="result_line", help="with one web address: also print one RESULT line a Ledger workflow reads")
    c.add_argument("--out", default="")
    l = sub.add_parser("list"); l.add_argument("pack"); l.add_argument("kind"); l.add_argument("cities", nargs="?", default="")
    l.add_argument("--miles", type=float, default=25.0); l.add_argument("--max", type=int, default=40); l.add_argument("--country", default="US"); l.add_argument("--source", default="foursquare"); l.add_argument("--cities-file", default="", dest="cities_file"); l.add_argument("--tiers", default="")
    l.add_argument("--strict", action="store_true"); l.add_argument("--fast", action="store_true"); l.add_argument("--all", action="store_true"); l.add_argument("--words", default=""); l.add_argument("--skip", default="")
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
    vt = sub.add_parser("vet"); vt.add_argument("engine"); vt.add_argument("--offer", required=True); vt.add_argument("--url", default="")
    vt.add_argument("--commission", type=float, default=0); vt.add_argument("--ticket", type=float, default=0)
    vt.add_argument("--status", default="researching", choices=list(vetting.STATUSES)); vt.add_argument("--notes", default="")
    vt.add_argument("--target", type=float, default=3000, help="the monthly income you want from this offer")
    for q in vetting.questions():
        vt.add_argument(f"--{q['id']}", choices=["yes", "no", "unknown"], default="unknown", help=argparse.SUPPRESS)
    of = sub.add_parser("offers"); of.add_argument("engine")
    ca = sub.add_parser("cash"); ca.add_argument("engine", help="an engine, or all"); ca.add_argument("--month", default=""); ca.add_argument("--target", type=float, default=0)
    ci = sub.add_parser("cashin"); ci.add_argument("engine"); ci.add_argument("--amount", type=float, required=True)
    ci.add_argument("--kind", default="commission", choices=list(cashdesk.KINDS)); ci.add_argument("--note", default=""); ci.add_argument("--date", default="")
    cl = sub.add_parser("cashlog"); cl.add_argument("engine")
    cx = sub.add_parser("call"); cx.add_argument("action", choices=["prep", "after"]); cx.add_argument("engine"); cx.add_argument("--source", required=True); cx.add_argument("--row", required=True)
    cx.add_argument("--outcome", default="follow_up", choices=list(calls.OUTCOMES)); cx.add_argument("--problem", default=""); cx.add_argument("--cost-month", type=float, default=0, dest="cost_month")
    cx.add_argument("--price", type=float, default=0); cx.add_argument("--agreed", default=""); cx.add_argument("--stop", action="store_true"); cx.add_argument("--name", default="")
    pf_ = sub.add_parser("proof"); pf_.add_argument("action", choices=["due", "ask", "mark", "quote", "claim", "excerpt", "quotes", "withdraw", "refer", "referral", "thanked", "list"]); pf_.add_argument("engine")
    pf_.add_argument("item", nargs="?", default="", help="ASK-001, Q-001 or REF-001, where the action needs one")
    pf_.add_argument("--who", default=""); pf_.add_argument("--source", default=""); pf_.add_argument("--kind", default="both"); pf_.add_argument("--trigger", default="manual"); pf_.add_argument("--sent", action="store_true")
    pf_.add_argument("--to", default=""); pf_.add_argument("--role", default=""); pf_.add_argument("--text", default=""); pf_.add_argument("--channel", default=""); pf_.add_argument("--ask", default="")
    pf_.add_argument("--consent", default="no", choices=["yes", "no"]); pf_.add_argument("--consent-how", default="", dest="consent_how"); pf_.add_argument("--name", default="anonymous")
    pf_.add_argument("--company", default="no", choices=["yes", "no"]); pf_.add_argument("--numbers", default="no", choices=["yes", "no"]); pf_.add_argument("--scope", default="")
    pf_.add_argument("--number", default=""); pf_.add_argument("--reason", default=""); pf_.add_argument("--from", dest="from_who", default=""); pf_.add_argument("--contact", default="")
    pf_.add_argument("--referred", default=""); pf_.add_argument("--status", default=""); pf_.add_argument("--value", type=float, default=0); pf_.add_argument("--date", default="")
    bk = sub.add_parser("books"); bk.add_argument("engine"); bk.add_argument("--month", default=""); bk.add_argument("--base", default="USD")
    fxp = sub.add_parser("fx"); fxp.add_argument("action", choices=["add", "list"]); fxp.add_argument("engine"); fxp.add_argument("--from", dest="from_cur", default=""); fxp.add_argument("--to", dest="to_cur", default="USD")
    fxp.add_argument("--rate", type=float, default=0); fxp.add_argument("--date", default=""); fxp.add_argument("--note", default="")
    sc_ = sub.add_parser("success"); sc_.add_argument("engine"); sc_.add_argument("--view", default="overview", choices=["overview", "flags", "drafts", "forecast"]); sc_.add_argument("--months", type=int, default=6)
    mt = sub.add_parser("match"); mt.add_argument("engine"); mt.add_argument("statement", help="your exported CSV (in engines/<engine>/statements/, or a path)")
    mt.add_argument("--apply", action="store_true", help="record the SURE matches"); mt.add_argument("--monthfirst", action="store_true", help="read 03/04/2026 as March 4"); mt.add_argument("--tolerance", type=float, default=None, help="the transfer fee you allow a payment to be short by")
    ct = sub.add_parser("cut"); ct.add_argument("action", choices=["add", "report", "paid", "list", "show", "status", "sync", "accounts"]); ct.add_argument("target", help="an engine (add, list) or engine/student (the rest)")
    ct.add_argument("--name", default=""); ct.add_argument("--percent", type=float, default=0); ct.add_argument("--basis", default="gross"); ct.add_argument("--currency", default="USD")
    ct.add_argument("--method", default="grey"); ct.add_argument("--email", default=""); ct.add_argument("--due-days", type=int, default=7, dest="due_days"); ct.add_argument("--start", default="")
    ct.add_argument("--month", default=""); ct.add_argument("--earned", type=float, default=-1); ct.add_argument("--fees", type=float, default=0); ct.add_argument("--proof", default="")
    ct.add_argument("--replace", action="store_true"); ct.add_argument("--invoice", default=""); ct.add_argument("--amount", type=float, default=0); ct.add_argument("--date", default="")
    ct.add_argument("--writeoff", action="store_true"); ct.add_argument("--to", default="")
    ct.add_argument("--program", default="custom", choices=["custom", "dfy"], help="dfy = the DFY terms: 20%% of net, capped at 18000, 12 qualified months")
    ct.add_argument("--auto", default="", choices=["", "on", "off"]); ct.add_argument("--publish", action="store_true"); ct.add_argument("--example", action="store_true")
    cd = sub.add_parser("client"); cd.add_argument("action", choices=["won", "list", "show", "done", "invoice", "paid"]); cd.add_argument("target", help="an engine (won, list) or engine/client (the rest)")
    cd.add_argument("--proposal", default=""); cd.add_argument("--email", default=""); cd.add_argument("--address", default=""); cd.add_argument("--item", default="")
    cd.add_argument("--date", default=""); cd.add_argument("--kind", default="final"); cd.add_argument("--amount", type=float, default=0); cd.add_argument("--note", default="")
    cd.add_argument("--terms", type=int, default=7); cd.add_argument("--invoice", default="")
    pr = sub.add_parser("proposal"); pr.add_argument("engine"); pr.add_argument("--client", required=True); pr.add_argument("--contact", default=""); pr.add_argument("--problem", required=True)
    pr.add_argument("--offer", required=True); pr.add_argument("--price", type=float, default=0); pr.add_argument("--deliverables", required=True); pr.add_argument("--weeks", type=int, default=3)
    pr.add_argument("--cost-month", type=float, default=0, dest="cost_month"); pr.add_argument("--options", default=""); pr.add_argument("--deposit", type=int, default=50)
    pr.add_argument("--currency", default="USD"); pr.add_argument("--excludes", default=""); pr.add_argument("--start", default=""); pr.add_argument("--quotes", action="store_true", help="add approved testimonials (their exact words, the attribution they chose)")
    pf = sub.add_parser("preflight"); pf.add_argument("target", nargs="?", default="", help="an engine (newest list) or a path to a list"); pf.add_argument("--domain", default="")
    pf.add_argument("--clean", action="store_true", help="write a copy without the blocked rows")
    cx = sub.add_parser("context"); cx.add_argument("engine"); cx.add_argument("--add", default=""); cx.add_argument("--label", default="")
    cx.add_argument("--remove", default=""); cx.add_argument("--scan", action="store_true"); cx.add_argument("--show", action="store_true")
    cx.add_argument("--suggest", action="store_true"); cx.add_argument("--adopt", default=""); cx.add_argument("--apply", action="store_true")
    hd = sub.add_parser("herald", help="Herald: your sending mailboxes"); hd.add_argument("rest", nargs=argparse.REMAINDER)
    pz = sub.add_parser("presence", help="Presence: research, graphics and video for your social content"); pz.add_argument("rest", nargs=argparse.REMAINDER)
    gp = sub.add_parser("grid", help="HQ Tools into grids: send a list into a grid of your Ledgers"); gp.add_argument("rest", nargs=argparse.REMAINDER)
    op = sub.add_parser("outreach"); op.add_argument("target"); op.add_argument("--door", default=""); op.add_argument("--start", default="")
    op.add_argument("--name", default=""); op.add_argument("--address", default="")
    rp = sub.add_parser("reply"); rp.add_argument("engine"); rp.add_argument("--text", required=True); rp.add_argument("--name", default=""); rp.add_argument("--source", default="")
    rp.add_argument("--row", default=""); rp.add_argument("--email", default=""); rp.add_argument("--log", action="store_true", help="record it and update the do-not-contact list")
    dn = sub.add_parser("dnc"); dn.add_argument("engine")
    en = sub.add_parser("enrich"); en.add_argument("source", nargs="?", default="", help="a CSV with a website or domain column"); en.add_argument("--site", default="", help="look at one website instead")
    en.add_argument("--icp", default="", help="words you want to find on their site, comma separated"); en.add_argument("--engine", default="", help="also save an import-ready copy in this engine")
    en.add_argument("--max", type=int, default=100); en.add_argument("--fast", action="store_true", help="skip the hidden browser"); en.add_argument("--result-line", action="store_true", dest="result_line", help="with --site: also print one RESULT line a Ledger workflow reads")
    en.add_argument("--provider", default="", help="optional: one paid provider, set up with --add-provider (legacy single-rung mode)"); en.add_argument("--waterfall-config", default="", help="JSON file defining ordered email providers, acceptance policy and call cap")
    en.add_argument("--budget", type=int, default=None, help="override the provider-call cap in the waterfall config"); en.add_argument("--dry-run", action="store_true", help="project optional provider calls without making provider requests")
    en.add_argument("--providers", action="store_true", help="list the providers set up here"); en.add_argument("--add-provider", default="", dest="add_provider")
    se = sub.add_parser("signals", help="research public business/search/social signals for leads and draft email with a local AI")
    se.add_argument("source", help="CSV with a company name; city and website improve matching")
    se.add_argument("--engine", default="", help="also save the researched CSV to this engine's imports")
    se.add_argument("--path", choices=list(signal_enrichment.path_signals.PATH_SIGNAL_PROFILES), default="any", help="path focus; a selected Engine path is used automatically")
    se.add_argument("--max", type=int, default=25, help="most leads to research in this stage, 1 to 50")
    se.add_argument("--profile", choices=["any", "franchise_group", "local_smb", "saas", "online_store", "enterprise"], default="any", help="business type to prioritize in search; this is not a verified classification")
    se.add_argument("--decision-maker", choices=["any", "owner_compact", "franchise_operator", "functional_leader", "specialist_director"], default="any", help="decision-maker path to prioritize")
    se.add_argument("--decision-role", choices=list(signal_enrichment.business_profiles.DECISION_ROLES), default="signal_based", help="role to find, or infer several role targets from the supplied lead signal")
    se.add_argument("--custom-role", default="", help="optional role title to search in addition to inferred or preset roles")
    se.add_argument("--legal-form", choices=["any", "us_c_corp", "us_s_corp"], default="any", help="US C-Corp/S-Corp search hint only; results are not legal verification")
    se.add_argument("--search-provider", choices=["duckduckgo", "brave"], default="duckduckgo", help="public search provider; Brave requires a PC-local key and uses your API allowance")
    se.add_argument("--search-budget", type=int, default=12, help="maximum ordered search queries per lead (0 to 30)")
    se.add_argument("--minimum-identity-score", type=float, default=0.0, help="discard results below this heuristic 0 to 1 score; not a probability")
    se.add_argument("--no-ai", action="store_true", help="collect sourced search signals without asking local Ollama to draft email")
    ps = sub.add_parser("presence-signals", help="collect separate public professional/social signals for Presence (no outreach draft)")
    ps.add_argument("source", help="CSV with a company name; contact name and city improve matching")
    ps.add_argument("--engine", default="", help="also save the Presence-specific CSV to this engine's imports")
    ps.add_argument("--max", type=int, default=25, help="most leads to check in this stage, 1 to 50")
    ps.add_argument("--search-budget", type=int, default=3, help="maximum ordered public search queries per lead (0 to 10)")
    ps.add_argument("--minimum-identity-score", type=float, default=0.0, help="discard results below this heuristic 0 to 1 score; not a probability")
    gl = sub.add_parser("goal"); gl.add_argument("engine"); gl.add_argument("--month", default=""); gl.add_argument("--stretch", type=float, default=goals.STRETCH_DEFAULT)
    gl.add_argument("--apply", action="store_true", help="save the suggestion as that month's goal"); gl.add_argument("--set", type=float, default=0, dest="set_to")
    rv = sub.add_parser("review"); rv.add_argument("engine", help="an engine, or all"); rv.add_argument("--top", type=int, default=5)
    ch = sub.add_parser("calls"); ch.add_argument("engine")
    cr = sub.add_parser("crm", help="keep your engines' leads, replies and calls in your BPS CRM"); cr.add_argument("action", choices=["status", "preview", "on", "off", "sync"]); cr.add_argument("engine", nargs="?", default="")
    dc = sub.add_parser("doctor", help="the System check: what is on, what is missing, and the exact fix"); dc.add_argument("--offline", action="store_true", help="skip the questions to the Citadel database")
    bf = sub.add_parser("brief", help="what to do first today, across all your engines"); bf.add_argument("--top", type=int, default=3)
    vc = sub.add_parser("voices", help="the Voices library: figures worth learning from, real passages with sources")
    vc.add_argument("action", choices=["list", "show", "verify", "fetch", "update", "ask", "today", "note", "check", "setup", "repair"])
    vc.add_argument("target", nargs="?", default="", help="a question (ask), a figure id (show, fetch, note), or nothing")
    vc.add_argument("--figure", default=""); vc.add_argument("--stratum", default=""); vc.add_argument("--path", default=""); vc.add_argument("--n", type=int, default=3)
    vc.add_argument("--text", default=""); vc.add_argument("--source", default=""); vc.add_argument("--minutes", type=int, default=25); vc.add_argument("--force", action="store_true")
    lg =sub.add_parser("log"); lg.add_argument("engine"); lg.add_argument("source", help="the list name, e.g. 2026-11-16 or 2026-11-17-followups")
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
    elif a.cmd == "vet":
        engines.load(a.engine)
        print(vetting.report(a.engine, a.offer, a.url, a.commission, a.ticket, a.status, a.notes, {q["id"]: getattr(a, q["id"]) for q in vetting.questions()}, a.target))
    elif a.cmd == "offers":
        engines.load(a.engine)
        print(vetting.listing(a.engine))
    elif a.cmd == "cash":
        try:
            print(cashdesk.build(a.engine, a.month or None, target=a.target or None))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "cashin":
        try:
            r = cashdesk.log_cash(a.engine, a.amount, a.kind, a.note, a.date)
        except ValueError as e:
            sys.exit(str(e))
        print(f"Logged {r['amount']} ({r['kind']}) on {r['date']}.")
        print()
        print(cashdesk.build(a.engine))
    elif a.cmd == "goal":
        try:
            print(goals.report(a.engine, a.month or None, a.stretch, a.apply, a.set_to or None))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "review":
        print(review.build(a.engine, max(1, min(a.top, 30))))
    elif a.cmd == "enrich":
        try:
            if a.providers:
                print(enrich_providers.describe())
            elif a.add_provider:
                print(enrich_providers.add_provider(a.add_provider))
            elif a.site:
                print(enrich.card(a.site, a.icp, not a.fast, a.provider, a.budget,
                                  a.result_line, a.waterfall_config, a.dry_run))
            elif a.source:
                print(enrich.enrich_file(a.source, a.icp, a.engine, a.max, not a.fast, provider=a.provider, budget=a.budget,
                                         waterfall_config_path=a.waterfall_config, dry_run=a.dry_run))
            else:
                sys.exit("Give a CSV to enrich (python dse.py enrich leads.csv), or --site https://their-site.com, or --providers.")
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "signals":
        try:
                print(signal_enrichment.enrich_file(a.source, a.engine, a.max, not a.no_ai, a.profile, a.decision_maker, a.legal_form, a.decision_role, a.custom_role,
                                                    a.search_provider, a.path, a.search_budget, a.minimum_identity_score))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "presence-signals":
        try:
            print(signal_enrichment.enrich_presence_file(a.source, a.engine, a.max, a.search_budget, a.minimum_identity_score))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "reply":
        try:
            print(replies.report(a.engine, a.text, a.name, a.source, a.row, a.log, a.email))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "dnc":
        print(replies.dnc_report(a.engine))
    elif a.cmd == "context":
        try:
            if a.suggest:
                print(context_folder.suggest(a.engine))
            elif a.adopt:
                print(context_folder.adopt(a.engine, a.adopt, a.apply))
            else:
                print(context_folder.report(a.engine, a.add, a.label, a.remove, a.scan, a.show))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "herald":
        sys.exit(herald.cli(a.rest))
    elif a.cmd == "presence":
        sys.exit(presence.cli(a.rest))
    elif a.cmd == "grid":
        from dse import gridpush
        sys.exit(gridpush.cli(a.rest))
    elif a.cmd == "outreach":
        try:
            print(outreach.report(a.target, a.door, a.start or None, a.name, a.address))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "preflight":
        try:
            print(preflight.report(a.target, a.domain, a.clean))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "proposal":
        try:
            print(proposal.report(a.engine, a.client, a.contact, a.problem, a.offer, a.price, a.deliverables, a.weeks, a.cost_month, a.options, a.deposit, a.currency, a.excludes, a.start, with_quotes=a.quotes))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "client":
        try:
            if a.action == "won":
                print(clients.won(a.target, a.proposal, a.email, a.address))
            elif a.action == "list":
                print(clients.listing(a.target))
            elif a.action == "show":
                print(clients.show(a.target))
            elif a.action == "done":
                print(clients.done(a.target, a.item, a.date))
            elif a.action == "invoice":
                print(clients.invoice(a.target, a.kind, a.amount, a.note, a.terms))
            else:
                print(clients.paid(a.target, a.invoice, a.amount, a.date))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "cut":
        try:
            if a.action == "add":
                print(cuts.add(a.target, a.name, a.percent, a.basis, a.currency, a.method, a.email, a.due_days, a.start, program=a.program))
            elif a.action == "report":
                if a.earned < 0:
                    sys.exit("Say what they earned: --earned 3200 (0 if nothing).")
                print(cuts.report(a.target, a.month, a.earned, a.fees, a.proof, a.replace))
            elif a.action == "paid":
                print(cuts.paid(a.target, a.invoice, a.amount, a.date, a.writeoff))
            elif a.action == "list":
                print(cuts.listing(a.target))
            elif a.action == "show":
                print(cuts.show(a.target))
            elif a.action == "sync":
                print(dfysync.set_auto(a.target, a.auto == "on") if a.auto else dfysync.run(a.target))
            elif a.action == "accounts":
                print(dfysync.accounts(a.target, a.publish, a.example))
            else:
                print(cuts.set_status(a.target, a.to))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "match":
        try:
            print(matcher.report(a.engine, a.statement, a.apply, a.monthfirst, a.tolerance))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "success":
        try:
            print(success.report(a.engine, a.view, a.months))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "books":
        try:
            print(books.build(a.engine, a.month or None, a.base))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "fx":
        try:
            print(fx.add_rate(a.engine, a.from_cur, a.to_cur, a.rate, a.date, a.note) if a.action == "add" else fx.listing(a.engine))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "proof":
        try:
            x = a.action
            if x == "due":
                print(proof.due(a.engine))
            elif x == "ask":
                print(proof.ask(a.engine, a.who, a.source or "manual", a.kind, a.trigger, a.sent))
            elif x == "mark":
                print(proof.mark(a.engine, a.item, a.to, date=a.date))
            elif x == "quote":
                print(proof.quote(a.engine, a.who, a.text, a.role, a.channel, a.ask, a.consent == "yes", a.consent_how, a.name, a.company == "yes", a.numbers == "yes", a.scope))
            elif x == "claim":
                print(proof.claim(a.engine, a.item, a.number, a.source))
            elif x == "excerpt":
                print(proof.excerpt(a.engine, a.item, a.text))
            elif x == "quotes":
                print(proof.quotes(a.engine, a.scope))
            elif x == "withdraw":
                print(proof.withdraw(a.engine, a.item, a.reason))
            elif x == "refer":
                print(proof.refer(a.engine, a.from_who, a.referred, a.contact, a.ask))
            elif x == "referral":
                print(proof.referral(a.engine, a.item, a.status, a.value))
            elif x == "thanked":
                print(proof.thanked(a.engine, a.item))
            else:
                print(proof.listing(a.engine))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "call":
        try:
            print(calls.prep(a.engine, a.source, a.row) if a.action == "prep" else calls.after(a.engine, a.source, a.row, a.outcome, a.problem, a.cost_month, a.price, a.agreed, a.stop, name=a.name))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "crm":
        try:
            x, e = a.action, a.engine
            if x == "status":
                print(crmsync.status(e or "all"))
            elif x == "sync":
                print(crmsync.sync(e, say=lambda m: print(m, flush=True)))
            elif not e:
                sys.exit("Name the engine, like: python dse.py crm " + x + " my-engine")
            elif x == "preview":
                print(crmsync.preview(e))
            else:
                print(crmsync.set_enabled(e, x == "on"))
        except ValueError as ex:
            sys.exit(str(ex))
    elif a.cmd == "doctor":
        print(doctor.run(a.offline))
    elif a.cmd == "brief":
        print(brief.run(a.top))
    elif a.cmd == "voices":
        try:
            x, t = a.action, ("" if a.target == "any" else a.target)
            a.figure, a.stratum, a.path = ("" if v == "any" else v for v in (a.figure, a.stratum, a.path))
            if x == "list":
                print(voices.list_figures(a.stratum, a.path))
            elif x == "show":
                print(voices.show(t or a.figure))
            elif x == "verify":
                print(voices.verify(t or a.figure))
            elif x == "fetch":
                print(voices.fetch(t or a.figure))
            elif x == "update":
                print(voices.update(t or a.figure))
            elif x == "ask":
                print(voices.ask(t, a.figure, a.stratum, a.path, a.n))
            elif x == "today":
                print(voices.today(a.stratum or "wisdom"))
            elif x == "setup":
                print(voices.setup(t or a.figure, a.minutes, a.force, say=lambda m: print(m, flush=True)))
            elif x == "repair":
                print(voices.repair(t or a.figure, say=lambda m: print(m, flush=True)))
            elif x == "note":
                print(voices.note(t or a.figure, a.text, a.source))
            else:
                p = voices.roster_problems()
                print("Roster rules: OK" if not p else "Roster problems:\n- " + "\n- ".join(p))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "cashlog":
        print(cashdesk.history(a.engine))
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
        by_cat = niches.by_category()
        total = sum(len(v) for v in by_cat.values())
        print(f"the app's {total} niches are built in too, in {len(by_cat)} groups (type any of them by name, like 'stump grinding'; python dse.py kinds --all lists them):")
        for cat, items in by_cat.items():
            print(f"  {cat:<28} {len(items):>3}")
            if a.all:
                for e in items:
                    k = e.get("same_as") or e["id"]
                    print(f"      {e['name']:<52} {k}" + ("" if places.extract_path(k).exists() else "   (built on first use)"))
        mine = places.custom_kinds()
        if mine:
            print("your own:")
            for k, v in mine.items():
                print(f"  {k:<20} {v['label']:<28} " + ("ready" if places.extract_path(k).exists() else "built on first use"))
    elif a.cmd == "packs":
        for p in sorted(chk.PACKS.glob("*.json")):
            pk = chk.load_pack(p.stem)
            print(f"{p.stem:<11} {pk['label']}: {pk.get('about', '')}")
        for pid in custom.pack_ids():
            pk = chk.load_pack(pid)
            print(f"{pid:<11} {pk['label']}: {pk.get('about', '')}")
        print("(make your own check for any business with: python dse.py mypack)")
    elif a.cmd == "mypack":
        try:
            print(custom.make_pack(a.name, a.sells, a.checks, a.opener, a.pages))
        except ValueError as e:
            sys.exit(str(e))
    elif a.cmd == "categories":
        cats = places.categories()
        hits = places.match_categories(a.search, cats) if a.search.strip() else sorted({n for _, n in cats})
        print(f"{len(hits)} Foursquare business categories" + (f" like '{a.search}'" if a.search.strip() else "") + ":")
        for n in hits[:60]:
            print("  " + n)
        print("Type any of these (or a plain word like 'photographer') as the business type in the lead tools: it is saved for you.")
        print("podcasts    The Broadcast Engine: python dse.py podcasts \"<topics>\"")
    elif a.cmd == "build":
        places.build([places.resolve_kind(k.strip()) for k in a.kinds.split(",") if k.strip()], a.country, a.source)
    elif a.cmd == "cities":
        cities.suggest(a.kind, a.country, a.source, a.levels, a.refresh, a.cover, a.min_pool)
    elif a.cmd == "tech":
        if a.target.lower().endswith(".csv"):
            tech.tech_file(a.target, a.max, not a.fast, a.out)
        else:
            print(tech.card(a.target, not a.fast))
    elif a.cmd == "research":
        from dse import research
        if a.action == "run":
            if not (a.kind or a.cities_file):
                sys.exit("Give a business type and cities, or --cities-file.")
            research.run(a.kind, a.cities, a.country or "US", a.cities_file, a.tiers, a.cap, a.strict, a.new_only, not a.no_enrich, a.icp, a.words, a.skip, a.source, a.max, owners=a.owners)
        elif a.action == "history":
            print(research.history())
        else:
            print(research.leads(a.kind, a.min_score, a.country, a.csv))
    elif a.cmd == "directors":
        from dse import chdirectors
        try:
            chdirectors.file(a.source, a.company_column, a.city_column, a.max, a.out)
        except (ValueError, RuntimeError) as e:
            sys.exit(str(e))
    elif a.cmd == "audit":
        if a.score:
            audit.score(a.target)
        else:
            audit.make(a.target, a.sample, a.seed, a.out)
    elif a.cmd == "directories":
        print(chr(10).join(registers.catalog_lines()))
    elif a.cmd == "registry":
        if a.action == "build":
            registers.build([places.resolve_kind(k.strip()) for k in a.kind.split(",") if k.strip()], a.file, a.sic)
        else:
            registers.find(places.resolve_kind(a.kind), a.towns, a.min_age, a.max, a.out, a.all)
    elif a.cmd == "countries":
        print(chr(10).join(countries.listing()))
    elif a.cmd == "find":
        kind, country = a.kind, a.country
        inferred = cities.from_file_name(a.cities_file) if a.cities_file else None
        if inferred:                                  # cities-gb-dentist.csv says it is for dentists in GB
            country, kind = country or inferred[0], kind or inferred[1]
        if not kind:
            sys.exit("Give a business type, or a cities file made by: python dse.py cities <type> --country <code>")
        places.find(kind, a.cities, a.miles, a.max, a.all, a.out, a.words, a.skip, country or "US", a.source, a.cities_file, a.tiers, a.strict)
    elif a.cmd == "check":
        if a.target.lower().startswith(("http://", "https://", "www.")) or (a.target.count(".") and not a.target.lower().endswith(".csv")):
            chk.check_one(a.pack, a.target, render=not a.fast, result_line=a.result_line)
        else:
            chk.check_file(a.pack, a.target, render=not a.fast, out=a.out)
    elif a.cmd == "list":
        if a.pack in PACK_KINDS and PACK_KINDS[a.pack] and a.kind not in PACK_KINDS[a.pack] and not places.kind_info(a.kind):
            print(f"Note: '{a.kind}' isn't one of the {a.pack} business types: treating it as a business type of your own.", file=sys.stderr)
        src = places.find(a.kind, a.cities, a.miles, a.max, a.all, "", a.words, a.skip, a.country, a.source, a.cities_file, a.tiers, a.strict)
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
