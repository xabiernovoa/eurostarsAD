"""
run.py — Punto de entrada CLI del sistema autónomo.

Uso:
    python autonomous/run.py --mode tick        # un único ciclo
    python autonomous/run.py --mode loop        # bucle continuo
    python autonomous/run.py --mode demo        # demostración end-to-end
    python autonomous/run.py --dry-run          # sin envío real (por defecto)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Permite ejecutar el script directamente ``python autonomous/run.py``
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(PROJECT_ROOT / ".env")
except ModuleNotFoundError:
    pass

from autonomous import (  # noqa: E402
    campaign_generator,
    config,
    generic_campaigns,
    heartbeat,
    oracle,
    state as state_module,
    user_scheduler,
)


def _configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format=config.LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _print_summary(title: str, data: dict) -> None:
    print(f"\n── {title} ──")
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k2, v2 in value.items():
                print(f"    {k2}: {v2}")
        else:
            print(f"  {key}: {value}")


def _run_demo(force_mock: bool) -> int:
    """Genera 5 campañas personalizadas + 1 genérica y persiste todo en disco."""
    logger = logging.getLogger("autonomous.run.demo")
    config.ensure_output_dirs()

    # 1. Oráculo
    logger.info("Generando contexto del Oráculo…")
    ctx = oracle.refresh_oracle(limit=10)
    oracle.save_oracle_context(ctx)
    logger.info("Oráculo: %d entradas", len(ctx))

    # 2. Cargar / reiniciar estado
    state = state_module.load_state()
    state_module.record_oracle_refresh(state, ctx)

    # 3. Seleccionar 5 usuarios con amplia ventana
    candidates = user_scheduler.find_candidates(
        state,
        window_days=400,  # ventana ancha para demo
        cooldown_days=0,
        max_candidates=5,
        blocked_destinations=oracle.get_blocked_destinations(ctx),
    )
    if not candidates:
        logger.warning("No se encontraron candidatos — cargando top 5 por lead time")
        plans = user_scheduler.compute_user_plans()
        candidates = plans[:5]

    logger.info("Generando %d campañas personalizadas…", len(candidates))
    generated = []
    for cand in candidates[:5]:
        result = campaign_generator.generate_campaign(
            cand["guest_id"],
            oracle_context=ctx,
            force_mock=force_mock,
        )
        if result:
            generated.append(result)
            state_module.mark_contacted(state, cand["guest_id"])

    logger.info("Campañas personalizadas generadas: %d", len(generated))

    # 4. Campaña genérica
    logger.info("Generando campañas genéricas…")
    proposals = generic_campaigns.generate_generic_campaigns(
        oracle_context=ctx,
        max_campaigns=1,
        min_segment_size=1,
        force_mock=force_mock,
    )
    if proposals:
        state_module.record_generic_campaign(state)

    state_module.record_tick(state)
    state_module.save_state(state)

    # 5. Resumen en consola
    print("\n═══ RESUMEN DEMO SISTEMA AUTÓNOMO EUROSTARS ═══")
    print(f"  Entradas del Oráculo: {len(ctx)}")
    print(f"  Campañas personalizadas: {len(generated)}")
    for g in generated:
        seg = g["segment"]
        print(
            f"    • {g['guest_id']} [{seg.get('age_segment')}/{seg.get('travel_profile')}] "
            f"→ {g['hotel'].get('name')} ({g['hotel'].get('city')}) "
            f"[copy={g['copy_source']}]"
        )
    print(f"  Campañas genéricas: {len(proposals)}")
    for p in proposals:
        print(
            f"    • {p['campaign_name']} → {p['destination_city']} "
            f"[segmento={p['target_segment']}, fuente={p['source']}]"
        )
    print(f"\n  Salida guardada en: {config.OUTPUT_DIR}")
    print(f"  Estado actualizado: {config.STATE_FILE}")
    print("════════════════════════════════════════════════\n")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sistema autónomo de marketing por email de Eurostars."
    )
    parser.add_argument(
        "--mode",
        choices=["tick", "loop", "demo"],
        default="tick",
        help="Modo de ejecución: tick (un ciclo), loop (bucle continuo) o demo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="No envía emails reales (por defecto).",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Desactiva el modo dry-run.",
    )
    parser.add_argument(
        "--force-mock",
        action="store_true",
        help="Fuerza contenido mock sin llamar a Gemini aunque haya API key.",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="En modo loop, detiene tras N ticks.",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
        help="En modo loop, intervalo entre ticks.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Activa logs DEBUG.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    logger = logging.getLogger("autonomous.run")
    logger.info(
        "Modo: %s · dry_run=%s · force_mock=%s",
        args.mode,
        args.dry_run,
        args.force_mock,
    )

    if not args.dry_run:
        logger.warning("dry_run desactivado — el envío real no está implementado en este sistema")

    if args.mode == "demo":
        return _run_demo(force_mock=args.force_mock)

    if args.mode == "tick":
        summary = heartbeat.run_tick(force_mock=args.force_mock)
        _print_summary("Tick completado", summary)
        return 0

    if args.mode == "loop":
        heartbeat.run_loop(
            interval_minutes=args.interval_minutes,
            max_ticks=args.max_ticks,
            force_mock=args.force_mock,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
