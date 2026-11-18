"""Builds dse/niche_catalog.json: the app's whole niche list (512 business types) as built-in business types for the lead finder.

The niche list lives in the app (DBI Citadel, src/lib/smb-niches.ts). Export it, then run this:

  node -e "import('./src/lib/smb-niches.ts').then(N=>console.log(JSON.stringify(N.NICHE_OPTIONS.map(o=>({name:o.name,term:o.term,category:o.category,door:o.door})))))" > niches.json
  python tools/build_niche_catalog.py niches.json

Foursquare's open data has only about 1,300 business categories, far coarser than 512 niches, so each niche gets the 1 to 4 NEAREST Foursquare categories
(by the rules below, most specific first) plus words from its own name. The finder keeps a business only if its website uses one of those words, which is what
narrows "Tree Service" down to "Stump Grinding". A niche that is the same as one of the 26 hand-made types points at that type instead (ALIASES).
Needs the Foursquare category list (python dse.py categories, which needs the free HF_TOKEN once) so every category name is checked against the real list.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import places as P  # noqa: E402

MAX_CATS = 4

# niche name (exactly as in the app) -> a hand-made built-in type it is the same as
ALIASES = {
    "Dentists & Orthodontists": "dentist", "Chiropractors": "chiropractor", "Physiotherapists": "physical-therapy", "Optometrists": "optometrist",
    "Veterinary Clinics": "veterinarian", "HVAC, Plumbing & Electrical (Independents Only)": "hvac", "Emergency Plumbing & Drain Snaking": "plumber",
    "Roofing Contractors": "roofer", "Landscaping & Lawn Care": "landscaper", "Hair Salons & Barbershops": "hair-salon", "Day Spas": "spa",
    "Law Firms": "law-office", "Insurance Agencies": "insurance", "Real Estate Agents": "real-estate", "Gyms & Fitness Studios": "gym",
    "Moving Companies & Storage": "movers", "Interior Designers": "interior-design", "Home Care Agencies": "home-care",
    "Assisted Living Facilities": "assisted-living", "Nursing Homes and Care Homes": "nursing-home", "Pest & Wildlife Control": "pest-control",
    "Commercial Office Cleaning": "cleaning",
}

# (regex on the lower-cased niche name, Foursquare categories). Every matching rule adds its categories, in this order, up to MAX_CATS.
RULES: list[tuple[str, list[str]]] = [
    # auto and transport
    (r"moving|movers|senior move", ["Mover"]),
    (r"tow|roadside", ["Towing Service"]),
    (r"transmission", ["Transmissions Shop"]),
    (r"oil change|quick lube", ["Oil Change Service"]),
    (r"tire", ["Tire Repair Shop"]),
    (r"motorcycle", ["Motorcycle Repair Shop", "Motorcycle Dealership"]),
    (r"classic car", ["Classic and Antique Car Dealership", "Automotive Repair Shop"]),
    (r"used car", ["Used Car Dealership"]),
    (r"car rental", ["Rental Car Location"]),
    (r"inspection & emissions|emissions", ["Vehicle Inspection Station", "Smog Check Shop"]),
    (r"driving school", ["Driving School"]),
    (r"car wash|detailing|ceramic coating|paint protection|vehicle wrap|window tinting shops", ["Car Wash and Detail"]),
    (r"mechanic|auto repair|auto electrical|brake|muffler|car ac|battery|truck & trailer|rv repair|collision|auto body|auto glass|dent repair|auto locksmith|car audio|upfitter|off-road|food truck builder|wheelchair accessible vehicle|custom van", ["Automotive Repair Shop", "Automotive Service"]),
    (r"boat|marine", ["Boat Dealership", "Harbor or Marina"]),
    (r"limousine|limo", ["Limo Service"]),
    (r"charter bus|coach rental", ["Charter Bus"]),
    (r"taxi|shuttle", ["Taxi", "Transportation Service"]),
    (r"courier|delivery|freight|trucking|fleet|dispatch|shipping & packing", ["Shipping, Freight, and Material Transportation Service"]),
    (r"junk car", ["Salvage Yard"]),
    # home and building trades
    (r"garage door|overhead door", ["Garage Door Supplier", "Home Improvement Service"]),
    (r"chimney", ["Chimney Sweep"]),
    (r"pest|wildlife|mosquito|bee removal", ["Pest Control Service"]),
    (r"locksmith|lock\b", ["Locksmith"]),
    (r"security|cctv|alarm|fire sprinkler|extinguisher", ["Security and Safety"]),
    (r"septic|sewer|sewage", ["Sewer Contractor", "Plumber"]),
    (r"plumb|drain|water heater|water softener|filtration|tankless|tub-to-shower|bathtub|well drilling|pumps", ["Plumber"]),
    (r"refrigeration", ["Refrigeration and Ice Supplier", "Heating, Ventilating and Air Conditioning Contractor"]),
    (r"hvac|heating|cooling|mini-split|geothermal|ductless|air duct", ["Heating, Ventilating and Air Conditioning Contractor"]),
    (r"electric|ev charger|generator|panel upgrade|ceiling fan|lighting install", ["Electrician"]),
    (r"solar", ["Renewable Energy Service", "Electrician"]),
    (r"smart home|home theater|home theatre|av &|conferencing|acoustic", ["Audiovisual Service", "Electrician"]),
    (r"network cabling|it support|managed services|voip|business phone", ["IT Service", "Telecommunication Service"]),
    (r"\broof|gutter|skylight|solar tube", ["Roofer"]),
    (r"siding|stucco|insulation|soundproof|weatherization|energy audit", ["Home Improvement Service", "General Contractor"]),
    (r"\bpaint(?!less| protection)|drywall|plaster|wallpaper|popcorn ceiling|texture|decorative finish|mural", ["Painter"]),
    (r"floor|tile|grout|carpet install|stone install|mosaic", ["Carpet and Flooring Contractor"]),
    (r"(?<!outdoor )kitchen(?! equipment)", ["Kitchen Remodeler"]),
    (r"bathroom|bath designers|shower door|tub-to-shower|bathtub", ["Bathroom Contractor"]),
    (r"cabinet|closet|millwork|carpent|staircase|railing|trim|furniture makers|woodwork", ["Carpenter"]),
    (r"countertop|stone and countertop|stone & countertop", ["Home Improvement Service"]),
    (r"^(?!.*(auto|car |vehicle|clean)).*(\bwindows?\b|\bdoors?\b|blinds|shutters|drapery|tinting|glass|mirror|screen repair|conservator)", ["Doors and Windows Contractor"]),
    (r"\bdeck|\bpatio|pergola|porch|sunroom|gazebo|outdoor kitchen|bbq|fire pit|outdoor fireplace|outdoor living|outdoor structure", ["Deck and Patio Contractor"]),
    (r"fence|gate", ["Fence Contractor"]),
    (r"pool|swim spa|hot tub", ["Swimming Pool Maintenance and Service", "Swimming Pool Supply Store"]),
    (r"tree|stump|brush clearing|forestry|arborist|firewood", ["Tree Service"]),
    (r"landscap|lawn|garden|irrigation|sprinkler repair|irrigation|turf|sod |mulch|xeriscape|raised bed|drainage|pond|water feature|aeration|fertiliz|topsoil", ["Landscaper and Gardener"]),
    (r"garden cent|plant nurser", ["Garden Center"]),
    (r"concrete|mason|brick|asphalt|paving|paver|retaining|hardscape|sealcoat|striping|excavat|grading|foundation|seawall|dock", ["Construction", "General Contractor"]),
    (r"builders|home additions|addition and extension|basement|attic|loft|adu\b|tiny home|modular|prefab|log home|timber|remodel|renovation|historic home restoration|fit-out|tenant improvement|demolition|storm damage|garage conversion|\bbarn|\bshed|carport|detached garage|post-frame|project manager|handyman", ["General Contractor"]),
    (r"handyman|assembly|tv mounting|accessibility|aging-in-place|caretaker|appliance", ["Home Improvement Service", "Home Service"]),
    (r"appliance repair", ["Repair Service"]),
    (r"property manager", ["Property Management Office"]),
    (r"land surveyor", ["Building and Land Surveyor"]),
    (r"home inspect", ["Home Inspection"]),
    (r"weld|metal fabricat|ironwork|cnc|machining|laser cutting|3d print|hydraulic", ["Welding Service", "Machine Shop"]),
    # cleaning and restoration
    (r"radon|asbestos|lead abatement|mold|biohazard|crime scene|hoarding|water damage|fire & smoke|contents pack-out", ["Professional Cleaning Service", "Home Service"]),
    (r"clean|janitorial|pressure washing|graffiti|solar panel clean", ["Professional Cleaning Service"]),
    (r"laundry|linen", ["Laundry Service"]),
    (r"junk|hauling|dumpster|cash for cars|portable toilet|grease trap|hood clean", ["Waste Management Service"]),
    (r"shredding", ["Business Service"]),
    (r"pallet|recycl", ["Recycling Facility", "Industrial Equipment Supplier"]),
    (r"rental|forklift|tool & equipment|temporary fencing|portable storage", ["Equipment Rental Service", "Rental Service"]),
    # business services
    (r"signage|print|wide-format|embroidery|engraving|stationery|invitation", ["Print Store"]),
    (r"trade-show|exhibit", ["Event Service"]),
    (r"industrial equipment|racking|shelving", ["Industrial Equipment Supplier"]),
    (r"bookkeep|accountant|tax prepar", ["Accounting and Bookkeeping Service"]),
    (r"office furniture", ["Furniture and Home Store"]),
    (r"commercial kitchen equipment", ["Kitchen Supply Store"]),
    (r"packaging|labels", ["Packaging Supply Store"]),
    (r"copier|printer service", ["Business Service", "Repair Service"]),
    (r"notary", ["Notary"]),
    (r"vending", ["Vending Machine"]),
    (r"water treatment|water filtration", ["Water Treatment Service"]),
    # design and build
    (r"interior design|stager|design-build", ["Interior Designer"]),
    (r"architect|drafting|home plan|residential designers", ["Architecture Firm"]),
    (r"lighting and showroom|lighting designers", ["Lighting Store"]),
    (r"upholstery", ["Upholstery Service"]),
    (r"antique restor|refinishers", ["Art Restoration Service"]),
    (r"rug|flooring showroom", ["Carpet Store"]),
    (r"3d visual|model and", ["Design Studio"]),
    # pets
    (r"veterinar|equine vet|vet clinics", ["Veterinarian"]),
    (r"groomers", ["Pet Grooming Service"]),
    (r"dog trainers|pet sitters|dog walkers|boarding|kennel|dog daycare|cat cafe|cremation", ["Pet Service", "Pet Sitting and Boarding Service"]),
    (r"aquarium|exotic pet", ["Pet Supplies Store"]),
    (r"horse|equestrian|farrier|\blivery\b", ["Equestrian Facility", "Stable"]),
    # professional
    (r"coaches & consultants|consultants", ["Management Consultant", "Business and Strategy Consulting Office"]),
    (r"immigration", ["Immigration Attorney", "Law Office"]),
    (r"\blaw\b|lawyer|attorney|attorneys|solicitor|conveyanc|trademark", ["Law Office", "Legal Service"]),
    (r"financial planner", ["Financial Planner"]),
    (r"mortgage", ["Loans Agency", "Financial Service"]),
    (r"bail bond", ["Legal Service", "Financial Service"]),
    (r"recruiter|staffing|hr ", ["Employment Agency", "Human Resources Agency"]),
    (r"translation", ["Translation Service"]),
    (r"investigator", ["Business and Professional Services"]),
    (r"business broker", ["Business Broker"]),
    # health
    (r"periodont|oral surgeon", ["Oral Surgeon", "Dentist"]),
    (r"\bdent(al|ist|ists)\b|orthodont|aligner", ["Dentist"]),
    (r"med spa|aesthetic|laser and skin|esthetician|skin", ["Skin Care Clinic", "Spa"]),
    (r"physio|occupational|speech therap", ["Physical Therapy Clinic", "Rehabilitation Center"]),
    (r"optomet|eye surgery", ["Optometrist", "Eyecare Store", "Ophthalmologist"]),
    (r"hearing", ["Other Healthcare Professional"]),
    (r"podiatr", ["Podiatrist"]),
    (r"acupunct|naturopath|holistic", ["Acupuncture Clinic", "Alternative Medicine Clinic"]),
    (r"massage", ["Massage Clinic"]),
    (r"nutrition|dietitian", ["Nutritionist"]),
    (r"pharmac", ["Pharmacy"]),
    (r"urgent care", ["Urgent Care Center"]),
    (r"fertility|ivf", ["Women's Health Clinic", "Healthcare Clinic"]),
    (r"plastic and cosmetic surgeons|hair transplant", ["Plastic Surgeon", "Skin Care Clinic"]),
    (r"therapists and counsel|mental health", ["Mental Health Clinic", "Psychologist", "Mental Health Service"]),
    (r"weight loss", ["Weight Loss Center"]),
    (r"sports medicine", ["Sports Medicine Clinic"]),
    (r"dermatolog", ["Dermatologist"]),
    (r"sleep", ["Medical Center", "Healthcare Clinic"]),
    # beauty
    (r"hair salon|barber|wig|hair extension|beard|hair stylist", ["Hair Salon", "Barbershop"]),
    (r"nail", ["Nail Salon"]),
    (r"eyelash|microblading|permanent makeup|brow", ["Brow Bar", "Skin Care Clinic"]),
    (r"tanning", ["Tanning Salon"]),
    (r"day spa", ["Spa"]),
    (r"waxing|hair removal", ["Hair Removal Service"]),
    (r"bridal salon|bridal boutique", ["Bridal Store"]),
    (r"makeup|henna|bridal hair|bridal beauty", ["Health and Beauty Service"]),
    (r"piercing", ["Body Piercing Shop"]),
    (r"tailor|alteration|bespoke|dressmaker|fashion designer|custom clothing", ["Tailor"]),
    # food and hospitality
    (r"^restaurants", ["Restaurant", "Cafe, Coffee, and Tea House"]),
    (r"bakeri|cake|custom bakers", ["Bakery", "Pastry Shop"]),
    (r"food truck", ["Food Truck"]),
    (r"caterer|private chef|meal prep|catering", ["Caterer"]),
    (r"boutique hotels", ["Hotel", "Bed and Breakfast"]),
    (r"venue|banquet|function hall", ["Wedding Hall", "Event Space"]),
    (r"coffee roaster", ["Coffee Roaster"]),
    (r"juice|smoothie", ["Juice Bar", "Smoothie Shop"]),
    (r"ice cream", ["Ice Cream Parlor"]),
    (r"pizzeria", ["Pizzeria"]),
    (r"bars and pubs|bartend|mobile bar", ["Bar", "Pub", "Caterer"]),
    (r"brewer|taproom", ["Brewery"]),
    (r"vineyard|winer", ["Winery", "Vineyard"]),
    (r"vacation rental", ["Vacation Rental"]),
    (r"butcher", ["Butcher", "Meat and Seafood Store"]),
    # fitness
    (r"personal trainer|performance coach", ["Personal Trainer"]),
    (r"yoga", ["Yoga Studio"]),
    (r"pilates", ["Pilates Studio"]),
    (r"martial arts", ["Martial Arts Dojo"]),
    (r"golf", ["Golf Course", "Golf Club", "Golf Driving Range"]),
    (r"swim school", ["Swim School"]),
    (r"tennis", ["Tennis Club"]),
    (r"climbing", ["Climbing Gym"]),
    (r"gymnastics", ["Gymnastics Center"]),
    (r"ski and snowboard", ["Snow Sports"]),
    (r"\bgym|crossfit|boxing|fitness", ["Gym", "Gym and Studio"]),
    # creative and events
    (r"wedding planner|event planner|celebrant|officiant|party planner|experience planner|decor and styling|balloon", ["Event Service", "Entertainment Service"]),
    (r"photograph|360 virtual|matterport|photo book", ["Photographer", "Photography Studio", "Photography Service"]),
    (r"video|film and|film production|animation|podcast|recording|drone", ["Film Studio", "Media Agency", "Recording Studio"]),
    (r"florist", ["Flower Store"]),
    (r"jewel", ["Jewelry Store"]),
    (r"art galler", ["Art Gallery"]),
    (r"tattoo", ["Tattoo Parlor"]),
    (r"music teacher|music school", ["Music School"]),
    (r"party and event rentals|\btent\b|marquee|bounce house|inflatable|costume|formalwear|kids party", ["Party Supply Store", "Rental Service", "Party Center"]),
    (r"\bdjs\b|live bands|sound, lighting", ["Entertainment Service", "Audiovisual Service"]),
    (r"branding|graphic design|web design", ["Creative Service", "Website Designer", "Design Studio", "Advertising Agency"]),
    (r"framing", ["Framing Store"]),
    (r"dance", ["Dance Studio"]),
    (r"pottery|art class|sculptor|art studio|illustrators|henna", ["Art Studio", "Art School"]),
    (r"leather|shoemaker", ["Leather Goods Store", "Shoe Repair Service"]),
    (r"kids party", ["Entertainment Service"]),
    # education
    (r"tutor|test prep|maths|learning support", ["Tutoring Service", "Adult Education"]),
    (r"private school", ["Private School"]),
    (r"^nurseries and preschools|preschool", ["Preschool", "Nursery School"]),
    (r"^daycare|after-school|nanny|babysit", ["Daycare", "Child Care Service"]),
    (r"language school", ["Language School"]),
    (r"coding", ["Computer Training School", "Tutoring Service"]),
    (r"art and craft", ["Art School", "Art Studio"]),
    (r"summer camp", ["Summer Camp"]),
    (r"admissions", ["Career Counselor", "Tutoring Service"]),
    (r"flight school", ["Flight School"]),
    (r"training school", ["Trade School"]),
    # senior care
    (r"companion care", ["Home Health Care Service", "Senior Citizen Service"]),
    (r"memory care", ["Assisted Living Service", "Assisted Living"]),
    (r"palliative|hospice", ["Hospice"]),
    (r"geriatric", ["Senior Citizen Service", "Geriatric Doctor"]),
    (r"mobility equipment|stairlift", ["Mobility Store", "Medical Supply Store"]),
    (r"funeral", ["Funeral Home"]),
    (r"adult day care", ["Senior Citizen Service", "Disabled Persons Service"]),
]

# when no rule fits: the nearest category for the niche's group in the app
FALLBACK = {
    "Home trades": ["Home Improvement Service", "General Contractor"], "Outdoor and property": ["Landscaper and Gardener", "Home Service"],
    "Cleaning and restoration": ["Professional Cleaning Service", "Home Service"], "Auto and transport": ["Automotive Service"],
    "B2B local services": ["Business Service"], "Design and build": ["Design Studio", "General Contractor"], "Pets": ["Pet Service"],
    "Professional services": ["Business and Professional Services"], "Health and wellness": ["Healthcare Clinic"],
    "Beauty and personal": ["Health and Beauty Service"], "Food and hospitality": ["Restaurant"], "Fitness and sport": ["Sports and Recreation"],
    "Creative and events": ["Creative Service"], "Education and kids": ["Education"], "Senior and home care": ["Senior Citizen Service"],
}

# words that say nothing about the trade, so are not used to check a website
GENERIC = set("""and the for with from your our independents independent only specialist specialists pros pro installers installer contractors contractor company companies
providers provider studios studio shops shop centres centers centre center clinics clinic services service agencies agency firms firm makers builders builder designers designer
repair replacement installation installations commercial residential custom local home luxury general independent""".split())


def words_for(name: str) -> str:
    out = []
    for tok in re.findall(r"[a-z]{4,}", re.sub(r"\([^)]*\)", " ", name.lower())):
        if tok in GENERIC:
            continue
        stem = re.sub(r"(ings?|ers|ies|es|s)$", "", tok) if len(tok) > 5 else tok
        out.append(stem if len(stem) >= 4 else tok)
    return "|".join(dict.fromkeys(out))


def categories_for(name: str, group: str, valid: set[str]) -> list[str]:
    low = name.lower()
    picked: list[str] = []
    for pat, cats in RULES:
        if re.search(pat, low):
            for c in cats:
                if c not in picked:
                    picked.append(c)
    chosen = picked[:MAX_CATS] or FALLBACK[group]
    bad = [c for c in chosen if c not in valid]
    if bad:
        raise SystemExit(f"Unknown Foursquare category {bad} for '{name}'")
    return chosen


def slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower().replace("&", " and "))).strip("-")


def main(src: str) -> None:
    niches = json.load(open(src, encoding="utf-8"))
    valid = {n for _, n in P.categories()}
    for alias in ALIASES.values():
        assert alias in P.KINDS, alias
    out, seen_slugs, fallback_only = [], set(), []
    for n in niches:
        s = slug(n["name"])
        assert s not in seen_slugs, f"duplicate id {s}"
        seen_slugs.add(s)
        row = {"id": s, "name": n["name"], "term": n["term"], "category": n["category"], "door": n["door"]}
        if n["name"] in ALIASES:
            row["same_as"] = ALIASES[n["name"]]
        else:
            row["fsq"] = categories_for(n["name"], n["category"], valid)
            row["words"] = words_for(n["name"])
            if not any(re.search(p, n["name"].lower()) for p, _ in RULES):
                fallback_only.append(n["name"])
        out.append(row)
    dst = ROOT / "dse" / "niche_catalog.json"
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out)} niches written to {dst} ({sum(1 for r in out if 'same_as' in r)} point at a hand-made type)")
    print(f"{len(fallback_only)} had no specific rule and use their group's nearest category:")
    print("; ".join(fallback_only))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
