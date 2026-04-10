#!/usr/bin/env python3
"""
send_campaign.py — Phase 8: Campaign Sending & Tracking

Sends emails via SendGrid (or saves to disk in --dry-run mode).
Tracks all sent campaigns in campaign_log.json with UTM parameters.
"""

import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("send_campaign")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _load_log() -> list[dict]:
    """Load existing campaign log."""
    log_path = os.path.join(DATA_DIR, "campaign_log.json")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_log(log: list[dict]) -> None:
    """Save campaign log."""
    log_path = os.path.join(DATA_DIR, "campaign_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _inject_utm(html: str, segment: dict, moment: str) -> str:
    """Ensure all links have UTM parameters."""
    # UTM params are already in templates via copy.cta_url_suffix
    # This adds utm_content with segment info to any remaining links
    utm_content = f"seg_{segment.get('age_segment', 'unknown')}_{segment.get('travel_profile', 'unknown')}"
    html = html.replace("utm_content=joven", f"utm_content={utm_content}")
    html = html.replace("utm_content=adulto", f"utm_content={utm_content}")
    html = html.replace("utm_content=senior", f"utm_content={utm_content}")
    return html


def send_email_sendgrid(
    to_email: str,
    subject: str,
    html_content: str,
) -> bool:
    """Send email via SendGrid API."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key or api_key.startswith("SG.xxxxx"):
        logger.warning("No valid SendGrid API key")
        return False

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        sender = os.environ.get("SENDER_EMAIL", "noreply@eurostarshotels.com")
        message = Mail(
            from_email=sender,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logger.info("SendGrid response: %d", response.status_code)
        return response.status_code in (200, 201, 202)

    except Exception as e:
        logger.error("SendGrid send failed: %s", e)
        return False


def send_campaign(
    campaign_data: dict,
    html: str,
    copy: dict,
    channel: dict,
    sms_text: str = "",
    dry_run: bool = True,
) -> dict:
    """Send or save a campaign and log the result."""
    guest_id = campaign_data.get("guest_id", "")
    moment = campaign_data.get("campaign_type", "unknown")
    segment = campaign_data.get("segment", {})

    # Inject UTM parameters
    html = _inject_utm(html, segment, moment)

    primary_channel = channel.get("primary_channel", "email")

    log_entry = {
        "guest_id": guest_id,
        "channel": primary_channel,
        "template": f"template_{segment.get('age_segment', 'adulto').lower()}.html",
        "campaign_type": moment,
        "hotel_recommended": "",
        "subject": copy.get("subject", ""),
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "dry_run": dry_run,
    }

    # Extract hotel info
    hotel = campaign_data.get("recommended_hotel", campaign_data.get("last_stay", {}))
    log_entry["hotel_recommended"] = hotel.get("name", hotel.get("hotel_name", ""))

    if dry_run:
        # Save HTML to disk
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename = f"{moment}_{guest_id}.html"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        log_entry["status"] = "saved_to_disk"
        log_entry["output_file"] = filename
        logger.info("Dry-run: saved %s to %s", filename, OUTPUT_DIR)

        # Also save SMS if applicable
        if sms_text and primary_channel == "sms":
            sms_path = os.path.join(OUTPUT_DIR, f"sms_{guest_id}.txt")
            with open(sms_path, "w", encoding="utf-8") as f:
                f.write(sms_text)
            log_entry["sms_file"] = f"sms_{guest_id}.txt"

    else:
        # Real send
        if primary_channel == "email":
            success = send_email_sendgrid(
                to_email=f"guest_{guest_id}@example.com",  # Placeholder
                subject=copy.get("subject", "Eurostars Hotels"),
                html_content=html,
            )
            log_entry["status"] = "sent" if success else "failed"
        elif primary_channel == "sms":
            # SMS would be sent via Twilio or similar — mock for now
            log_entry["status"] = "sms_mock_sent"
            log_entry["sms_text"] = sms_text[:160]
        else:
            # Push notification — mock
            log_entry["status"] = "push_mock_sent"

    # Append to campaign log
    log = _load_log()
    log.append(log_entry)
    _save_log(log)

    return log_entry


def send_batch(
    campaigns: list[dict],
    htmls: list[str],
    copies: list[dict],
    channels: list[dict],
    sms_texts: list[str],
    dry_run: bool = True,
) -> list[dict]:
    """Send a batch of campaigns."""
    results = []
    for i, (campaign, html, copy, channel) in enumerate(
        zip(campaigns, htmls, copies, channels)
    ):
        sms = sms_texts[i] if i < len(sms_texts) else ""
        result = send_campaign(campaign, html, copy, channel, sms, dry_run)
        results.append(result)

    # Summary
    statuses = {}
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
    logger.info("Batch complete — %d campaigns: %s", len(results), statuses)

    return results


def main():
    log = _load_log()
    logger.info("Campaign log has %d entries", len(log))
    if log:
        for entry in log[-5:]:
            logger.info("  %s — %s — %s — %s",
                        entry["guest_id"], entry["campaign_type"],
                        entry["channel"], entry["status"])


if __name__ == "__main__":
    main()
