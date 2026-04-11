#!/usr/bin/env python3
"""
channel_selector.py — Phase 7: Communication Channel Selection

Selects the optimal communication channel (email / SMS / push)
based on user profile and booking behavior.
"""

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
logger = logging.getLogger("channel_selector")


def select_channel(segment: dict, campaign_data: dict) -> dict:
    """
    Select communication channel based on user segment.

    Returns:
        {
            "primary_channel": "email" | "sms" | "push",
            "secondary_channel": "email" | "sms" | "push" | None,
            "reason": str,
        }
    """
    age_segment = segment.get("age_segment", "ADULTO")
    avg_leadtime = campaign_data.get("avg_booking_leadtime",
                                     segment.get("avg_booking_leadtime", 15))

    # Extract leadtime from customer data if nested in campaign
    if "profile_summary" in campaign_data:
        # checkin_report type
        avg_leadtime = 15  # default for checkin reports always email

    # Rule 1: SENIOR → always email, never SMS
    if age_segment == "SENIOR":
        return {
            "primary_channel": "email",
            "secondary_channel": None,
            "reason": "Segmento SENIOR: se prioriza email siempre para máxima claridad y comodidad.",
        }

    # Rule 2: Very short lead time → SMS (fast decision maker)
    if avg_leadtime < 7:
        secondary = "email"
        return {
            "primary_channel": "sms",
            "secondary_channel": secondary,
            "reason": f"Lead time corto ({avg_leadtime:.0f} días): SMS para decisión rápida, email como respaldo.",
        }

    # Rule 3: JOVEN with engagement → push notification
    if age_segment == "JOVEN":
        return {
            "primary_channel": "push",
            "secondary_channel": "email",
            "reason": "Segmento JOVEN con posible uso de app: push notification + email de respaldo.",
        }

    # Rule 4: Long lead time → email (has time to read)
    if avg_leadtime > 30:
        return {
            "primary_channel": "email",
            "secondary_channel": None,
            "reason": f"Lead time largo ({avg_leadtime:.0f} días): email para comunicación detallada.",
        }

    # Default: email
    return {
        "primary_channel": "email",
        "secondary_channel": None,
        "reason": "Canal por defecto: email.",
    }


def select_channels_batch(campaigns: list[dict]) -> list[dict]:
    """Select channels for a batch of campaign data."""
    results = []
    for campaign in campaigns:
        seg = campaign.get("segment", {})
        channel = select_channel(seg, campaign)
        results.append({
            "guest_id": campaign.get("guest_id", ""),
            "campaign_type": campaign.get("campaign_type", ""),
            **channel,
        })
    return results


def main():
    seg_path = DATA_DIR / "segments.json"
    with open(seg_path) as f:
        segments = json.load(f)

    # Show channel distribution
    from collections import Counter
    channels = Counter()
    for uid, seg in segments.items():
        ch = select_channel(seg, {"avg_booking_leadtime": 15})
        channels[ch["primary_channel"]] += 1

    logger.info("Channel distribution: %s", dict(channels))


if __name__ == "__main__":
    main()
