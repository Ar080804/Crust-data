"""Owner: Sunil. Loads the opted-in expert pool from data/experts.json."""
import json
import os
from pathlib import Path

from backend.app.config import CLOUD

POOL = Path(__file__).resolve().parents[2] / "data" / "experts.json"


def load_experts() -> list[dict]:
    """Format: contract/fixtures/pool_example.json. Checked by: python contract/check_integrations.py"""
    private_pool = os.getenv("EXPERT_POOL_JSON")
    if CLOUD and not private_pool:
        return []
    experts = json.loads(private_pool) if private_pool else json.loads(POOL.read_text(encoding="utf-8"))
    if not CLOUD:
        return experts
    return [e for e in experts if not e.get("simulated") and e.get("availability")
            and str(e.get("telegram_chat_id", "")).lstrip("-").isdigit()
            and "TODO" not in str(e.get("linkedin_url", "")).upper()]
