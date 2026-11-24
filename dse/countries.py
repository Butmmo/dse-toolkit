"""Countries and country groups the lead finder can search (Foursquare Open Source Places covers the whole world).

Two tiers, as decided 18 Nov 2026: tier 1 = rich markets first (UK, EU, Gulf, Israel, Japan, South Korea, Australasia, Singapore),
tier 2 = fast-developing markets after them (Turkey and neighbours, North Africa, South-East Asia, Southern and Eastern Africa, China).
A group name (like "eu") can be built in one go; searching ("find") needs one country, because a city name alone is ambiguous.

  python dse.py countries                 lists every group and its countries
  python dse.py build dentist --country eu
  python dse.py find dentist "Leeds" --country GB
"""
from __future__ import annotations

# ISO 3166-1 alpha-2 code -> English name (only the countries in a group below)
NAMES: dict[str, str] = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom",
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark",
    "EE": "Estonia", "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece", "HU": "Hungary", "IE": "Ireland",
    "IT": "Italy", "LV": "Latvia", "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands", "PL": "Poland",
    "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
    "AE": "United Arab Emirates", "SA": "Saudi Arabia", "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman",
    "JP": "Japan", "KR": "South Korea", "AU": "Australia", "NZ": "New Zealand", "FJ": "Fiji", "PG": "Papua New Guinea",
    "SB": "Solomon Islands", "VU": "Vanuatu", "WS": "Samoa", "TO": "Tonga",
    "SG": "Singapore", "MY": "Malaysia", "TH": "Thailand", "ID": "Indonesia", "PH": "Philippines", "VN": "Vietnam",
    "BN": "Brunei", "KH": "Cambodia", "LA": "Laos", "MM": "Myanmar", "TL": "Timor-Leste",
    "EG": "Egypt", "MA": "Morocco", "DZ": "Algeria", "TN": "Tunisia", "LY": "Libya",
    "ZA": "South Africa", "BW": "Botswana", "NA": "Namibia", "ZW": "Zimbabwe", "ZM": "Zambia", "MZ": "Mozambique",
    "MW": "Malawi", "AO": "Angola", "LS": "Lesotho", "SZ": "Eswatini", "MU": "Mauritius", "MG": "Madagascar",
    "KE": "Kenya", "TZ": "Tanzania", "UG": "Uganda", "RW": "Rwanda", "ET": "Ethiopia", "BI": "Burundi", "DJ": "Djibouti",
    "CN": "China",
    "IL": "Israel", "TR": "Turkey", "JO": "Jordan", "LB": "Lebanon", "IQ": "Iraq", "GE": "Georgia", "AM": "Armenia", "AZ": "Azerbaijan",
}

# group -> (tier, label, country codes)
GROUPS: dict[str, tuple[int, str, list[str]]] = {
    "us": (1, "United States", ["US"]),
    "north-america": (1, "North America", ["US", "CA"]),
    "uk": (1, "United Kingdom", ["GB"]),
    "eu": (1, "European Union", ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV",
                                 "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]),
    "gulf": (1, "Arab Gulf", ["AE", "SA", "QA", "KW", "BH", "OM"]),
    "israel": (1, "Israel", ["IL"]),
    "japan": (1, "Japan", ["JP"]),
    "korea": (1, "South Korea", ["KR"]),
    "australasia": (1, "Australasia", ["AU", "NZ", "FJ", "PG", "SB", "VU", "WS", "TO"]),
    "singapore": (1, "Singapore", ["SG"]),
    "north-africa": (2, "North Africa", ["EG", "MA", "DZ", "TN", "LY"]),
    "south-east-asia": (2, "South-East Asia", ["MY", "TH", "ID", "PH", "VN", "BN", "KH", "LA", "MM", "TL"]),
    "southern-africa": (2, "Southern Africa", ["ZA", "BW", "NA", "ZW", "ZM", "MZ", "MW", "AO", "LS", "SZ", "MU", "MG"]),
    "eastern-africa": (2, "Eastern Africa", ["KE", "TZ", "UG", "RW", "ET", "BI", "DJ"]),
    "china": (2, "China", ["CN"]),
    "turkey-and-neighbours": (2, "Turkey and neighbours", ["TR", "JO", "LB", "IQ", "GE", "AM", "AZ"]),
}

# Not included on purpose: countries under broad sanctions (Iran, Syria). Cyprus is in the EU group.

# Countries where business websites are normally in English. The built-in "does the site talk about this trade" check uses
# English words, so it is applied only here: elsewhere it would throw away real businesses whose sites are in their own language.
ENGLISH: set[str] = {"US", "CA", "GB", "IE", "AU", "NZ", "SG", "ZA", "KE", "UG", "TZ", "ZM", "ZW", "BW", "NA", "MW", "MU", "FJ", "PG",
                     "SB", "VU", "WS", "TO", "MY", "PH", "LS", "SZ", "RW", "MT", "CY", "BN", "BI", "DJ"}


def resolve(text: str) -> list[str]:
    """'GB', 'gb', 'eu' or 'uk,gulf' -> country codes in order, no repeats. Raises ValueError for anything not known (never guesses)."""
    out: list[str] = []
    for part in [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]:
        key = part.lower().replace(" ", "-").replace("_", "-")
        if key in GROUPS:
            codes = GROUPS[key][2]
        elif part.upper() in NAMES:
            codes = [part.upper()]
        else:
            raise ValueError(f"Unknown country or group '{part}'. Run: python dse.py countries")
        out += [c for c in codes if c not in out]
    if not out:
        raise ValueError("Give a country code (like GB) or a group (like eu). Run: python dse.py countries")
    return out


def one(text: str) -> str:
    """Exactly one country for searching; a group of several is refused, because 'Paris' or 'Springfield' alone could be anywhere."""
    codes = resolve(text)
    if len(codes) != 1:
        raise ValueError(f"'{text}' is {len(codes)} countries ({', '.join(codes[:6])}{'...' if len(codes) > 6 else ''}). To search, pick one country code, like {codes[0]}.")
    return codes[0]


def english(code: str) -> bool:
    return code in ENGLISH


def listing() -> list[str]:
    """Lines for `python dse.py countries`, tier 1 first."""
    lines: list[str] = []
    for tier, title in ((1, "Tier 1 (rich markets, do these first)"), (2, "Tier 2 (fast-developing markets)")):
        lines.append(title)
        for key, (t, label, codes) in GROUPS.items():
            if t == tier:
                lines.append(f"  {key:<16} {label:<18} {' '.join(codes)}")
    return lines
