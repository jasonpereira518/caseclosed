"""Canonical US jurisdiction identifiers shared by retrieval and corpus sync."""

JURISDICTIONS = {
    "federal": "United States", "al": "Alabama", "ak": "Alaska", "az": "Arizona",
    "ar": "Arkansas", "ca": "California", "co": "Colorado", "ct": "Connecticut",
    "de": "Delaware", "dc": "District of Columbia", "fl": "Florida", "ga": "Georgia",
    "hi": "Hawaii", "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "me": "Maine",
    "md": "Maryland", "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota",
    "ms": "Mississippi", "mo": "Missouri", "mt": "Montana", "ne": "Nebraska",
    "nv": "Nevada", "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico",
    "ny": "New York", "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio",
    "ok": "Oklahoma", "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas",
    "ut": "Utah", "vt": "Vermont", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
}

ALIASES = {name.lower(): code for code, name in JURISDICTIONS.items()}
ALIASES.update({"us": "federal", "u.s.": "federal", "united states": "federal"})


def normalize_jurisdiction(value: str | None) -> str | None:
    key = str(value or "").strip().lower()
    return key if key in JURISDICTIONS else ALIASES.get(key)
