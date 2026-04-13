from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.paths import MARKETING_CONTEXT_PATH


def load_marketing_context(default: dict[str, Any]) -> dict[str, Any]:
    if not MARKETING_CONTEXT_PATH.exists():
        save_marketing_context(default)
    with open(MARKETING_CONTEXT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return default | data


def save_marketing_context(context: dict[str, Any]) -> Path:
    MARKETING_CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MARKETING_CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    return MARKETING_CONTEXT_PATH
