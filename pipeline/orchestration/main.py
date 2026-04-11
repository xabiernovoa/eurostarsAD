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
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.paths import DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")


def phase_embeddings():
    """Phase 1: Build embeddings."""
    logger.info("=" * 60)
    logger.info("PHASE 1 — Building hotel & user embeddings")
    logger.info("=" * 60)
    from pipeline.embeddings import build_embeddings
    data = build_embeddings.build()
    build_embeddings.save(data)
    return data


def phase_segment():
    """Phase 2: Segment users."""
    logger.info("=" * 60)
    logger.info("PHASE 2 — Segmenting users")
    logger.info("=" * 60)
    from pipeline.segmentation import segment_users
    segs = segment_users.segment()
    segment_users.save(segs)
    return segs


def phase_auto_tag():
    """Phase 4a: Generate image metadata."""
    logger.info("=" * 60)
    logger.info("PHASE 4a — Generating image metadata")
    logger.info("=" * 60)
    from pipeline.assets import auto_tag_images
    auto_tag_images.generate_metadata()


def phase_campaign(moment: str, guest_id: str | None = None, dry_run: bool = True):
    """Phase 3-8: Run campaign pipeline for a specific moment."""
    logger.info("=" * 60)
    logger.info("PHASE 3-8 — Campaign pipeline: %s", moment)
    logger.info("=" * 60)

    from pipeline.campaigns import campaign_engine
    from pipeline.content import text_generator
    from pipeline.assets import image_selector
    from pipeline.rendering import email_renderer
    from pipeline.channels import channel_selector
    from pipeline.delivery import send_campaign

    # Load base data
    emb_path = DATA_DIR / "embeddings.json"
    seg_path = DATA_DIR / "segments.json"

    with open(emb_path) as f:
        embeddings = json.load(f)
    with open(seg_path) as f:
        segments = json.load(f)

    # Step 3: Generate campaign data
    logger.info("Step 3: Generating campaign data...")
    campaigns = campaign_engine.generate_all(moment, guest_id)
    if not campaigns:
        logger.warning("No campaigns generated for moment=%s guest_id=%s", moment, guest_id)
        return []

    logger.info("Generated %d campaign(s)", len(campaigns))

    results = []
    for i, camp in enumerate(campaigns):
        gid = camp.get("guest_id", "?")
        seg = camp.get("segment", {})

        if moment == "checkin_report":
            # Step 6: Render receptionist report (no text gen / images needed)
            logger.info("[%d/%d] Rendering checkin report for %s...",
                        i + 1, len(campaigns), gid)
            html = email_renderer.render_email(camp, {}, [], moment)
            copy = {"subject": f"Informe de Recepción — Guest #{gid}"}
            channel = {"primary_channel": "internal_report", "reason": "Informe interno"}
            sms_text = ""
        else:
            # Step 4: Select images
            logger.info("[%d/%d] Processing guest %s (%s)...",
                        i + 1, len(campaigns), gid, seg.get("age_segment", "?"))
            hotel = camp.get("recommended_hotel", camp.get("last_stay", {}))
            hotel_id = hotel.get("id", hotel.get("hotel_id", ""))
            user_emb = embeddings["user_embeddings"].get(str(gid), {})

            images_data = image_selector.select_images(hotel_id, user_emb, seg)
            image_paths = [img["path"] for img in images_data]

            # Step 5: Generate text
            copy = text_generator.generate_copy(camp, moment, dry_run=dry_run)

            # Step 6: Render email
            html = email_renderer.render_email(camp, copy, image_paths, moment)

            # Step 7: Select channel
            channel = channel_selector.select_channel(seg, camp)

            # Generate SMS if needed
            sms_text = ""
            if channel["primary_channel"] == "sms":
                sms_text = text_generator.generate_sms(camp, dry_run=dry_run)

        # Step 8: Send or save
        result = send_campaign.send_campaign(
            camp, html, copy, channel, sms_text, dry_run=dry_run
        )
        results.append(result)

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

    # Phase 1
    phase_embeddings()

    # Phase 2
    phase_segment()

    # Phase 4a: Auto-tag images
    phase_auto_tag()

    # Phase 3-8: Run campaigns
    for moment in ["pre_arrival", "checkin_report", "post_stay"]:
        phase_campaign(moment, guest_id=None, dry_run=dry_run)

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
  python main.py --dry-run
        """,
    )
    parser.add_argument(
        "--phase",
        choices=["all", "embeddings", "segment", "auto_tag", "campaign"],
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


if __name__ == "__main__":
    main()
