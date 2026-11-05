"""Owner: Sunil. Builds data/experts.json from Crustdata Person Search, so nobody fills it by hand.

    python -m backend.integrations.seed_pool

- Keeps the teammate entries (simulated == false) exactly as they are.
- Real logistics/warehouse people in India -> claims taken from their REAL current role (should verify).
- Planted test cases (planted: true): claims deliberately inflated by the team so the verifier must catch them.
  The real person never made these claims. Never contact them: simulated == true, no chat id.
- Search results include employment history, so they are written to data/crustdata_cache/<id>.json
  (marked _source = crustdata:person_search). verify() then needs no extra enrich credits.
"""
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "data" / "experts.json"
CACHE = ROOT / "data" / "crustdata_cache"
load_dotenv(ROOT / ".env")

N_REAL = 12
FIELDS = ["crustdata_person_id", "basic_profile.name", "basic_profile.current_title",
          "social_handles.professional_network_identifier.profile_url",
          "experience.employment_details.current", "experience.employment_details.past"]
DAYS = ["2026-11-06", "2026-11-07", "2026-11-08"]
AVAIL = [{"start": f"{d}T17:00:00+05:30", "end": f"{d}T22:00:00+05:30"} for d in DAYS]


def search(title_keywords: list[str], limit: int) -> list[dict]:
    body = {"filters": {"op": "and", "conditions": [
                {"op": "or", "conditions": [{"field": "experience.employment_details.current.title",
                                             "type": "(.)", "value": k} for k in title_keywords]},
                {"field": "basic_profile.location.country", "type": "=", "value": "India"}]},
            "sorts": [{"field": "crustdata_person_id", "order": "asc"}],
            "limit": limit, "fields": FIELDS}
    r = httpx.post("https://api.crustdata.com/person/search", json=body, timeout=90,
                   headers={"authorization": f"Bearer {os.environ['CRUSTDATA_API_KEY'].strip()}",
                            "content-type": "application/json", "x-api-version": "2025-11-01"})
    print(f"search {title_keywords}: HTTP {r.status_code}, credits {r.headers.get('x-credits-used')}")
    r.raise_for_status()
    return r.json().get("profiles", [])


def _main_role(p: dict, keywords: list[str]) -> dict | None:
    cur = (p.get("experience", {}).get("employment_details", {}) or {}).get("current") or []
    for role in cur:
        t = (role.get("title") or "").lower()
        if role.get("start_date") and role.get("name") and any(k in t for k in keywords):
            return role
    return None


def _cache(eid: str, url: str, p: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = [{"matched_on": url, "match_type": "professional_network_profile_url", "match_status": "matched",
            "_source": "crustdata:person_search",
            "matches": [{"confidence_score": 1.0, "person_data": p}]}]
    (CACHE / f"{eid}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def _expert(eid: str, p: dict, claim: str, headline: str) -> dict:
    url = p["social_handles"]["professional_network_identifier"]["profile_url"]
    pid = int(p.get("crustdata_person_id") or 0)
    _cache(eid, url, p)
    return {"expert_id": eid, "name": p["basic_profile"]["name"], "headline": headline, "linkedin_url": url,
            "rate_inr": 1000 + (pid % 11) * 200, "availability": AVAIL,
            "telegram_chat_id": f"sim-{eid}", "email": "", "claims": [claim], "simulated": True}


def _planted(ex: dict, k: int) -> dict:
    """Planted test cases get an anonymised display name: the claim is ours, not the real person's."""
    ex.update(planted=True, name=f"Planted Test {chr(65 + k)}", availability=AVAIL,
              telegram_chat_id=f"sim-{ex['expert_id']}", simulated=True)
    return ex


def _url(p: dict) -> str | None:
    return (p.get("social_handles", {}).get("professional_network_identifier", {}) or {}).get("profile_url")


REAL_KW = ["warehouse", "logistics", "supply chain", "fulfilment", "fulfillment"]


def main():
    old = json.loads(POOL.read_text(encoding="utf-8")) if POOL.exists() else []
    team = [{**e, "availability": AVAIL} for e in old if not e.get("simulated")]
    kept_planted = [e for e in old if e.get("planted")]   # reuse: saves the intern-search credits
    seen = {e["linkedin_url"] for e in kept_planted}

    real = []
    for p in search(REAL_KW, 20):
        role = _main_role(p, ["warehouse", "logistic", "supply chain", "fulfil"])
        url = _url(p)
        if not role or not url or url in seen or "intern" in role["title"].lower():
            continue
        seen.add(url)
        real.append((p, role))
    need_inflate = not kept_planted and len(real) > N_REAL
    inflate = real.pop() if need_inflate else None
    real = real[:N_REAL]

    out = list(team)
    for i, (p, role) in enumerate(real):
        claim = f"{role['title']} at {role['name']}, {role['start_date'][:4]}-present"
        out.append(_expert(f"e{4 + i}", p, claim, f"{role['title']}, {role['name']}"))

    if kept_planted:
        out += [_planted(e, k) for k, e in enumerate(kept_planted)]
    else:
        n = 4 + len(real)
        fakes = []
        for p in search(["logistics intern", "warehouse intern", "supply chain intern", "operations intern"], 10):
            role, url = _main_role(p, ["intern"]), _url(p)
            if role and url and url not in seen and len(fakes) < 2:
                seen.add(url)
                y = int(role["start_date"][:4])
                fakes.append(_expert(f"e{n + len(fakes)}", p, f"Warehouse Head at {role['name']}, {y - 2}-present",
                                     f"Warehouse Head, {role['name']}"))
        if inflate:
            p, role = inflate
            y = int(role["start_date"][:4])
            fakes.append(_expert(f"e{n + len(fakes)}", p, f"{role['title']} at {role['name']}, {y - 6}-present",
                                 f"{role['title']}, {role['name']} (6+ yrs)"))
        out += [_planted(e, k) for k, e in enumerate(fakes)]

    ids = [e["expert_id"] for e in out]
    assert len(ids) == len(set(ids)), f"duplicate expert ids: {ids}"
    POOL.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} experts ({len(team)} team, {len(real)} real, "
          f"{sum(1 for e in out if e.get('planted'))} planted)")


if __name__ == "__main__":
    main()
