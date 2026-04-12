"""
state.py — Persistencia del estado del sistema autónomo.

El estado se guarda como JSON plano y contiene:
  - última fecha de refresco del Oráculo
  - mapa de usuarios contactados (guest_id → timestamp ISO)
  - contexto actual del Oráculo
  - contadores (campañas enviadas, ticks ejecutados, campañas genéricas)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from autonomous import config

logger = logging.getLogger("autonomous.state")


DEFAULT_STATE: dict[str, Any] = {
    "last_oracle_refresh": None,
    "last_generic_campaign": None,
    "user_last_contacted": {},
    "oracle_context": [],
    "campaigns_sent": 0,
    "generic_campaigns_sent": 0,
    "ticks_executed": 0,
    "blocked_destinations": [],
}


def _default_state() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_STATE))


def load_state(path: Path | None = None) -> dict[str, Any]:
    """Carga el estado desde disco. Si no existe, devuelve el estado por defecto."""
    path = Path(path or config.STATE_FILE)
    if not path.exists():
        logger.info("No existe state.json — inicializando estado por defecto")
        return _default_state()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("State file corrupto (%s) — reiniciando", exc)
        return _default_state()

    merged = _default_state()
    merged.update(data)
    return merged


def save_state(state: dict[str, Any], path: Path | None = None) -> Path:
    """Guarda el estado en disco de forma atómica."""
    path = Path(path or config.STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)
    logger.debug("Estado guardado en %s", path)
    return path


def was_contacted_recently(
    state: dict[str, Any],
    guest_id: str,
    cooldown_days: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Indica si el usuario fue contactado dentro del periodo de cooldown."""
    cooldown_days = cooldown_days if cooldown_days is not None else config.USER_COOLDOWN_DAYS
    ts = state.get("user_last_contacted", {}).get(str(guest_id))
    if not ts:
        return False

    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return False

    now = now or datetime.now()
    return (now - last) < timedelta(days=cooldown_days)


def mark_contacted(
    state: dict[str, Any],
    guest_id: str,
    now: datetime | None = None,
) -> None:
    """Registra que el usuario ha sido contactado en este momento."""
    now = now or datetime.now()
    state.setdefault("user_last_contacted", {})[str(guest_id)] = now.isoformat(timespec="seconds")
    state["campaigns_sent"] = state.get("campaigns_sent", 0) + 1


def should_refresh_oracle(
    state: dict[str, Any],
    interval_hours: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Devuelve True si toca refrescar el Oráculo."""
    interval_hours = interval_hours if interval_hours is not None else config.ORACLE_INTERVAL_HOURS
    ts = state.get("last_oracle_refresh")
    if not ts:
        return True

    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return True

    now = now or datetime.now()
    return (now - last) >= timedelta(hours=interval_hours)


def should_generate_generic(
    state: dict[str, Any],
    interval_hours: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Devuelve True si toca generar campañas genéricas."""
    interval_hours = (
        interval_hours if interval_hours is not None else config.GENERIC_CAMPAIGN_INTERVAL_HOURS
    )
    ts = state.get("last_generic_campaign")
    if not ts:
        return True

    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return True

    now = now or datetime.now()
    return (now - last) >= timedelta(hours=interval_hours)


def record_oracle_refresh(
    state: dict[str, Any],
    oracle_context: list[dict],
    now: datetime | None = None,
) -> None:
    """Registra los resultados del último refresco del Oráculo."""
    now = now or datetime.now()
    state["last_oracle_refresh"] = now.isoformat(timespec="seconds")
    state["oracle_context"] = oracle_context
    state["blocked_destinations"] = sorted(
        {
            entry.get("city", "").upper()
            for entry in oracle_context
            if entry.get("category") == "travel_alert"
            and not entry.get("actionable", True)
        }
    )


def record_generic_campaign(state: dict[str, Any], now: datetime | None = None) -> None:
    now = now or datetime.now()
    state["last_generic_campaign"] = now.isoformat(timespec="seconds")
    state["generic_campaigns_sent"] = state.get("generic_campaigns_sent", 0) + 1


def record_tick(state: dict[str, Any]) -> None:
    state["ticks_executed"] = state.get("ticks_executed", 0) + 1
