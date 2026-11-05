"""Owner: Sunil. Uses getUpdates long-polling, so no public URL is needed.
Only ONE process may poll a given bot token at a time (otherwise Telegram returns 409 Conflict)."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

IST = timezone(timedelta(hours=5, minutes=30))


def _api(method: str, **params) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty in .env")
    poll = int(params.get("timeout", 0))
    r = httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=poll + 10)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {data.get('error_code')} {data.get('description')}")
    return data["result"]


def send_message(chat_id: str, text: str) -> str:
    """Send a message and return the Telegram message_id as a str."""
    result = _api("sendMessage", chat_id=str(chat_id), text=text)
    return str(result["message_id"])


def get_replies(since_update_id: int, timeout: int = 1) -> list[dict]:
    """Return [{update_id, chat_id, text, t}] for updates newer than since_update_id.
    Note: passing offset confirms (deletes on Telegram's side) all updates <= since_update_id."""
    updates = _api("getUpdates", offset=since_update_id + 1, timeout=timeout,
                   allowed_updates=["message"])
    replies = []
    for u in updates:
        msg = u.get("message") or {}
        text = msg.get("text")
        if not text:
            continue
        replies.append({
            "update_id": u["update_id"],
            "chat_id": str(msg["chat"]["id"]),
            "text": text,
            "t": datetime.fromtimestamp(msg["date"], IST).isoformat(timespec="seconds"),
        })
    return replies


if __name__ == "__main__":
    # Quick manual test:  python -m backend.integrations.telegram
    for r in get_replies(0):
        print(r)
