from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.paths import CAMPAIGN_LOG_PATH


def load_campaign_log(path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(path or CAMPAIGN_LOG_PATH)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_campaign_log(entries: list[dict[str, Any]], path: str | Path | None = None) -> Path:
    path = Path(path or CAMPAIGN_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return path
