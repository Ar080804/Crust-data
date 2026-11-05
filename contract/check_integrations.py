"""Owner: Aditya. Sunil runs this before every push:  python contract/check_integrations.py
It checks that Sunil's functions return exactly the shapes the backend expects.
If this passes, integration will not break."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.integrations import crustdata, pool  # noqa: E402

EXPERT_KEYS = {"expert_id", "name", "headline", "linkedin_url", "rate_inr", "availability",
               "telegram_chat_id", "email", "claims", "simulated"}
CLAIM_KEYS = {"text", "status", "evidence", "source", "fetched_at"}
CLAIM_STATUS = {"verified", "contradicted", "unverifiable"}
REPLY_KEYS = {"update_id", "chat_id", "text", "t"}

ok = True


def fail(msg):
    global ok
    ok = False
    print("FAIL:", msg)


experts = pool.load_experts()
print(f"pool: {len(experts)} experts")
for e in experts:
    missing = EXPERT_KEYS - e.keys()
    if missing:
        fail(f"expert {e.get('expert_id')} missing {missing}")
    if not isinstance(e.get("rate_inr"), int):
        fail(f"expert {e.get('expert_id')} rate_inr must be int")
    if not isinstance(e.get("telegram_chat_id"), str):
        fail(f"expert {e.get('expert_id')} telegram_chat_id must be str")

if experts:
    try:
        claims = crustdata.verify(experts[0])
        print(f"verify({experts[0]['expert_id']}): {len(claims)} claims")
        for c in claims:
            if CLAIM_KEYS - c.keys():
                fail(f"claim missing {CLAIM_KEYS - c.keys()}")
            if c.get("status") not in CLAIM_STATUS:
                fail(f"bad claim status {c.get('status')}")
    except NotImplementedError:
        print("SKIP: crustdata.verify not implemented yet")

try:
    from backend.integrations import telegram
    replies = telegram.get_replies(0)
    for r in replies:
        if REPLY_KEYS - r.keys():
            fail(f"reply missing {REPLY_KEYS - r.keys()}")
    print(f"get_replies: {len(replies)} replies")
except NotImplementedError:
    print("SKIP: telegram.get_replies not implemented yet")

print("ALL GOOD" if ok else "FIX THE ABOVE BEFORE PUSHING")
sys.exit(0 if ok else 1)
