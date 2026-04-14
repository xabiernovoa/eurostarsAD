"""
live.py — Orquestador multi-agente concurrente del modo autónomo.

Diseñado para la pestaña "Modo autónomo" del dashboard de marketing:
emite eventos NDJSON mientras el sistema:

1. Consulta al Oráculo (una vez por sesión, en el hilo principal).
2. Selecciona candidatos con ``user_scheduler.find_candidates`` (ibíd.).
3. Lanza N **workers concurrentes** de recomendación que compiten por los
   candidatos desde una cola compartida. Cada worker genera su propia
   recomendación llamando a ``campaign_generator.generate_campaign``.
   La concurrencia es realista: en producción varios usuarios comparten
   ``preferred_month`` + lead time parecido y por tanto su ``ideal_send_date``
   cae a la misma franja; el sistema debe poder generar sus recomendaciones
   en paralelo.
4. Lanza 1 worker de propuestas que genera ``campaigns_per_tick`` campañas
   estilo Generador (vía ``chat_engine.generate_single_campaign_proposal``)
   de forma concurrente con los workers de recomendación.

El generador principal drena un ``queue.Queue`` compartido al que todos los
workers empujan eventos; los eventos se ceden como NDJSON al cliente HTTP.
Si el cliente cierra la conexión, el ``GeneratorExit`` se propaga, el
``stop_event`` se activa, y los workers terminan tras su paso actual
(los workers no pueden interrumpir llamadas HTTP a Gemini en vuelo).

Nota: dos pestañas de navegador que streamean a la vez obtienen cada una
su propio pool de hilos (via ``ThreadingMixIn`` del servidor). Eso implica
que ``data/runtime/autonomous_state.json`` se escribe con semántica
*last-writer-wins*.
Aceptable para la demo.

Eventos emitidos (``type``):
    start               — metadatos iniciales y configuración
    oracle_start        — comienza el refresco del Oráculo
    oracle_entry        — cada entrada del Oráculo
    oracle_done         — resumen del Oráculo (count, blocked, trending)
    candidates_start    — se abre la búsqueda de candidatos
    candidate           — un candidato válido detectado
    candidates_done     — fin de la fase de selección
    feed_start          — arranca el feed concurrente
    worker_state        — un worker cambia de estado (idle/busy/done)
    campaign_start      — un worker arranca una recomendación
    campaign_done       — recomendación completa (incluye matched_events)
    campaign_skipped    — usuario omitido (destino bloqueado o sin datos)
    proposal_start      — el worker de propuestas arranca una propuesta
    proposal_done       — propuesta estilo Generador completada
    error               — fallo en un worker (no mata el tick)
    feed_done           — todos los workers han terminado
    tick_done           — resumen final
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from typing import Any, Iterator

from backend import config
from backend.ai import gemini as gemini_client
from backend.autonomous import oracle
from backend.autonomous import generator as campaign_generator
from backend.autonomous import scheduler as user_scheduler
from backend.storage import autonomous_state as state_module

logger = logging.getLogger("autonomous.live")


# Sentinel pushed by each worker as its last action so the drain loop knows
# to decrement its expected-workers counter. Using sentinels (not Thread.is_alive)
# is critical: a worker can push its final event *and then* exit; is_alive()
# would read False while that event is still in the queue, causing early exit.
_WORKER_DONE = object()


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _warm_caches(force_mock: bool) -> None:
    """
    Precalienta los singletons compartidos (cliente Gemini + cache del
    dashboard del chat) desde el hilo principal para evitar carreras
    benignas pero lentas en la primera llamada concurrente.
    """
    if not force_mock:
        try:
            gemini_client.call_gemini("ok", json_output=False)
        except Exception:
            pass
    try:
        from backend.marketing import chat

        chat._get_dashboard()
    except Exception:
        pass


def _interruptible_sleep(seconds: float, stop_event: threading.Event) -> None:
    remaining = seconds
    while remaining > 0 and not stop_event.is_set():
        step = min(0.2, remaining)
        time.sleep(step)
        remaining -= step


def _recommender_worker(
    *,
    worker_id: int,
    candidate_q: "queue.Queue[Any]",
    event_q: "queue.Queue[Any]",
    oracle_ctx: list[dict[str, Any]],
    st: dict[str, Any],
    worker_lock: threading.Lock,
    stop_event: threading.Event,
    force_mock: bool,
    timing_mode: str | None,
    send_offset_days: int | None,
    per_worker_delay: float,
    initial_stagger: float,
    mock_work_seconds: float,
) -> None:
    """
    Worker de recomendación: extrae candidatos de ``candidate_q`` hasta
    agotarla o recibir señal de parada, y emite eventos a ``event_q``.
    """
    try:
        if initial_stagger > 0:
            _interruptible_sleep(initial_stagger, stop_event)

        event_q.put({
            "type": "worker_state",
            "worker_id": worker_id,
            "kind": "recommender",
            "state": "idle",
        })

        while not stop_event.is_set():
            try:
                cand = candidate_q.get_nowait()
            except queue.Empty:
                break
            if cand is None:  # centinela de cola vacía
                candidate_q.task_done()
                break

            guest_id = cand["guest_id"]
            event_q.put({
                "type": "worker_state",
                "worker_id": worker_id,
                "kind": "recommender",
                "state": "busy",
                "guest_id": guest_id,
            })
            event_q.put({
                "type": "campaign_start",
                "worker_id": worker_id,
                "guest_id": guest_id,
                "preferred_month": cand.get("preferred_month"),
                "ideal_send_date": cand.get("ideal_send_date"),
            })

            # En modo mock, la llamada a Gemini no existe y la generación
            # tarda ~ms. Para que la demo *muestre* la concurrencia entre
            # agentes, simulamos el tiempo de "thinking" que tendría una
            # llamada real (5-10s en Vertex). En modo real este sleep es 0
            # porque ``campaign_generator.generate_campaign`` ya bloquea.
            if mock_work_seconds > 0:
                _interruptible_sleep(mock_work_seconds, stop_event)
                if stop_event.is_set():
                    candidate_q.task_done()
                    break

            try:
                result = campaign_generator.generate_campaign(
                    guest_id,
                    oracle_context=oracle_ctx,
                    force_mock=force_mock,
                    timing_mode=timing_mode,
                    send_offset_days=send_offset_days,
                )
            except Exception as exc:  # pragma: no cover — defensivo
                logger.exception("Worker %d falló en campaña %s", worker_id, guest_id)
                event_q.put({
                    "type": "error",
                    "stage": "recommender_worker",
                    "worker_id": worker_id,
                    "guest_id": guest_id,
                    "message": str(exc),
                })
                candidate_q.task_done()
                continue

            if result is None:
                event_q.put({
                    "type": "campaign_skipped",
                    "worker_id": worker_id,
                    "guest_id": guest_id,
                    "reason": "Destino bloqueado o sin datos",
                })
                candidate_q.task_done()
                continue

            with worker_lock:
                state_module.mark_contacted(st, guest_id, now=datetime.now())

            event_q.put({
                "type": "campaign_done",
                "worker_id": worker_id,
                "guest_id": guest_id,
                "segment": result["segment"],
                "hotel": result["hotel"],
                "channel": result["channel"],
                "copy": result["copy"],
                "copy_source": result["copy_source"],
                "matched_events": result.get("matched_events", []),
                "travel_prediction": result.get("travel_prediction", {}),
                "html_path": result.get("html_path"),
            })
            candidate_q.task_done()

            # Throttle entre iteraciones: sensible a stop_event.
            _interruptible_sleep(per_worker_delay, stop_event)

    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Worker %d murió inesperadamente", worker_id)
        try:
            event_q.put({
                "type": "error",
                "stage": "recommender_worker",
                "worker_id": worker_id,
                "message": str(exc),
            })
        except Exception:
            pass
    finally:
        try:
            event_q.put({
                "type": "worker_state",
                "worker_id": worker_id,
                "kind": "recommender",
                "state": "done",
            })
        except Exception:
            pass
        event_q.put(_WORKER_DONE)


def _proposals_worker(
    *,
    event_q: "queue.Queue[Any]",
    stop_event: threading.Event,
    campaigns_per_tick: int,
    force_mock: bool,
    interval_seconds: float,
) -> None:
    """
    Worker de propuestas estilo Generador: genera exactamente
    ``campaigns_per_tick`` propuestas de campaña de forma secuencial
    pero concurrentemente con los workers de recomendación.
    """
    try:
        event_q.put({
            "type": "worker_state",
            "worker_id": 0,
            "kind": "proposals",
            "state": "idle",
        })

        previous_names: list[str] = []
        for idx in range(campaigns_per_tick):
            if stop_event.is_set():
                break

            event_q.put({
                "type": "worker_state",
                "worker_id": 0,
                "kind": "proposals",
                "state": "busy",
                "index": idx + 1,
            })
            event_q.put({
                "type": "proposal_start",
                "worker_id": 0,
                "index": idx + 1,
                "total": campaigns_per_tick,
            })

            try:
                from backend.marketing import chat

                proposal = chat.generate_single_campaign_proposal(
                    idx,
                    previous_names,
                    force_mock=force_mock,
                )
            except Exception as exc:  # pragma: no cover — defensivo
                logger.exception("Proposals worker falló en propuesta %d", idx + 1)
                event_q.put({
                    "type": "error",
                    "stage": "proposals_worker",
                    "worker_id": 0,
                    "index": idx + 1,
                    "message": str(exc),
                })
                proposal = None

            if isinstance(proposal, dict) and proposal.get("name"):
                previous_names.append(proposal["name"])
                event_q.put({
                    "type": "proposal_done",
                    "worker_id": 0,
                    "index": idx + 1,
                    "total": campaigns_per_tick,
                    "proposal": proposal,
                })
            else:
                event_q.put({
                    "type": "error",
                    "stage": "proposals_worker",
                    "worker_id": 0,
                    "index": idx + 1,
                    "message": "Propuesta vacía o inválida",
                })

            if idx < campaigns_per_tick - 1:
                _interruptible_sleep(interval_seconds, stop_event)

    except Exception as exc:  # pragma: no cover — defensivo
        logger.exception("Proposals worker murió inesperadamente")
        try:
            event_q.put({
                "type": "error",
                "stage": "proposals_worker",
                "worker_id": 0,
                "message": str(exc),
            })
        except Exception:
            pass
    finally:
        try:
            event_q.put({
                "type": "worker_state",
                "worker_id": 0,
                "kind": "proposals",
                "state": "done",
            })
        except Exception:
            pass
        event_q.put(_WORKER_DONE)


def iter_tick(
    *,
    force_mock: bool = False,
    reset_state: bool = True,
    delay_between_seconds: float = 10.0,
    max_recommendations: int = 20,
    window_days: int = 400,
    cooldown_days: int = 0,
    pacing_seconds: float = 0.05,
    recommender_workers: int = 3,
    campaigns_per_tick: int = 5,
    timing_mode: str | None = None,
    send_offset_days: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Ejecuta un feed autónomo concurrente y emite eventos NDJSON.

    * ``recommender_workers``: número de agentes concurrentes que generan
      recomendaciones individuales (clamped 1..6 por el servidor).
    * ``campaigns_per_tick``: número total de propuestas estilo Generador
      que emite el worker de propuestas durante la sesión. Si es 0 el
      worker de propuestas no se crea.
    * ``delay_between_seconds``: throttle total "conceptual"; cada worker
      duerme ``delay_between_seconds / recommender_workers`` entre
      iteraciones, manteniendo el throughput agregado constante cuando se
      cambia ``recommender_workers``.
    * ``max_recommendations``: cap de seguridad sobre el total de
      candidatos procesados en la sesión.
    """
    config.ensure_output_dirs()

    recommender_workers = max(1, int(recommender_workers))
    campaigns_per_tick = max(0, int(campaigns_per_tick))

    started_at = datetime.now()
    yield {
        "type": "start",
        "ts": started_at.isoformat(timespec="seconds"),
        "message": "Iniciando modo autónomo concurrente…",
        "config": {
            "force_mock": force_mock,
            "reset_state": reset_state,
            "delay_between_seconds": delay_between_seconds,
            "max_recommendations": max_recommendations,
            "window_days": window_days,
            "cooldown_days": cooldown_days,
            "recommender_workers": recommender_workers,
            "campaigns_per_tick": campaigns_per_tick,
            "travel_prediction_mode": timing_mode or "heuristic/env",
            "regression_send_offset_days": send_offset_days,
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
        st: dict[str, Any] = {
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

    # ── 1. Oracle (main thread) ──────────────────────────────────────
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

    # ── 2. Candidates (main thread) ──────────────────────────────────
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
            timing_mode=timing_mode,
            send_offset_days=send_offset_days,
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

    if not candidates and campaigns_per_tick == 0:
        yield {
            "type": "tick_done",
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": round((datetime.now() - started_at).total_seconds(), 2),
            "summary": {
                "oracle_entries": len(ctx),
                "candidates_found": 0,
                "recommendations_generated": 0,
                "recommendations_skipped": 0,
                "campaigns_generated": 0,
                "blocked_destinations": sorted(blocked),
            },
        }
        return

    # ── 3. Warm caches antes de spawnar workers ──────────────────────
    _warm_caches(force_mock)

    # ── 4. Feed concurrente ──────────────────────────────────────────
    active_recommender_workers = min(recommender_workers, max(1, len(candidates))) if candidates else 0

    yield {
        "type": "feed_start",
        "total_candidates": len(candidates),
        "max_recommendations": max_recommendations,
        "delay_between_seconds": delay_between_seconds,
        "recommender_workers": active_recommender_workers,
        "campaigns_per_tick": campaigns_per_tick,
    }
    _sleep(pacing_seconds)

    candidate_q: "queue.Queue[Any]" = queue.Queue()
    for cand in candidates[:max_recommendations]:
        candidate_q.put(cand)
    # Centinela por worker para que todos puedan salir limpiamente.
    for _ in range(active_recommender_workers):
        candidate_q.put(None)

    event_q: "queue.Queue[Any]" = queue.Queue()
    worker_lock = threading.Lock()
    stop_event = threading.Event()

    per_worker_delay = (
        delay_between_seconds / max(1, active_recommender_workers)
        if delay_between_seconds > 0
        else 0.0
    )
    proposals_interval = max(delay_between_seconds, 6.0) if campaigns_per_tick > 0 else 0.0
    # Sólo en modo mock simulamos tiempo de "pensar" para que la demo
    # demuestre visualmente la concurrencia; en modo Gemini real la
    # latencia del modelo (5-10s/llamada) ya produce el mismo efecto.
    mock_work_seconds = 2.2 if force_mock else 0.0

    workers: list[threading.Thread] = []
    for i in range(active_recommender_workers):
        t = threading.Thread(
            target=_recommender_worker,
            name=f"recommender-{i + 1}",
            kwargs=dict(
                worker_id=i + 1,
                candidate_q=candidate_q,
                event_q=event_q,
                oracle_ctx=ctx,
                st=st,
                worker_lock=worker_lock,
                stop_event=stop_event,
                force_mock=force_mock,
                timing_mode=timing_mode,
                send_offset_days=send_offset_days,
                per_worker_delay=per_worker_delay,
                initial_stagger=i * 0.4,
                mock_work_seconds=mock_work_seconds,
            ),
            daemon=True,
        )
        workers.append(t)

    if campaigns_per_tick > 0:
        workers.append(
            threading.Thread(
                target=_proposals_worker,
                name="proposals-1",
                kwargs=dict(
                    event_q=event_q,
                    stop_event=stop_event,
                    campaigns_per_tick=campaigns_per_tick,
                    force_mock=force_mock,
                    interval_seconds=proposals_interval,
                ),
                daemon=True,
            )
        )

    total_workers = len(workers)
    for t in workers:
        t.start()

    # ── 5. Drain loop + contadores ───────────────────────────────────
    recommendations_done = 0
    recommendations_skipped = 0
    proposals_done = 0
    markers_seen = 0

    try:
        while markers_seen < total_workers or not event_q.empty():
            try:
                ev = event_q.get(timeout=0.2)
            except queue.Empty:
                # Seguridad: si todos los hilos han muerto sin dejar centinela
                # (no debería ocurrir, pero defensivo), rompemos.
                if all(not t.is_alive() for t in workers) and event_q.empty():
                    break
                continue

            if ev is _WORKER_DONE:
                markers_seen += 1
                continue

            ev_type = ev.get("type")
            if ev_type == "campaign_done":
                recommendations_done += 1
            elif ev_type == "campaign_skipped":
                recommendations_skipped += 1
            elif ev_type == "proposal_done":
                proposals_done += 1

            yield ev
    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
        stop_event.set()
        raise
    finally:
        stop_event.set()
        for t in workers:
            t.join(timeout=2.0)

    _sleep(pacing_seconds)
    yield {
        "type": "feed_done",
        "recommendations_generated": recommendations_done,
        "recommendations_skipped": recommendations_skipped,
        "proposals_generated": proposals_done,
        "reason": (
            "cap_reached" if recommendations_done >= max_recommendations else "pool_exhausted"
        ),
    }
    _sleep(pacing_seconds)

    # ── 6. Persist + summary ─────────────────────────────────────────
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
            "recommendations_generated": recommendations_done,
            "recommendations_skipped": recommendations_skipped,
            "campaigns_generated": proposals_done,
            "blocked_destinations": sorted(blocked),
        },
    }
