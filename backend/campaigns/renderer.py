#!/usr/bin/env python3
"""
email_renderer.py — Phase 6: Email Rendering with Jinja2

Renders personalized HTML emails using segment-specific templates:
  - template_joven.html for JOVEN segment
  - template_adulto.html for ADULTO segment
  - template_senior.html for SENIOR segment
  - receptionist_report.html for check-in reports
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import EMBEDDINGS_PATH, OUTPUT_DIR, SEGMENTS_PATH, TEMPLATES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("email_renderer")

# Template mapping by age segment
TEMPLATE_MAP = {
    "JOVEN": "template_joven.html",
    "ADULTO": "template_adulto.html",
    "SENIOR": "template_senior.html",
}


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )


def render_email(
    campaign_data: dict,
    copy: dict,
    images: list[str],
    moment: str = "pre_arrival",
) -> str:
    """Render an email HTML from campaign data and generated copy."""
    env = _get_env()
    seg = campaign_data.get("segment", {})
    age_segment = seg.get("age_segment", "ADULTO")

    if moment == "checkin_report":
        template_name = "receptionist_report.html"
    else:
        template_name = TEMPLATE_MAP.get(age_segment, "template_adulto.html")

    template = env.get_template(template_name)

    # Build context
    if moment == "checkin_report":
        context = {
            "profile": campaign_data.get("profile_summary", {}),
            "segment": seg,
            "preferences": campaign_data.get("preferences", []),
            "upsell_recommendations": campaign_data.get("upsell_recommendations", []),
            "visit_history": campaign_data.get("visit_history", []),
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        context["profile"]["guest_id"] = campaign_data.get("guest_id", "")
    else:
        # Pre-arrival or post-stay
        if moment == "post_stay":
            # For post_stay, use last_stay for display but recommended_hotel for next destination
            display_hotel = campaign_data.get("last_stay", {})
            next_hotel = campaign_data.get("recommended_hotel", {})
            hotel_name = display_hotel.get("hotel_name", display_hotel.get("name", ""))
            city_name = next_hotel.get("CITY_NAME", next_hotel.get("city", display_hotel.get("city", "")))
            country = next_hotel.get("COUNTRY_ID", next_hotel.get("country", ""))
            stars = next_hotel.get("STARS", next_hotel.get("stars", 4))
        else:
            hotel = campaign_data.get("recommended_hotel", {})
            hotel_name = hotel.get("name", hotel.get("HOTEL_NAME", ""))
            city_name = hotel.get("city", hotel.get("CITY_NAME", ""))
            country = hotel.get("country", hotel.get("COUNTRY_ID", ""))
            stars = hotel.get("stars", hotel.get("STARS", 4))

        context = {
            "user_name": None,  # No real names in data → "Estimado viajero"
            "hotel_name": hotel_name,
            "city_name": city_name,
            "country": country,
            "stars": stars,
            "travel_profile": seg.get("travel_profile", ""),
            "checkin_suggested": campaign_data.get("checkin_suggested", ""),
            "stay_nights": campaign_data.get("stay_nights", 0),
            "season": campaign_data.get("season", ""),
            "images": images,
            "copy": copy,
            "preferences": campaign_data.get("preferences", []),
            "unsubscribe_url": "https://www.eurostarshotels.com/unsubscribe",
            "tracking_pixel": f"https://track.eurostars.com/pixel/{campaign_data.get('guest_id', '')}",
        }

    html = template.render(**context)
    if not html.strip():
        raise ValueError(
            f"Rendered template {template_name} for guest {campaign_data.get('guest_id', '?')} is empty"
        )
    logger.info("Rendered %s template for guest %s (%s)",
                template_name, campaign_data.get("guest_id", "?"), moment)
    return html


def save_email(html: str, guest_id: str, moment: str) -> str:
    """Save rendered email to output directory."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"{moment}_{guest_id}.html"
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Saved email to %s", path)
    return path


def main():
    """Test rendering with sample data."""
    import json

    with open(EMBEDDINGS_PATH) as f:
        embeddings = json.load(f)
    with open(SEGMENTS_PATH) as f:
        segments = json.load(f)

    from backend.campaigns import copy as text_generator
    from backend.campaigns import planner as campaign_engine

    # Test all three templates with different users
    test_cases = [
        ("1018922044", "pre_arrival"),   # JOVEN
        ("1014907189", "pre_arrival"),   # ADULTO
        ("1018449824", "pre_arrival"),   # SENIOR
        ("1014907189", "checkin_report"),
    ]

    for guest_id, moment in test_cases:
        results = campaign_engine.generate_all(moment, guest_id)
        if not results:
            continue

        data = results[0]

        if moment == "checkin_report":
            html = render_email(data, {}, [], moment)
        else:
            copy = text_generator.generate_copy(data, moment, dry_run=True)
            html = render_email(data, copy, [], moment)

        save_email(html, guest_id, moment)


if __name__ == "__main__":
    main()
