"""Owner: Sunil. Cache every raw response in data/crustdata_cache/<key>.json and commit it.

verify() NEVER raises: any failure (network, 429, no profile) becomes an "unverifiable" claim,
because backend/app/adapters.py only catches NotImplementedError.
"contradicted" drops the expert, so it is only returned on clear evidence."""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import synonyms

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "crustdata_cache"
load_dotenv(ROOT / ".env")

API = "https://api.crustdata.com/person/enrich"
FIELDS = ["basic_profile", "experience.employment_details.current", "experience.employment_details.past"]
SOURCE = "crustdata:person_enrich"
IST = timezone(timedelta(hours=5, minutes=30))
NOW_YEAR = datetime.now(IST).year

_CLAIM_RE = re.compile(
    r"^\s*(?P<title>.+?)\s+(?:at|@)\s+(?P<company>.+?)"
    r"(?:,\s*(?P<y1>\d{4})\s*[-–—to ]+\s*(?P<y2>\d{4}|\d{2}|present|current|now|till date))?\s*$",
    re.I)
_COMPANY_NOISE = {"pvt", "private", "ltd", "limited", "inc", "llp", "llc", "india", "technologies",
                  "technology", "tech", "solutions", "services", "the", "co", "company", "corp", "group"}


# ---- fetch + cache ----------------------------------------------------------

def _cache_path(expert: dict) -> Path:
    key = re.sub(r"[^A-Za-z0-9_\-]", "_", str(expert.get("expert_id") or "unknown"))
    return CACHE / f"{key}.json"


def _norm_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower()).rstrip("/")


def fetch(expert: dict, max_retries: int = 3) -> tuple[list | None, str]:
    """Return (raw_response, fetched_at). Reads cache first; calls the API only on a miss."""
    url = expert.get("linkedin_url") or ""
    path = _cache_path(expert)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Planted test profiles have no public URL in the pool, so their cache is matched by expert_id alone.
        if raw and (not url or _norm_url(raw[0].get("matched_on", "")) == _norm_url(url)):
            fetched = datetime.fromtimestamp(path.stat().st_mtime, IST).isoformat(timespec="seconds")
            return raw, fetched
    if not url or "TODO" in url:
        return None, _now()
    key = os.getenv("CRUSTDATA_API_KEY", "").strip()
    if not key:
        return None, _now()
    for _ in range(max_retries):
        r = httpx.post(API, timeout=60, json={"professional_network_profile_urls": [url], "fields": FIELDS},
                       headers={"authorization": f"Bearer {key}", "content-type": "application/json",
                                "x-api-version": "2025-11-01"})
        if r.status_code == 429:
            time.sleep(min(int(r.headers.get("x-ratelimit-reset", "10") or 10), 65) + 1)
            continue
        r.raise_for_status()
        raw = r.json()
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        return raw, _now()
    raise RuntimeError("Crustdata rate limit: retries exhausted")


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def roles_from(raw: list | None) -> list[dict] | None:
    """Flatten to [{title, company, start, end, seniority_level}]. None = no profile matched."""
    if not raw or raw[0].get("match_status") != "matched" or not raw[0].get("matches"):
        return None
    emp = (raw[0]["matches"][0].get("person_data", {}).get("experience", {}) or {}).get("employment_details", {}) or {}
    out = []
    for r in (emp.get("current") or []) + (emp.get("past") or []):
        out.append({"title": r.get("title") or "", "company": r.get("name") or "",
                    "start": r.get("start_date"), "end": r.get("end_date"),
                    "seniority_level": r.get("seniority_level") or ""})
    return out


# ---- claim matching ---------------------------------------------------------

def parse_claim(text: str) -> dict:
    m = _CLAIM_RE.match(text or "")
    if not m:
        title, _, company = (text or "").rpartition(",")
        return {"title": title.strip() or text, "company": company.strip(), "y1": None, "y2": None}
    y2 = m["y2"]
    if y2:
        y2 = NOW_YEAR if not y2.isdigit() else (2000 + int(y2) if len(y2) == 2 else int(y2))
    return {"title": m["title"].strip(), "company": m["company"].strip(),
            "y1": int(m["y1"]) if m["y1"] else None, "y2": y2}


def _company_tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in _COMPANY_NOISE and len(w) > 1}


def same_company(a: str, b: str) -> bool:
    ta, tb = _company_tokens(a), _company_tokens(b)
    return bool(ta and tb and (ta & tb))


def _year(d: str | None) -> int | None:
    return int(d[:4]) if d else None


def _months(r: dict) -> int | None:
    if not r["start"]:
        return None
    s = datetime.fromisoformat(r["start"][:10])
    e = datetime.fromisoformat(r["end"][:10]) if r["end"] else datetime.now()
    return max(1, (e.year - s.year) * 12 + e.month - s.month)


def describe(r: dict) -> str:
    y1, y2 = _year(r["start"]), _year(r["end"])
    span = f"{y1 or '?'}–{y2 or 'present'}"
    mo = _months(r)
    dur = f" ({mo} mo)" if mo is not None and mo < 24 else ""
    return f"{r['title'] or 'Unknown title'} at {r['company']}, {span}{dur}"


def _check(claim: dict, role: dict) -> tuple[str, str]:
    """Return (status, reason) for one claim against one role at the same company."""
    c_rank = synonyms.seniority(claim["title"])
    r_rank = synonyms.seniority(role["title"], role["seniority_level"])
    if c_rank is not None and r_rank is not None and c_rank - r_rank >= 2:
        return "contradicted", "claimed seniority not supported"
    title_ok = synonyms.same_family(claim["title"], role["title"]) or \
        claim["title"].strip().lower() == role["title"].strip().lower()
    if not title_ok:
        if synonyms.families(claim["title"]) and synonyms.families(role["title"]):
            return "contradicted", "different role"
        return "unverifiable", "title could not be matched"
    if claim["y1"]:
        rs, re_ = _year(role["start"]), _year(role["end"]) or NOW_YEAR
        if rs and (rs > claim["y1"] + 1 or re_ < (claim["y2"] or NOW_YEAR) - 1):
            return "contradicted", "dates do not match"
    return "verified", ""


def verify_claim(text: str, roles: list[dict] | None) -> tuple[str, str]:
    if roles is None:
        return "unverifiable", "No Crustdata profile matched this LinkedIn URL"
    claim = parse_claim(text)
    at_company = [r for r in roles if claim["company"] and same_company(claim["company"], r["company"])]
    if not at_company:
        listed = "; ".join(describe(r) for r in roles[:3]) or "no employment history"
        return "unverifiable", f"No role at {claim['company'] or 'that company'} on Crustdata. Crustdata shows: {listed}"
    results = [(_check(claim, r), r) for r in at_company]
    for (status, _), r in results:
        if status == "verified":
            return "verified", f"Crustdata shows: {describe(r)}"
    for (status, why), r in results:
        if status == "contradicted":
            return "contradicted", f"Crustdata shows: {describe(r)} ({why})"
    return "unverifiable", f"Crustdata shows: {describe(results[0][1])} (title could not be matched)"


def verify(expert: dict) -> list[dict]:
    """Return a list of Claim dicts (see contract/CONTRACT.md):
    {text, status: verified|contradicted|unverifiable, evidence, source: "crustdata:person_enrich", fetched_at}"""
    texts = expert.get("claims") or ([expert["headline"]] if expert.get("headline") else [])
    try:
        raw, fetched_at = fetch(expert)
        roles = roles_from(raw)
        if raw is None:
            reason = "No usable LinkedIn URL or API key, so Crustdata was not called"
            return [{"text": t, "status": "unverifiable", "evidence": reason, "source": SOURCE,
                     "fetched_at": fetched_at} for t in texts]
    except Exception as e:  # noqa: BLE001  never break the pipeline
        return [{"text": t, "status": "unverifiable", "evidence": f"Crustdata lookup failed: {type(e).__name__}",
                 "source": SOURCE, "fetched_at": _now()} for t in texts]
    src = raw[0].get("_source", SOURCE) if raw else SOURCE
    out = []
    for t in texts:
        status, evidence = verify_claim(t, roles)
        out.append({"text": t, "status": status, "evidence": evidence, "source": src, "fetched_at": fetched_at})
    return out + _identity_claim(expert)


def _identity_claim(expert: dict) -> list[dict]:
    """Set by backend/integrations/onboarding.py: LinkedIn login + Telegram deep link + Crustdata name match."""
    idn = expert.get("identity") or {}
    if idn.get("status") != "verified":
        return []
    return [{"text": "Identity: this Telegram account belongs to the LinkedIn profile owner",
             "status": "verified",
             "evidence": f"Signed in with LinkedIn as {idn.get('linkedin_name')}, linked Telegram via one-time link; "
                         f"Crustdata profile name: {idn.get('crustdata_name')}",
             "source": "linkedin:oidc+telegram", "fetched_at": idn.get("verified_at") or _now()}]


if __name__ == "__main__":
    # python -m backend.integrations.crustdata   -> verifies the whole pool (cache first)
    from .pool import load_experts
    for e in load_experts():
        for c in verify(e):
            print(f"{e['expert_id']:>4} {c['status']:<13} {c['text']}  |  {c['evidence']}")
