from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.paths import EVENTS_PATH


def load_events(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    path = Path(path or EVENTS_PATH)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}
