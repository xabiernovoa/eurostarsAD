#!/usr/bin/env python3
"""
main.py — Eurostars AI Personalization Engine Orchestrator

Runs the complete pipeline or individual phases:

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
    logger.info("Reset batch outputs and campaign log")


def _campaign_worker_count(total_campaigns: int) -> int:
    """Choose a bounded thread count for mostly I/O-bound campaign work."""
    configured = os.environ.get("CAMPAIGN_MAX_WORKERS")
    if configured:
        try:
            return max(1, min(total_campaigns, int(configured)))
        except ValueError:
            logger.warning("Invalid CAMPAIGN_MAX_WORKERS=%s; using default.", configured)

    default_workers = max(4, (os.cpu_count() or 2) * 2)
    return max(1, min(total_campaigns, default_workers))


def phase_embeddings():
    """Phase 1: Build embeddings."""
    logger.info("=" * 60)
    logger.info("PHASE 1 — Building hotel & user embeddings")
    logger.info("=" * 60)
    from backend.personalization import embeddings as build_embeddings
    data = build_embeddings.build()
    build_embeddings.save(data)
    return data


def phase_segment():
    """Phase 2: Segment users."""
    logger.info("=" * 60)
    logger.info("PHASE 2 — Segmenting users")
    logger.info("=" * 60)
    from backend.personalization import segmentation as segment_users
    segs = segment_users.segment()
    segment_users.save(segs)
    return segs


def phase_auto_tag():
    """Phase 4a: Generate image metadata."""
    logger.info("=" * 60)
    logger.info("PHASE 4a — Generating image metadata")
    logger.info("=" * 60)
    from backend.assets import image_metadata as auto_tag_images
    auto_tag_images.generate_metadata()


def phase_marketing():
    """Build a marketing dashboard snapshot."""
    logger.info("=" * 60)
    logger.info("PHASE 9 — Building marketing dashboard snapshot")
    logger.info("=" * 60)
    from backend.marketing import dashboard as dashboard_engine

    payload = dashboard_engine.build_dashboard_data()
    snapshot_path = MARKETING_SNAPSHOT_PATH
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Saved marketing dashboard snapshot to %s", snapshot_path)
    return payload


def phase_campaign(moment: str, guest_id: str | None = None, dry_run: bool = True):
    """Phase 3-8: Run campaign pipeline for a specific moment."""
    logger.info("=" * 60)
    logger.info("PHASE 3-8 — Campaign pipeline: %s", moment)
    logger.info("=" * 60)

    from backend.assets import image_selector
    from backend.campaigns import channels as channel_selector
    from backend.campaigns import copy as text_generator
    from backend.campaigns import delivery as send_campaign
    from backend.campaigns import planner as campaign_engine
    from backend.campaigns import renderer as email_renderer

    # Load base data
    embeddings = load_embeddings()
    segments = load_segments()

    # Step 3: Generate campaign data
    logger.info("Step 3: Generating campaign data...")
    campaigns = campaign_engine.generate_all(moment, guest_id)
    if not campaigns:
        logger.warning("No campaigns generated for moment=%s guest_id=%s", moment, guest_id)
        return []

    logger.info("Generated %d campaign(s)", len(campaigns))

    def process_campaign(index: int, camp: dict) -> tuple[int, dict]:
        gid = camp.get("guest_id", "?")
        seg = camp.get("segment", {})

        try:
            if moment == "checkin_report":
                logger.info(
                    "[%d/%d] Rendering checkin report for %s...",
                    index + 1,
                    len(campaigns),
                    gid,
                )
                html = email_renderer.render_email(camp, {}, [], moment)
                copy = {"subject": f"Informe de Recepción — Guest #{gid}"}
                channel = {
                    "primary_channel": "internal_report",
                    "reason": "Informe interno",
                }
                sms_text = ""
            else:
                logger.info(
                    "[%d/%d] Processing guest %s (%s)...",
                    index + 1,
                    len(campaigns),
                    gid,
                    seg.get("age_segment", "?"),
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
                "Campaign processing failed for guest %s (%s): %s",
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
    logger.info("Processing %d campaign(s) with %d worker thread(s)", len(campaigns), max_workers)

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

    # Summary
    logger.info("-" * 60)
    logger.info("Campaign summary for '%s':", moment)
    statuses = {}
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
    logger.info("  Total: %d | Statuses: %s", len(results), statuses)
    logger.info("-" * 60)

    return results


def run_all(dry_run: bool = True):
    """Run the complete pipeline."""
    logger.info("*" * 60)
    logger.info("EUROSTARS AI PERSONALIZATION ENGINE — Full pipeline")
    logger.info("*" * 60)

    _reset_batch_artifacts()

    # Phase 1
    phase_embeddings()

    # Phase 2
    phase_segment()

    # Phase 4a: Auto-tag images
    phase_auto_tag()

    # Phase 3-8: Run campaigns
    for moment in ["pre_arrival", "checkin_report", "post_stay"]:
        phase_campaign(moment, guest_id=None, dry_run=dry_run)

    # Phase 9
    phase_marketing()

    logger.info("*" * 60)
    logger.info("Pipeline complete!")
    logger.info("*" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Eurostars AI Personalization Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
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
        help="Which phase to run (default: all)",
    )
    parser.add_argument(
        "--moment",
        choices=["pre_arrival", "checkin_report", "post_stay"],
        default=None,
        help="Campaign moment (required when --phase=campaign)",
    )
    parser.add_argument(
        "--guest_id",
        default=None,
        help="Specific guest ID to process (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Save outputs to disk without sending real emails (default: True)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        default=False,
        help="Actually send emails via SendGrid (requires API key)",
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
            parser.error("--moment is required when --phase=campaign")
        phase_campaign(args.moment, args.guest_id, dry_run=dry_run)
    elif args.phase == "marketing":
        phase_marketing()


if __name__ == "__main__":
    main()
