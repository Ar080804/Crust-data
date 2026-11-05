"""Owner: Aditya. All settings come from .env at the repo root."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")
DB_PATH = str(ROOT / os.getenv("DB_PATH", "sutradhar.db"))
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
OUTREACH_TIMEOUT_S = int(os.getenv("OUTREACH_TIMEOUT_S", "90"))
WORKER_TICK_S = float(os.getenv("WORKER_TICK_S", "1"))
# Who receives the calendar invite on the client side (the requester).
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL", "")

IST = timezone(timedelta(hours=5, minutes=30))


def now() -> datetime:
    return datetime.now(IST)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")
