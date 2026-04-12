"""
heartbeat.py — Bucle principal del sistema autónomo.

Cada "tick" ejecuta estas comprobaciones en orden:

1. ¿Toca refrescar el Oráculo?  → ``oracle.refresh_oracle``
2. ¿Hay usuarios candidatos para contactar?  → ``user_scheduler.find_candidates``
3. Para cada candidato, ``campaign_generator.generate_campaign``.
4. ¿Toca generar campañas genéricas?  → ``generic_campaigns.generate_generic_campaigns``
5. Actualizar ``state.json`` y registrar el resumen del tick.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from autonomous import (
    campaign_generator,
    config,
    generic_campaigns,
    oracle,
    state as state_module,
    user_scheduler,
)

logger = logging.getLogger("autonomous.heartbeat")


def run_tick(
    *,
    force_oracle_refresh: bool = False,
    force_generic: bool = False,
    max_candidates: int | None = None,
    force_mock: bool = False,
) -> dict[str, Any]:
    """Ejecuta un único tick del sistema y devuelve un resumen."""
    config.ensure_output_dirs()
    now = datetime.now()
    state = state_module.load_state()

    summary: dict[str, Any] = {
        "started_at": now.isoformat(timespec="seconds"),
        "oracle_refreshed": False,
        "oracle_entries": 0,
        "candidates_found": 0,
        "campaigns_generated": 0,
        "campaigns_skipped": 0,
        "generic_generated": 0,
        "errors": [],
    }

    # ── 1. Oráculo ────────────────────────────────────────────────────
    if force_oracle_refresh or state_module.should_refresh_oracle(state, now=now):
        try:
            ctx = oracle.refresh_oracle()
            oracle.save_oracle_context(ctx)
            state_module.record_oracle_refresh(state, ctx, now=now)
            summary["oracle_refreshed"] = True
            summary["oracle_entries"] = len(ctx)
        except Exception as exc:  # pragma: no cover — defensivo
            logger.exception("Fallo al refrescar el Oráculo")
            summary["errors"].append(f"oracle: {exc}")
    oracle_context = state.get("oracle_context", [])

    # ── 2. Candidatos ─────────────────────────────────────────────────
    blocked = set(state.get("blocked_destinations", []))
    try:
        candidates = user_scheduler.find_candidates(
            state,
            now=now,
            max_candidates=max_candidates,
            blocked_destinations=blocked,
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Fallo al calcular candidatos")
        summary["errors"].append(f"scheduler: {exc}")
        candidates = []

    summary["candidates_found"] = len(candidates)

    # ── 3. Generación de campañas personalizadas ─────────────────────
    generated_campaigns: list[dict[str, Any]] = []
    for candidate in candidates:
        guest_id = candidate["guest_id"]
        try:
            result = campaign_generator.generate_campaign(
                guest_id,
                oracle_context=oracle_context,
                force_mock=force_mock,
            )
        except Exception as exc:  # pragma: no cover — defensivo
            logger.exception("Error generando campaña para %s", guest_id)
            summary["errors"].append(f"campaign[{guest_id}]: {exc}")
            continue

        if result is None:
            summary["campaigns_skipped"] += 1
            continue

        generated_campaigns.append(result)
        state_module.mark_contacted(state, guest_id, now=now)
        summary["campaigns_generated"] += 1
        logger.info(
            "Campaña generada para %s → %s (copy=%s)",
            guest_id,
            result["hotel"].get("name", "?"),
            result.get("copy_source", "?"),
        )

    # ── 4. Campañas genéricas ─────────────────────────────────────────
    if force_generic or state_module.should_generate_generic(state, now=now):
        try:
            proposals = generic_campaigns.generate_generic_campaigns(
                oracle_context=oracle_context,
                force_mock=force_mock,
            )
        except Exception as exc:  # pragma: no cover — defensivo
            logger.exception("Fallo al generar campañas genéricas")
            summary["errors"].append(f"generic: {exc}")
            proposals = []

        if proposals:
            state_module.record_generic_campaign(state, now=now)
            summary["generic_generated"] = len(proposals)

    # ── 5. Persistencia y cierre ──────────────────────────────────────
    state_module.record_tick(state)
    state_module.save_state(state)
    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["state_totals"] = {
        "campaigns_sent": state.get("campaigns_sent", 0),
        "generic_campaigns_sent": state.get("generic_campaigns_sent", 0),
        "ticks_executed": state.get("ticks_executed", 0),
    }

    logger.info(
        "Tick terminado — candidatos=%d, generadas=%d, genéricas=%d",
        summary["candidates_found"],
        summary["campaigns_generated"],
        summary["generic_generated"],
    )
    return summary


def run_loop(
    interval_minutes: int | None = None,
    max_ticks: int | None = None,
    force_mock: bool = False,
) -> None:
    """Ejecuta ticks en bucle con pausa ``interval_minutes`` entre iteraciones."""
    import time

    interval_minutes = interval_minutes if interval_minutes is not None else config.HEARTBEAT_INTERVAL_MINUTES
    tick_count = 0
    logger.info(
        "Iniciando bucle de heartbeat — intervalo=%s min, max_ticks=%s",
        interval_minutes,
        max_ticks,
    )

    try:
        while True:
            run_tick(force_mock=force_mock)
            tick_count += 1
            if max_ticks and tick_count >= max_ticks:
                logger.info("Alcanzado max_ticks=%d — deteniendo", max_ticks)
                break
            time.sleep(max(0, interval_minutes) * 60)
    except KeyboardInterrupt:  # pragma: no cover — ejecución manual
        logger.info("Interrumpido por el usuario — fin del bucle")
