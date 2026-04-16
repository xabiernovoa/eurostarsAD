#!/usr/bin/env python3
"""
email_renderer.py — Fase 6: renderizado de emails con Jinja2

Renderiza emails HTML personalizados con plantillas específicas por segmento:
  - template_joven.html para el segmento JOVEN
  - template_adulto.html para el segmento ADULTO
  - template_senior.html para el segmento SENIOR
  - receptionist_report.html para informes de check-in
"""

import logging
import sys
from hashlib import md5
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import EMBEDDINGS_PATH, OUTPUT_DIR, SEGMENTS_PATH, TEMPLATES_DIR
from backend.personalization.segment_views import (
    get_age_key,
    get_propensity_text,
    get_theme_key,
    get_theme_label,
    get_value_badge,
    summarize_segment,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("email_renderer")

# Mapa de plantillas por segmento de edad
TEMPLATE_MAP = {
    "JOVEN": "template_joven.html",
    "ADULTO": "template_adulto.html",
    "SENIOR": "template_senior.html",
}


def _get_young_theme_variant(
    campaign_data: dict,
    moment: str,
    theme_key: str,
    hotel_name: str,
    city_name: str,
) -> int:
    """Devuelve una variante visual estable para emails del segmento joven."""
    seed_parts = [
        campaign_data.get("guest_id", ""),
        moment,
        theme_key,
        hotel_name,
        city_name,
        campaign_data.get("checkin_suggested", ""),
        campaign_data.get("season", ""),
    ]
    seed = "|".join(str(part or "") for part in seed_parts)
    return int(md5(seed.encode("utf-8")).hexdigest()[:8], 16)


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
    """Renderiza un email HTML a partir de la campaña y el copy generado."""
    env = _get_env()
    seg = campaign_data.get("segment", {})
    age_segment = get_age_key(seg)

    if moment == "checkin_report":
        template_name = "receptionist_report.html"
    else:
        template_name = TEMPLATE_MAP.get(age_segment, "template_adulto.html")

    template = env.get_template(template_name)

    # Construir contexto
    if moment == "checkin_report":
        context = {
            "profile": campaign_data.get("profile_summary", {}),
            "segment": seg,
            "segment_overview": campaign_data.get("segment_overview", summarize_segment(seg)),
            "segment_value_badge": get_value_badge(seg),
            "segment_propensity_text": get_propensity_text(seg),
            "preferences": campaign_data.get("preferences", []),
            "upsell_recommendations": campaign_data.get("upsell_recommendations", []),
            "visit_history": campaign_data.get("visit_history", []),
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        context["profile"]["guest_id"] = campaign_data.get("guest_id", "")
    else:
        # Pre-arrival o post-stay
        if moment == "post_stay":
            # En post_stay se muestra last_stay, pero el siguiente destino sale de recommended_hotel
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

        theme_key = get_theme_key(seg)
        context = {
            "user_name": None,  # No hay nombres reales en los datos -> "Estimado viajero"
            "hotel_name": hotel_name,
            "city_name": city_name,
            "country": country,
            "stars": stars,
            "theme_key": theme_key,
            "theme_label": get_theme_label(seg),
            "young_theme_variant_index": _get_young_theme_variant(
                campaign_data,
                moment,
                theme_key,
                hotel_name,
                city_name,
            ),
            "segment_overview": campaign_data.get("segment_overview", summarize_segment(seg)),
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
            f"La plantilla renderizada {template_name} para el huésped {campaign_data.get('guest_id', '?')} está vacía"
        )
    logger.info("Plantilla %s renderizada para el huésped %s (%s)",
                template_name, campaign_data.get("guest_id", "?"), moment)
    return html


def save_email(html: str, guest_id: str, moment: str) -> str:
    """Guarda el email renderizado en el directorio de salida."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"{moment}_{guest_id}.html"
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Email guardado en %s", path)
    return path


def main():
    """Prueba el renderizado con datos de ejemplo."""
    import json

    with open(EMBEDDINGS_PATH) as f:
        embeddings = json.load(f)
    with open(SEGMENTS_PATH) as f:
        segments = json.load(f)

    from backend.campaigns import copy as text_generator
    from backend.campaigns import planner as campaign_engine

    # Probar las tres plantillas con distintos usuarios
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
