from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.paths import EMBEDDINGS_PATH


def load_embeddings(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path or EMBEDDINGS_PATH)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_embeddings(data: dict[str, Any], path: str | Path | None = None) -> Path:
    path = Path(path or EMBEDDINGS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
