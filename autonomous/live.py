"""
live.py — Generador instrumentado del feed autónomo continuo.

Diseñado para la pestaña "Modo autónomo" del dashboard de marketing:
emite eventos NDJSON mientras el sistema:

1. Consulta al Oráculo (una vez por sesión).
2. Recorre una lista de candidatos y, para cada uno, genera una
   recomendación personalizada con Gemini inyectando en el prompt los
   eventos del Oráculo que mejor casan con el perfil de viaje del usuario
   (ver ``campaign_generator.match_oracle_events``).
3. Entre recomendaciones introduce una pausa artificial de unos segundos
   (``delay_between_seconds``) para dar ritmo visual a la demo y evitar
   saturar cuotas del modelo.

El cliente (frontend) detiene la generación cerrando la conexión HTTP;
el servidor captura el ``BrokenPipeError`` y aborta el generador.

Eventos emitidos (``type``):
    start                   — metadatos iniciales y configuración
    oracle_start            — comienza el refresco del Oráculo
    oracle_entry            — cada entrada del Oráculo
    oracle_done             — resumen del Oráculo (count, blocked, trending)
    candidates_start        — se abre la búsqueda de candidatos
    candidate               — un candidato válido detectado
    candidates_done         — fin de la fase de selección
    feed_start              — arranca el feed continuo
    campaign_start          — comienza la generación para un guest
    campaign_done           — recomendación completa (incluye matched_events)
    campaign_skipped        — usuario omitido (destino bloqueado o sin datos)
    pause                   — espera artificial entre recomendaciones
    generic_campaign_start  — comienza una campaña genérica intercalada
    generic_campaign_done   — campaña genérica completada
    feed_done               — ya no hay más candidatos (cap o cola agotada)
    tick_done               — resumen final
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Iterator

from autonomous import (
    campaign_generator,
    config,
    gemini_client,
    oracle,
    state as state_module,
    user_scheduler,
)

logger = logging.getLogger("autonomous.live")


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def iter_tick(
    *,
    force_mock: bool = False,
    reset_state: bool = True,
    delay_between_seconds: float = 5.0,
    max_recommendations: int = 20,
    window_days: int = 400,
    cooldown_days: int = 0,
    pacing_seconds: float = 0.05,
    generic_every_n: int = 5,
) -> Iterator[dict[str, Any]]:
    """
    Ejecuta un feed autónomo continuo y emite eventos NDJSON.

    * ``delay_between_seconds``: pausa artificial entre recomendaciones
      (visible en el frontend como cuenta atrás).
    * ``max_recommendations``: cap de seguridad para evitar drenar la
      cuota del modelo en demos largas.
    * ``generic_every_n``: cada N recomendaciones individuales generadas,
      intercala una campaña genérica. Pon ``0`` para desactivar.
    """
    config.ensure_output_dirs()

    started_at = datetime.now()
    yield {
        "type": "start",
        "ts": started_at.isoformat(timespec="seconds"),
        "message": "Iniciando modo autónomo continuo…",
        "config": {
            "force_mock": force_mock,
            "reset_state": reset_state,
            "delay_between_seconds": delay_between_seconds,
            "max_recommendations": max_recommendations,
            "window_days": window_days,
            "cooldown_days": cooldown_days,
            "generic_every_n": generic_every_n,
            "gemini_available": gemini_client.is_available() and not force_mock,
            "model": (
                config.GEMINI_MODEL
                if gemini_client.is_available() and not force_mock
                else "mock"
            ),
        },
    }
    _sleep(pacing_seconds)

    # ── State ────────────────────────────────────────────────────────
    if reset_state:
        st = {
            "last_oracle_refresh": None,
            "last_generic_campaign": None,
            "user_last_contacted": {},
            "oracle_context": [],
            "campaigns_sent": 0,
            "generic_campaigns_sent": 0,
            "ticks_executed": 0,
            "blocked_destinations": [],
        }
    else:
        st = state_module.load_state()

    # ── 1. Oracle ────────────────────────────────────────────────────
    yield {"type": "oracle_start", "message": "Consultando al Oráculo…"}
    _sleep(pacing_seconds)
    try:
        ctx = oracle.refresh_oracle(limit=10, use_gemini=not force_mock)
        oracle.save_oracle_context(ctx)
    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Fallo al refrescar el Oráculo")
        yield {"type": "error", "stage": "oracle", "message": str(exc)}
        return

    for entry in ctx:
        yield {"type": "oracle_entry", "entry": entry}
        _sleep(pacing_seconds)

    state_module.record_oracle_refresh(st, ctx, now=datetime.now())
    blocked = oracle.get_blocked_destinations(ctx)
    yield {
        "type": "oracle_done",
        "count": len(ctx),
        "blocked": sorted(blocked),
        "trending": [
            {"city": c, "score": s}
            for c, s in oracle.get_trending_destinations(ctx, limit=5)
        ],
    }
    _sleep(pacing_seconds)

    # ── 2. Candidates ────────────────────────────────────────────────
    yield {
        "type": "candidates_start",
        "message": f"Seleccionando candidatos (cap {max_recommendations})…",
    }
    _sleep(pacing_seconds)

    try:
        candidates = user_scheduler.find_candidates(
            st,
            window_days=window_days,
            cooldown_days=cooldown_days,
            max_candidates=max_recommendations,
            blocked_destinations=blocked,
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Fallo en scheduler")
        yield {"type": "error", "stage": "scheduler", "message": str(exc)}
        return

    for cand in candidates:
        yield {"type": "candidate", "candidate": cand}
        _sleep(pacing_seconds)

    yield {"type": "candidates_done", "count": len(candidates)}
    _sleep(pacing_seconds)

    if not candidates:
        yield {
            "type": "tick_done",
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": round((datetime.now() - started_at).total_seconds(), 2),
            "summary": {
                "oracle_entries": len(ctx),
                "candidates_found": 0,
                "recommendations_generated": 0,
                "blocked_destinations": sorted(blocked),
            },
        }
        return

    # ── 3. Feed continuo plano ───────────────────────────────────────
    yield {
        "type": "feed_start",
        "total_candidates": len(candidates),
        "max_recommendations": max_recommendations,
        "delay_between_seconds": delay_between_seconds,
    }
    _sleep(pacing_seconds)

    generated: list[dict[str, Any]] = []
    generic_generated: list[dict[str, Any]] = []
    skipped = 0

    for idx, cand in enumerate(candidates):
        if len(generated) >= max_recommendations:
            break

        guest_id = cand["guest_id"]
        yield {
            "type": "campaign_start",
            "index": idx + 1,
            "guest_id": guest_id,
            "preferred_month": cand.get("preferred_month"),
            "ideal_send_date": cand.get("ideal_send_date"),
        }

        try:
            result = campaign_generator.generate_campaign(
                guest_id,
                oracle_context=ctx,
                force_mock=force_mock,
            )
        except Exception as exc:  # pragma: no cover — defensivo
            logger.exception("Error generando campaña %s", guest_id)
            yield {
                "type": "error",
                "stage": "campaign",
                "guest_id": guest_id,
                "message": str(exc),
            }
            skipped += 1
            continue

        if result is None:
            skipped += 1
            yield {
                "type": "campaign_skipped",
                "guest_id": guest_id,
                "reason": "Destino bloqueado o sin datos",
            }
            _sleep(pacing_seconds)
            continue

        state_module.mark_contacted(st, guest_id, now=datetime.now())
        payload = {
            "type": "campaign_done",
            "index": idx + 1,
            "guest_id": guest_id,
            "segment": result["segment"],
            "hotel": result["hotel"],
            "channel": result["channel"],
            "copy": result["copy"],
            "copy_source": result["copy_source"],
            "matched_events": result.get("matched_events", []),
            "html_path": result.get("html_path"),
        }
        generated.append(payload)
        yield payload

        # Intercalado: cada N recomendaciones, generar una genérica.
        if (
            generic_every_n
            and generic_every_n > 0
            and len(generated) % generic_every_n == 0
        ):
            yield {
                "type": "generic_campaign_start",
                "message": "Generando campaña genérica para un segmento amplio…",
                "after_individual": len(generated),
            }
            _sleep(pacing_seconds)
            try:
                from autonomous import generic_campaigns

                proposals = generic_campaigns.generate_generic_campaigns(
                    oracle_context=ctx,
                    force_mock=force_mock,
                    max_campaigns=1,
                    save_report=False,
                )
            except Exception as exc:  # pragma: no cover — defensivo
                logger.exception("Error generando campaña genérica")
                yield {
                    "type": "error",
                    "stage": "generic",
                    "message": str(exc),
                }
                proposals = []

            for prop in proposals or []:
                generic_generated.append(prop)
                state_module.record_generic_campaign(st, now=datetime.now())
                yield {
                    "type": "generic_campaign_done",
                    "index": len(generic_generated),
                    "campaign": prop,
                }
                _sleep(pacing_seconds)

        # Pausa artificial antes de la siguiente recomendación.
        remaining = min(len(candidates) - idx - 1, max_recommendations - len(generated))
        if remaining > 0 and delay_between_seconds > 0:
            yield {
                "type": "pause",
                "delay_seconds": delay_between_seconds,
                "remaining_candidates": remaining,
            }
            _sleep(delay_between_seconds)

    yield {
        "type": "feed_done",
        "total_recommendations": len(generated),
        "reason": "max_reached" if len(generated) >= max_recommendations else "pool_exhausted",
    }
    _sleep(pacing_seconds)

    # ── 4. Persist + summary ─────────────────────────────────────────
    state_module.record_tick(st)
    state_module.save_state(st)

    finished_at = datetime.now()
    yield {
        "type": "tick_done",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
        "summary": {
            "oracle_entries": len(ctx),
            "candidates_found": len(candidates),
            "recommendations_generated": len(generated),
            "recommendations_skipped": skipped,
            "generic_campaigns_generated": len(generic_generated),
            "blocked_destinations": sorted(blocked),
        },
    }
