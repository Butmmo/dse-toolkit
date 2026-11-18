"""Tests for the company register source and the lead-source catalog (18 Nov 2026): reads the Companies House file layout, keeps active companies of the right trade, finds them by town and age.   python tests/test_registers.py"""
import csv
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import places as P, registers as R  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except (ValueError, SystemExit) as e:
        return str(e)
    return None


TMP = Path(tempfile.mkdtemp(prefix="zz-registers-"))
P.DATA = R.DATA = TMP

# ---------------------------------------------------------------- the catalog
text = "\n".join(R.catalog_lines())
check("the catalog says which sources are built and which are not", "built: --source overture" in text and "built: registry build/find" in text and "not used" in text)
check("the catalog names the terms for every source", all(len(row) == 5 and row[3] for row in R.CATALOG))
check("every hand-made business type has register trade codes", set(P.HAND_MADE) <= set(R.SIC), str(set(P.HAND_MADE) - set(R.SIC)))
check("a niche from the app is matched by the words of its name", R.known("stump-grinding") and R.trade_words("stump-grinding") == ["grind", "stump"] or R.trade_words("stump-grinding") == ["grinding", "stump"], str(R.trade_words("stump-grinding")))
check("trade codes are 5 digits", all(len(c) == 5 and c.isdigit() for codes in R.SIC.values() for c in codes))

# ---------------------------------------------------------------- age
today = time.struct_time((2026, 11, 18, 0, 0, 0, 0, 0, 0))
check("a company's age is worked out from its incorporation date", R.age_years("18/11/2023", today) == 3.0 and R.age_years("18/11/2026", today) == 0.0 and R.age_years("", today) == 0.0 and R.age_years("garbage", today) == 0.0)

# ---------------------------------------------------------------- a small file in the real layout (the real header has stray spaces)
HEAD = ("CompanyName, CompanyNumber,RegAddress.CareOf,RegAddress.POBox,RegAddress.AddressLine1, RegAddress.AddressLine2,RegAddress.PostTown,RegAddress.County,RegAddress.Country,"
        "RegAddress.PostCode,CompanyCategory,CompanyStatus,CountryOfOrigin,DissolutionDate,IncorporationDate,Accounts.AccountRefDay,Accounts.AccountRefMonth,Accounts.NextDueDate,"
        "Accounts.LastMadeUpDate,Accounts.AccountCategory,Returns.NextDueDate,Returns.LastMadeUpDate,Mortgages.NumMortCharges,Mortgages.NumMortOutstanding,Mortgages.NumMortPartSatisfied,"
        "Mortgages.NumMortSatisfied,SICCode.SicText_1,SICCode.SicText_2,SICCode.SicText_3,SICCode.SicText_4,LimitedPartnerships.NumGenPartners,LimitedPartnerships.NumLimPartners,URI")
cols = [c.strip() for c in HEAD.split(",")]


def line(name, number, town, status, inc, sic1, sic2="", county="WEST YORKSHIRE", post="LS1 1AA"):
    d = dict.fromkeys(cols, "")
    d.update({"CompanyName": name, "CompanyNumber": number, "RegAddress.PostTown": town, "RegAddress.County": county, "RegAddress.PostCode": post,
              "CompanyCategory": "Private Limited Company", "CompanyStatus": status, "IncorporationDate": inc,
              "SICCode.SicText_1": sic1, "SICCode.SicText_2": sic2, "URI": f"http://business.data.gov.uk/id/company/{number}"})
    return ",".join('"' + d[c] + '"' for c in cols)


rows = [
    line("LEEDS SMILE DENTAL LTD", "00000001", "LEEDS", "Active", "01/03/2015", "86230 - Dental practice activities"),
    line("NEW TEETH LTD", "00000002", "LEEDS", "Active", "01/10/2026", "86230 - Dental practice activities"),                    # too young
    line("CLOSED DENTAL LTD", "00000003", "LEEDS", "Dissolved", "01/03/2010", "86230 - Dental practice activities"),                # not active
    line("BRADFORD DENTAL CARE LTD", "00000004", "BRADFORD", "Active", "01/03/2019", "86230 - Dental practice activities"),
    line("ASPEN DENTAL LEEDS LTD", "00000005", "LEEDS", "Active", "01/03/2012", "86230 - Dental practice activities"),              # a chain
    line("LEEDS PIPES LTD", "00000006", "LEEDS", "Active", "01/03/2016", "43220 - Plumbing, heat and air-conditioning installation"),
    line("LEEDS MULTI LTD", "00000007", "LEEDS", "Active", "01/03/2014", "41202 - Construction of domestic buildings", "43220 - Plumbing, heat and air-conditioning installation"),
    line("LEEDS CODERS LTD", "00000008", "LEEDS", "Active", "01/03/2014", "62020 - Information technology consultancy activities"),   # a trade we did not ask for
]
zpath = TMP / "BasicCompanyDataAsOneFile-2026-11-01.zip"
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("BasicCompanyDataAsOneFile-2026-11-01.csv", "﻿" + HEAD + "\n" + "\n".join(rows) + "\n")

R.build(["dentist", "plumber"], str(zpath))
dent = list(csv.DictReader(open(R.registry_path("dentist"), newline="", encoding="utf-8-sig")))
plum = list(csv.DictReader(open(R.registry_path("plumber"), newline="", encoding="utf-8-sig")))
check("only active companies of the asked trade are saved", {r["business"] for r in dent} == {"LEEDS SMILE DENTAL LTD", "NEW TEETH LTD", "BRADFORD DENTAL CARE LTD", "ASPEN DENTAL LEEDS LTD"}, str([r["business"] for r in dent]))
check("a company with the code in its second slot is found too", {r["business"] for r in plum} == {"LEEDS PIPES LTD", "LEEDS MULTI LTD"}, str([r["business"] for r in plum]))
check("the register file's stray spaces in the header do not matter", dent and dent[0]["city"] == "LEEDS" and dent[0]["company_number"] == "00000001" and dent[0]["postcode"] == "LS1 1AA")
check("a type with no trade codes is refused", "No trade codes" in (raises(R.build, ["no-such-business-type"], str(zpath)) or ""))
check("a missing file is explained", "File not found" in (raises(R.build, ["dentist"], str(TMP / "nope.zip")) or ""))

# ---------------------------------------------------------------- find by town
out = TMP / "leeds.csv"
R.find("dentist", "Leeds", min_age=1.0, cap=10, out=str(out))
got = list(csv.DictReader(open(out, newline="", encoding="utf-8-sig")))
check("find lists the older independent companies in the town", [r["business"] for r in got] == ["Leeds Smile Dental Ltd"], str([r["business"] for r in got]))
check("a company that is too young, dissolved, a chain or in another town is left out", not any(x in r["business"] for r in got for x in ("New Teeth", "Closed", "Aspen", "Bradford")))
check("each lead links to the register entry and says its source", got and got[0]["companies_house_url"].endswith("/company/00000001") and got[0]["source"].startswith("Companies House") and got[0]["country"] == "GB")
check("the lead has no website, so the next step can look for one", got and got[0]["website"] == "")
R.find("dentist", "Leeds; Bradford", min_age=0.0, cap=10, out=str(TMP / "two.csv"), keep_all=True)
two = list(csv.DictReader(open(TMP / "two.csv", newline="", encoding="utf-8-sig")))
check("several towns and --all work", {r["search_city"] for r in two} == {"Leeds", "Bradford"} and any("Aspen" in r["business"] for r in two), str([r["business"] for r in two]))
check("a missing list says how to build it", "registry build" in (raises(R.find, "gym", "Leeds") or ""))
check("find needs a town", "at least one town" in (raises(R.find, "dentist", " ; ") or ""))

sys.exit(1 if fails else 0)
