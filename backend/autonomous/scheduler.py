"""
user_scheduler.py — Cálculo del momento óptimo para contactar a cada usuario.

La lógica es puramente temporal:

1. Se determina el mes/estación de viaje habitual del usuario.
2. Se resta su ``AVG_BOOKING_LEADTIME`` para obtener la ventana ideal de envío.
3. Si la fecha actual cae dentro de esa ventana (±SEND_WINDOW_DAYS), el usuario
   pasa a ser candidato.
4. Se filtran los usuarios contactados recientemente (cooldown).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from backend import config
from backend.storage import autonomous_state as state_module
from backend.storage.customers import load_customers_df

logger = logging.getLogger("autonomous.user_scheduler")


def _load_customers(path: Path | None = None) -> pd.DataFrame:
    return load_customers_df(path)


def _next_occurrence(month: int, today: date) -> date:
    """Próxima fecha (día 15) del mes indicado, a partir de hoy."""
    year = today.year if month > today.month or (month == today.month and today.day <= 15) else today.year + 1
    return date(year, month, 15)


def _ideal_send_date(preferred_month: int, avg_leadtime_days: float, today: date) -> date:
    target_checkin = _next_occurrence(preferred_month, today)
    return target_checkin - timedelta(days=max(7, int(round(avg_leadtime_days))))


def compute_user_plans(
    customers: pd.DataFrame | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Calcula, para cada usuario, su próxima ventana de contacto.

    Devuelve una lista de diccionarios con los campos:
    ``guest_id``, ``preferred_month``, ``avg_leadtime_days``,
    ``ideal_send_date``, ``target_checkin``.
    """
    df = customers if customers is not None else _load_customers()
    now = now or datetime.now()
    today = now.date()

    plans: list[dict[str, Any]] = []
    for guest_id, rows in df.groupby("GUEST_ID"):
        months = rows["CHECKIN_DATE"].dt.month.tolist()
        if not months:
            continue
        preferred_month = Counter(months).most_common(1)[0][0]
        avg_leadtime = float(rows["AVG_BOOKING_LEADTIME"].iloc[0] or 14)
        target_checkin = _next_occurrence(preferred_month, today)
        send_date = _ideal_send_date(preferred_month, avg_leadtime, today)

        plans.append(
            {
                "guest_id": str(guest_id),
                "preferred_month": int(preferred_month),
                "avg_leadtime_days": avg_leadtime,
                "ideal_send_date": send_date.isoformat(),
                "target_checkin": target_checkin.isoformat(),
            }
        )

    logger.info("Calculados planes para %d usuarios", len(plans))
    return plans


def find_candidates(
    state: dict[str, Any],
    customers: pd.DataFrame | None = None,
    now: datetime | None = None,
    window_days: int | None = None,
    cooldown_days: int | None = None,
    max_candidates: int | None = None,
    blocked_destinations: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Devuelve la lista de usuarios candidatos a recibir una campaña en este tick.

    Un usuario es candidato si:
      * hoy cae dentro de (ideal_send_date ± window_days),
      * no ha sido contactado en los últimos ``cooldown_days``,
      * su destino objetivo no está bloqueado por el Oráculo (si se indica).
    """
    window_days = window_days if window_days is not None else config.SEND_WINDOW_DAYS
    cooldown_days = cooldown_days if cooldown_days is not None else config.USER_COOLDOWN_DAYS
    max_candidates = max_candidates if max_candidates is not None else config.MAX_USERS_PER_TICK
    now = now or datetime.now()
    today = now.date()

    plans = compute_user_plans(customers=customers, now=now)
    candidates: list[dict[str, Any]] = []
    for plan in plans:
        send_date = date.fromisoformat(plan["ideal_send_date"])
        delta_days = abs((today - send_date).days)
        if delta_days > window_days:
            continue

        if state_module.was_contacted_recently(
            state, plan["guest_id"], cooldown_days=cooldown_days, now=now
        ):
            continue

        candidate = {
            **plan,
            "delta_days": delta_days,
            "is_due": send_date <= today,
        }
        candidates.append(candidate)

    # Ordenamos por cercanía a la fecha ideal (los más urgentes primero)
    candidates.sort(key=lambda c: c["delta_days"])
    if max_candidates and max_candidates > 0:
        candidates = candidates[:max_candidates]

    if blocked_destinations:
        logger.info(
            "Destinos bloqueados por el Oráculo: %s",
            ", ".join(sorted(blocked_destinations)),
        )

    logger.info("Encontrados %d candidatos en esta ventana", len(candidates))
    return candidates


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    st = state_module.load_state()
    cands = find_candidates(st)
    for c in cands[:5]:
        logger.info("Candidato: %s", c)


if __name__ == "__main__":  # pragma: no cover
    main()
