#!/usr/bin/env python3
"""
main.py — Orquestador del motor de personalización Eurostars AI

Ejecuta el pipeline completo o fases individuales:

    python main.py --phase all
    python main.py --phase segment
    python main.py --phase campaign --moment pre_arrival
    python main.py --phase campaign --moment checkin_report --guest_id 1014907189
    python main.py --phase campaign --moment post_stay
    python main.py --dry-run
"""

import argparse
import os
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import MARKETING_SNAPSHOT_PATH, OUTPUT_DIR
from backend.personalization.segment_views import get_segment_label
from backend.storage.campaign_log import save_campaign_log
from backend.storage.embeddings import load_embeddings
from backend.storage.segments import load_segments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")


def _reset_batch_artifacts() -> None:
    """Limpia los artefactos batch de demo y reinicia el log generado."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            continue
        if path.name.startswith(("pre_arrival_", "post_stay_", "checkin_report_", "sms_")):
            path.unlink(missing_ok=True)
    save_campaign_log([])
    logger.info("Se han reiniciado las salidas batch y el registro de campañas")


def _campaign_worker_count(total_campaigns: int) -> int:
    """Elige un número acotado de hilos para campañas mayoritariamente de E/S."""
    configurado = os.environ.get("CAMPAIGN_MAX_WORKERS")
    if configurado:
        try:
            return max(1, min(total_campaigns, int(configurado)))
        except ValueError:
            logger.warning(
                "CAMPAIGN_MAX_WORKERS=%s no es válido; se usará el valor por defecto.",
                configurado,
            )

    trabajadores_por_defecto = max(4, (os.cpu_count() or 2) * 2)
    return max(1, min(total_campaigns, trabajadores_por_defecto))


def phase_embeddings():
    """Fase 1: construir embeddings."""
    logger.info("=" * 60)
    logger.info("FASE 1 — Construyendo embeddings de hoteles y usuarios")
    logger.info("=" * 60)
    from backend.personalization import embeddings as build_embeddings
    data = build_embeddings.build()
    build_embeddings.save(data)
    return data


def phase_segment():
    """Fase 2: segmentar usuarios."""
    logger.info("=" * 60)
    logger.info("FASE 2 — Segmentando usuarios")
    logger.info("=" * 60)
    from backend.personalization import segmentation as segment_users
    segs = segment_users.segment()
    segment_users.save(segs)
    return segs


def phase_auto_tag():
    """Fase 4a: generar metadatos de imágenes."""
    logger.info("=" * 60)
    logger.info("FASE 4a — Generando metadatos de imágenes")
    logger.info("=" * 60)
    from backend.assets import image_metadata as auto_tag_images
    auto_tag_images.generate_metadata()


def phase_marketing():
    """Construye un snapshot del dashboard de marketing."""
    logger.info("=" * 60)
    logger.info("FASE 9 — Construyendo snapshot del dashboard de marketing")
    logger.info("=" * 60)
    from backend.marketing import dashboard as dashboard_engine

    carga = dashboard_engine.build_dashboard_data()
    ruta_snapshot = MARKETING_SNAPSHOT_PATH
    with open(ruta_snapshot, "w", encoding="utf-8") as f:
        json.dump(carga, f, ensure_ascii=False, indent=2)
    logger.info("Snapshot de marketing guardado en %s", ruta_snapshot)
    return carga


def phase_campaign(
    moment: str,
    guest_id: str | None = None,
    dry_run: bool = True,
    timing_mode: str | None = None,
    send_offset_days: int | None = None,
):
    """Fases 3-8: ejecuta el pipeline de campañas para un momento concreto."""
    logger.info("=" * 60)
    logger.info("FASES 3-8 — Pipeline de campañas: %s", moment)
    logger.info("=" * 60)

    from backend.assets import image_selector
    from backend.campaigns import channels as channel_selector
    from backend.campaigns import copy as text_generator
    from backend.campaigns import delivery as send_campaign
    from backend.campaigns import planner as campaign_engine
    from backend.campaigns import renderer as email_renderer

    # Cargar los datos base
    embeddings = load_embeddings()
    segments = load_segments()

    # Paso 3: generar datos de campaña
    logger.info("Paso 3: generando datos de campaña...")
    campaigns = campaign_engine.generate_all(
        moment,
        guest_id,
        timing_mode=timing_mode,
        send_offset_days=send_offset_days,
    )
    if not campaigns:
        logger.warning("No se han generado campañas para moment=%s guest_id=%s", moment, guest_id)
        return []

    logger.info("Se han generado %d campaña(s)", len(campaigns))

    def process_campaign(index: int, camp: dict) -> tuple[int, dict]:
        gid = camp.get("guest_id", "?")
        seg = camp.get("segment", {})

        try:
            if moment == "checkin_report":
                logger.info(
                    "[%d/%d] Renderizando informe de check-in para %s...",
                    index + 1,
                    len(campaigns),
                    gid,
                )
                html = email_renderer.render_email(camp, {}, [], moment)
                copy = {"subject": f"Informe de Recepción — Huésped #{gid}"}
                channel = {
                    "primary_channel": "internal_report",
                    "reason": "Informe interno",
                }
                sms_text = ""
            else:
                logger.info(
                    "[%d/%d] Procesando huésped %s (%s)...",
                    index + 1,
                    len(campaigns),
                    gid,
                    get_segment_label(seg),
                )
                hotel = camp.get("recommended_hotel", camp.get("last_stay", {}))
                hotel_id = hotel.get("id", hotel.get("hotel_id", ""))
                user_emb = embeddings["user_embeddings"].get(str(gid), {})

                images_data = image_selector.select_images(hotel_id, user_emb, seg)
                image_paths = [img["path"] for img in images_data]
                copy = text_generator.generate_copy(camp, moment, dry_run=dry_run)
                html = email_renderer.render_email(camp, copy, image_paths, moment)
                channel = channel_selector.select_channel(seg, camp)
                sms_text = ""
                if channel["primary_channel"] == "sms":
                    sms_text = text_generator.generate_sms(camp, dry_run=dry_run)

            result = send_campaign.send_campaign(
                camp, html, copy, channel, sms_text, dry_run=dry_run
            )
            return index, result
        except Exception as exc:
            logger.exception(
                "Ha fallado el procesamiento de la campaña para el huésped %s (%s): %s",
                gid,
                moment,
                exc,
            )
            return index, {
                "guest_id": gid,
                "campaign_type": moment,
                "status": "processing_failed",
                "dry_run": dry_run,
                "error": str(exc),
            }

    results = [None] * len(campaigns)
    max_workers = _campaign_worker_count(len(campaigns))
    logger.info(
        "Procesando %d campaña(s) con %d hilo(s) de trabajo",
        len(campaigns),
        max_workers,
    )

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix=f"campaign-{moment}",
    ) as executor:
        futures = [
            executor.submit(process_campaign, index, camp)
            for index, camp in enumerate(campaigns)
        ]
        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result

    # Resumen
    logger.info("-" * 60)
    logger.info("Resumen de campañas para '%s':", moment)
    statuses = {}
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
    logger.info("  Total: %d | Estados: %s", len(results), statuses)
    logger.info("-" * 60)

    return results


def run_all(
    dry_run: bool = True,
    timing_mode: str | None = None,
    send_offset_days: int | None = None,
):
    """Ejecuta el pipeline completo."""
    logger.info("*" * 60)
    logger.info("EUROSTARS AI PERSONALIZATION ENGINE — Pipeline completo")
    logger.info("*" * 60)

    _reset_batch_artifacts()

    # Fase 1
    phase_embeddings()

    # Fase 2
    phase_segment()

    # Fase 4a: autoetiquetado de imágenes
    phase_auto_tag()

    # Fases 3-8: ejecutar campañas
    for moment in ["pre_arrival", "checkin_report", "post_stay"]:
        phase_campaign(
            moment,
            guest_id=None,
            dry_run=dry_run,
            timing_mode=timing_mode,
            send_offset_days=send_offset_days,
        )

    # Fase 9
    phase_marketing()

    logger.info("*" * 60)
    logger.info("Pipeline completado")
    logger.info("*" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Motor de personalización Eurostars AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py --phase all
  python main.py --phase segment
  python main.py --phase campaign --moment pre_arrival
  python main.py --phase campaign --moment checkin_report --guest_id 1014907189
  python main.py --phase campaign --moment post_stay
  python main.py --phase marketing
  python main.py --dry-run
        """,
    )
    parser.add_argument(
        "--phase",
        choices=["all", "embeddings", "segment", "auto_tag", "campaign", "marketing"],
        default="all",
        help="Qué fase ejecutar (por defecto: all)",
    )
    parser.add_argument(
        "--moment",
        choices=["pre_arrival", "checkin_report", "post_stay"],
        default=None,
        help="Momento de campaña (obligatorio con --phase=campaign)",
    )
    parser.add_argument(
        "--guest_id",
        default=None,
        help="ID de huésped concreto a procesar (opcional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Guardar salidas en disco sin enviar emails reales (por defecto: True)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        default=False,
        help="Enviar realmente los emails vía SendGrid (requiere API key)",
    )
    args = parser.parse_args()
    dry_run = not args.send

    if args.phase == "all":
        run_all(dry_run=dry_run)
    elif args.phase == "embeddings":
        phase_embeddings()
    elif args.phase == "segment":
        phase_segment()
    elif args.phase == "auto_tag":
        phase_auto_tag()
    elif args.phase == "campaign":
        if not args.moment:
            parser.error("--moment es obligatorio cuando --phase=campaign")
        phase_campaign(
            args.moment,
            args.guest_id,
            dry_run=dry_run,
        )
    elif args.phase == "marketing":
        phase_marketing()


if __name__ == "__main__":
    main()
