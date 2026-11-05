"""Owner: Sunil. Loads the opted-in expert pool from data/experts.json."""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parents[2] / "data" / "experts.json"


def load_experts() -> list[dict]:
    """Format: contract/fixtures/pool_example.json. Checked by: python contract/check_integrations.py"""
    return json.loads(POOL.read_text())
