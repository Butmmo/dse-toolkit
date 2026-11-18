"""Tests for the leaks a real six-niche audit found (18 Nov 2026): parked and hijacked sites, unfilled templates, big brands, and niche words that were too wide.   python tests/test_leak_fixes.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import places as P  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


filler = "Our family firm has served the area for many years and we pride ourselves on honest advice. " * 12


class Resp:
    def __init__(self, text):
        self.status_code, self.text, self.url, self.headers = 200, text, "https://x.example/", {"content-type": "text/html"}


def page(title, body=""):
    return Resp(f"<html><head><title>{title}</title></head><body><p>{filler} {body}</p></body></html>")


def live(title, body, words):
    P.requests.get = lambda url, **k: page(title, body)
    P.SITE_TITLES.clear()
    return P.site_live("https://t.example", words)


DENT = P.kind_info("dentist")[2]
check("a normal dentist page is still 'title'", live("Dentist Leeds | Smile Clinic", "", DENT) == "title")
check("a parked page titled 'Domain parking page' is rejected, not 'thin'", live("Domain parking page", "dentist " * 5, DENT) == "")
check("a server default page ('Index of /', 'Welcome to nginx') is rejected", live("Index of /", "dentist " * 5, DENT) == "" and live("Welcome to nginx!", "dentist teeth " * 3, DENT) == "")
check("a site hijacked by a casino is rejected even though the dental words are in the page", live("Best Regulated Crypto Casinos for British Players", "dentist teeth dental " * 4, DENT) == "")
check("each spam word alone is enough: casino, betting, crypto", live("Top Online Casino Sites", "dentist teeth dental " * 4, DENT) == "" and live("Football Betting Tips", "dentist teeth dental " * 4, DENT) == "" and live("Buy Crypto Today", "dentist teeth dental " * 4, DENT) == "")
check("ordinary titles that contain a spam word inside another word are kept (Roofing Specialist has cialis in it, Escorted, Pornic)", all(live(t_, "", DENT) == "title" for t_ in ("Dental Specialist Leeds", "Dentist and Roofing Specialists", "Escorted Care Dental Surgery", "Pornic Dental Studio")), "")
check("an unfilled website template ({company} | Roofing {county}) is rejected", live("{company} | Roofing Contractor {county}", "roofing " * 5, P.kind_info("roofer")[2]) == "")
check("lorem ipsum in the page is rejected", live("Leeds Roofing", "Lorem ipsum dolor sit amet. roofing roofing roofing", P.kind_info("roofer")[2]) == "")
check("real names that only look like spam words are kept (a cryptic crossword cafe, a parked-car valet is not 'parked' page)", live("Cryptic Dental Studio Leeds", "", DENT) == "title" and live("Parkedge Dental Care", "", DENT) == "title")

# brands and platform pages
HOSTS = ["https://wendyf.zumba.com/x", "https://www.zumba.com/en-US/profile", "https://www.argos.co.uk/", "https://www.colgate.co.uk/app/x", "https://uk.siggroup.com/our-brands/x", "https://www.curvesinternational.com/x"]
OWN = ["https://zumbafitnessbywendy.co.uk", "https://argosroofing.co.uk", "https://www.colgatedental.example", "https://sigmaroofing.co.uk"]
check("brand and platform pages are not a business's own website", all(P.NOT_A_SITE.search(u) for u in HOSTS), str([u for u in HOSTS if not P.NOT_A_SITE.search(u)]))
check("look-alike business domains are kept", not any(P.NOT_A_SITE.search(u) for u in OWN), str([u for u in OWN if P.NOT_A_SITE.search(u)]))
CHAIN = ["Argos Ltd", "Specsavers Leeds", "PureGym Manchester", "mydentist Leeds", "Wickes Bristol", "Nuffield Health Fitness"]
check("big UK chains are dropped like the US ones", all(P.CHAINS.search(n) for n in CHAIN), str([n for n in CHAIN if not P.CHAINS.search(n)]))
check("independents with a similar name are kept", not any(P.CHAINS.search(n) for n in ["Gargosa Roofing", "Boots & Roots Landscaping", "Bristol Dental Care", "The Jewel Gym Studio"]))

# niche words
WED, DRV, PT = (P.kind_info(k)[2] for k in ("wedding-photographers", "driving-schools", "personal-trainers"))
check("the wide words are replaced for the three niches that drifted, and other niches are untouched", "photograph" not in WED and not DRV.startswith("driv|") and not PT.startswith("personal|") and "dent" in DENT and "roof" in P.kind_info("roofer")[2])
check("a photo shop is not a wedding photographer, a wedding photographer is", live("Leeds Photography Studio | Photo processing and printing", "We print photographs, photographs on canvas and passport photographs, photograph restoration", WED) not in ("title", "body") and live("Jo Smith | Wedding Photographer Leeds", "", WED) == "title")
check("a forklift school is not clearly a driving school (never title or body), driving lessons are", live("NTT Forklift Training", "Forklift driving school and training courses", DRV) not in ("title", "body") and live("Driving Lessons Leeds | Drive 321", "", DRV) == "title")
check("a motorcycle school and a school of motoring are kept", live("Leeds Motorcycle Training | Learn to drive", "", DRV) == "title" and live("Bentley School of Motoring", "", DRV) == "title")
check("a gym or personal training page is a personal trainer, a random training firm is not", live("Elliott Hayes Personal Training", "", PT) == "title" and live("Safety Training Ltd", "Fire marshal training and first aid training courses", PT) not in ("title", "body"))
check("the text uses no em dash", chr(0x2014) not in Path(P.__file__).read_text(encoding="utf-8"))

sys.exit(1 if fails else 0)
