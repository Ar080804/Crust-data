"""Owner: Aditya. The ONLY place backend/app calls Sunil's integrations.
While a function of Sunil's raises NotImplementedError (or a file is missing), a labeled simulator is used instead.
When Sunil pushes his code, the real version takes over automatically with no change here."""
import os
import time
from datetime import timedelta

from . import db
from .config import CLOUD, now, now_iso

try:
    from backend.integrations import crustdata as _crust
except Exception:  # noqa: BLE001
    _crust = None
try:
    from backend.integrations import telegram as _tg
except Exception:  # noqa: BLE001
    _tg = None
try:
    from backend.integrations import pool as _pool
except Exception:  # noqa: BLE001
    _pool = None

MODE = {"pool": "?", "verify": "?", "telegram": "?"}


def _dev_pool():
    d = (now() + timedelta(days=1)).date().isoformat()
    avail = [{"start": f"{d}T17:00:00+05:30", "end": f"{d}T22:00:00+05:30"}]
    base = [
        ("e1", "Rohan Mehta", "Fulfilment Head, Delhivery", 2500, ["Fulfilment Head at Delhivery, 2020-present"], "verified"),
        ("e3", "Sunil Kumar", "Logistics Manager, Blinkit", 1800, ["Logistics Manager at Blinkit, 2021-2024"], "verified"),
        ("e7", "Priya Nair", "Ops Lead, regional 3PL", 1500, ["Ops Lead at ShipFast Logistics, 2019-2023"], "unverifiable"),
        ("e9", "Karan Shah", "Warehouse Manager, Flipkart", 1200, ["Warehouse Manager at Flipkart, 2022-2024"], "contradicted"),
    ]
    return [{"expert_id": i, "name": n, "headline": h, "linkedin_url": f"https://www.linkedin.com/in/dev-{i}",
             "rate_inr": r, "availability": avail, "telegram_chat_id": f"sim-{i}", "email": "",
             "claims": c, "simulated": True, "_sim_verify": v} for i, n, h, r, c, v in base]


def load_experts() -> list[dict]:
    if _pool:
        try:
            ex = _pool.load_experts()
            MODE["pool"] = "real"
            return ex
        except (FileNotFoundError, NotImplementedError):
            pass
    if CLOUD:
        raise RuntimeError("The expert pool is unavailable")
    MODE["pool"] = "sim"
    return _dev_pool()


def verify(expert: dict) -> tuple[list[dict], str]:
    if _crust:
        try:
            claims = _crust.verify(expert)
            MODE["verify"] = "real"
            return claims, (claims[0]["source"] if claims else "crustdata")
        except NotImplementedError:
            pass
    MODE["verify"] = "sim"
    status = expert.get("_sim_verify", "unverifiable")
    ev = {"verified": "Simulated: matching role and dates found",
          "contradicted": "Simulated: Crustdata shows only an internship at this company",
          "unverifiable": "Simulated: no matching employment record"}[status]
    return [{"text": c, "status": status, "evidence": ev, "source": "simulator:person_enrich",
             "fetched_at": now_iso()} for c in expert.get("claims", [])], "simulator"


# ---- messaging -------------------------------------------------------------

def send_once(key: str, chat_id: str, text: str) -> bool:
    """Idempotent send: the outbox row is written first, so a crash never causes a double message.
    Returns False if this key was already sent."""
    inserted = db.ex("INSERT INTO outbox (key, chat_id, text, status, t) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(key) DO NOTHING", (key, chat_id, text, "pending", now_iso()))
    if not inserted:
        return False
    if _tg and os.getenv("TELEGRAM_BOT_TOKEN") and not str(chat_id).startswith("sim-"):
        for attempt in range(3):
            try:
                _tg.send_message(str(chat_id), text)
                MODE["telegram"] = "real"
                db.ex("UPDATE outbox SET status='sent' WHERE key=?", (key,))
                return True
            except NotImplementedError:
                break
            except Exception as e:  # noqa: BLE001  network / Telegram error: retry, then give up
                print(f"Telegram send failed ({attempt + 1}/3): {type(e).__name__}")
                time.sleep(1 + attempt)
        else:
            db.ex("UPDATE outbox SET status='failed' WHERE key=?", (key,))
            return False
    MODE["telegram"] = "sim"
    db.ex("UPDATE outbox SET status='simulated' WHERE key=?", (key,))
    print(f"[SIM TELEGRAM → {chat_id}] {text}")
    return True


def poll_replies() -> list[dict]:
    """Return new replies [{update_id, chat_id, text, t}] and remember the offset in the DB."""
    if not _tg or not os.getenv("TELEGRAM_BOT_TOKEN"):
        return []
    since = int(db.kv_get("tg_last_update_id", "0"))
    try:
        replies = _tg.get_replies(since)
    except NotImplementedError:
        return []
    except Exception as e:  # noqa: BLE001  Telegram down / 409 conflict must not stop the pipeline
        print("Telegram poll failed:", type(e).__name__)
        return []
    return replies


def sim_reply(chat_id: str, text: str) -> dict:
    """Dev only: pretend an expert replied (used by POST /dev/reply and by the eval)."""
    uid = int(db.kv_get("sim_update_id", str(10**12))) + 1
    db.kv_set("sim_update_id", uid)
    return {"update_id": uid, "chat_id": str(chat_id), "text": text, "t": now_iso()}
