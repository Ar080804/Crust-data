"""Owner: Sunil. Loads the opted-in expert pool from data/experts.json."""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parents[2] / "data" / "experts.json"


def load_experts() -> list[dict]:
    """Each expert: {expert_id, name, headline, linkedin_url, rate_inr, availability, telegram_chat_id, simulated}"""
    return json.loads(POOL.read_text())
