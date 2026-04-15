#!/usr/bin/env python3
"""
channel_selector.py — Fase 7: selección del canal de comunicación

Selecciona el canal óptimo de comunicación (email / SMS / push)
en función del perfil del usuario y su comportamiento de reserva.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.personalization.segment_views import get_age_key, get_booking_behavior
from backend.storage.segments import load_segments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("channel_selector")


def select_channel(segment: dict, campaign_data: dict) -> dict:
    """
    Selecciona el canal de comunicación a partir del segmento del usuario.

    Devuelve:
        {
            "primary_channel": "email" | "sms" | "push",
            "secondary_channel": "email" | "sms" | "push" | None,
            "reason": str,
        }
    """
    age_segment = get_age_key(segment)
    booking_behavior = get_booking_behavior(segment)
    avg_leadtime = campaign_data.get("avg_booking_leadtime",
                                     segment.get("avg_booking_leadtime", 15))

    # Extraer el leadtime desde datos de cliente si la campaña lo trae anidado
    if "profile_summary" in campaign_data:
        # Para checkin_report se fuerza email por defecto
        avg_leadtime = 15

    # Regla 1: SENIOR -> siempre email, nunca SMS
    if age_segment == "SENIOR":
        return {
            "primary_channel": "email",
            "secondary_channel": None,
            "reason": "Segmento SENIOR: se prioriza email siempre para máxima claridad y comodidad.",
        }

    # Regla 2: lead time muy corto -> SMS
    if booking_behavior.get("antelacion") == "ultimo_minuto" or avg_leadtime < 7:
        secondary = "email"
        return {
            "primary_channel": "sms",
            "secondary_channel": secondary,
            "reason": f"Lead time corto ({avg_leadtime:.0f} días): SMS para decisión rápida, email como respaldo.",
        }

    # Regla 3: JOVEN con afinidad digital -> push notification
    if age_segment == "JOVEN":
        return {
            "primary_channel": "push",
            "secondary_channel": "email",
            "reason": "Segmento JOVEN con posible uso de app: push notification + email de respaldo.",
        }

    # Regla 4: lead time largo -> email
    if booking_behavior.get("antelacion") == "planificador" or avg_leadtime > 30:
        return {
            "primary_channel": "email",
            "secondary_channel": None,
            "reason": f"Lead time largo ({avg_leadtime:.0f} días): email para comunicación detallada.",
        }

    # Canal por defecto: email
    return {
        "primary_channel": "email",
        "secondary_channel": None,
        "reason": "Canal por defecto: email.",
    }


def select_channels_batch(campaigns: list[dict]) -> list[dict]:
    """Selecciona canales para un lote de campañas."""
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
    segments = load_segments()

    # Mostrar la distribución de canales
    from collections import Counter
    channels = Counter()
    for uid, seg in segments.items():
        ch = select_channel(seg, {"avg_booking_leadtime": 15})
        channels[ch["primary_channel"]] += 1

    logger.info("Distribución de canales: %s", dict(channels))


if __name__ == "__main__":
    main()
