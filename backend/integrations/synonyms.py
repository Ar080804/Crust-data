"""Owner: Sunil. Title normalisation: function family + seniority rank."""
import re

# Words that mean the same job family. Add more as needed.
FAMILIES = {
    "warehouse": {"warehouse", "warehousing", "fulfilment", "fulfillment", "inventory", "dc", "distribution"},
    "logistics": {"logistics", "supply", "chain", "scm", "transport", "transportation", "shipping",
                  "delivery", "last-mile", "lastmile", "fleet", "3pl", "freight"},
    "operations": {"operations", "ops", "operation"},
    "procurement": {"procurement", "sourcing", "purchase", "purchasing", "buyer", "vendor"},
    "engineering": {"engineer", "engineering", "developer", "software", "sde", "programmer"},
    "product": {"product", "pm"},
    "data": {"data", "analytics", "analyst", "scientist", "bi"},
    "sales": {"sales", "business", "bd", "account"},
    "events": {"organizer", "organiser", "coordinator", "events", "event", "fest"},
}
# Operations is adjacent to warehouse/logistics, so treat them as compatible.
COMPATIBLE = [{"warehouse", "logistics", "operations", "procurement"}]

# Higher = more senior. First match wins, so order from most to least senior.
SENIORITY = [
    (6, r"\b(founder|co-founder|ceo|coo|cto|chief|president)\b"),
    (5, r"\b(vp|vice president|director|head)\b"),
    (4, r"\b(senior manager|sr\.? manager|general manager|gm)\b"),
    (3, r"\b(manager|lead|supervisor|incharge|in-charge)\b"),
    (2, r"\b(senior|sr\.?|specialist|consultant)\b"),
    (1, r"\b(associate|executive|analyst|engineer|coordinator|officer|organizer|organiser|member)\b"),
    (0, r"\b(intern|internship|trainee|apprentice|student|volunteer)\b"),
]
CRUST_SENIORITY = {"intern": 0, "entry level": 1, "senior": 2, "manager": 3, "director": 5,
                   "vice president": 5, "cxo": 6, "owner / partner": 6, "owner": 6, "partner": 6}


def _words(title: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\-]+", (title or "").lower()))


def families(title: str) -> set[str]:
    w = _words(title)
    return {f for f, keys in FAMILIES.items() if w & keys}


def same_family(a: str, b: str) -> bool:
    fa, fb = families(a), families(b)
    if not fa or not fb:
        return False
    if fa & fb:
        return True
    return any(fa & g and fb & g for g in COMPATIBLE)


def seniority(title: str, crust_level: str | None = None) -> int | None:
    t = (title or "").lower()
    for rank, pat in SENIORITY:
        if re.search(pat, t):
            return rank
    if crust_level:
        return CRUST_SENIORITY.get(crust_level.strip().lower())
    return None
