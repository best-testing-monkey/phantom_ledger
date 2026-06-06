import json
from pathlib import Path

from phantom.errors import ProfileError
from phantom.models.broker import BrokerProfile


def load_profile(path: str | Path) -> BrokerProfile:
    path = Path(path)
    if not path.exists():
        raise ProfileError(f"Profile file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProfileError(f"Invalid JSON in {path}: {e}") from e
    profile_section = raw.get("profile", {})
    flat = {
        **profile_section,
        "commission": raw.get("commission", {}),
        "spread": raw.get("spread", {}),
        "slippage": raw.get("slippage", {}),
        "overnight": raw.get("overnight", {}),
        "margin": raw.get("margin", {}),
        "dividend": raw.get("dividend", {}),
        "trading_hours": raw.get("trading_hours", {}),
    }
    try:
        return BrokerProfile(**flat)
    except Exception as e:
        raise ProfileError(f"Validation failed for {path}: {e}") from e
