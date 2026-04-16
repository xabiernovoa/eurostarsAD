#!/usr/bin/env python3
"""
dashboard_engine.py — Motor de insights de marketing.

Construye un dashboard ejecutivo a partir de:
- logs de ejecución de campañas
- segmentación de audiencia
- histórico de reservas
- contexto de dirección, recepción y señales externas

Las recomendaciones del dashboard se generan con un modelo heurístico determinista.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

from backend.paths import MARKETING_CONTEXT_PATH
from backend.personalization.segment_views import (
    get_age_key,
    get_age_order,
    get_loyalty_principal,
    get_primary_affinity,
    get_primary_affinity_label,
    get_segment_label,
    get_value_label,
    get_value_level,
    get_value_weight,
)
from backend.storage.campaign_log import load_campaign_log as load_campaign_log_data
from backend.storage.customers import load_customers_df
from backend.storage.marketing_context import (
    load_marketing_context,
    save_marketing_context,
)
from backend.storage.segments import load_segments as load_segments_data

load_dotenv()

logger = logging.getLogger("marketing_dashboard")

CONTEXT_PATH = MARKETING_CONTEXT_PATH

DEFAULT_CONTEXT = {
    "strategic_priority": (
        "Impulsar reservas directas para escapadas urbanas premium entre mayo y julio "
        "con foco en Lisboa, Sevilla y Madrid."
    ),
    "manager_notes": [
        "El objetivo del trimestre es mejorar la conversión del segmento ADULTO de valor medio y alto.",
        "Necesitamos una narrativa más consistente entre email, RRSS y la experiencia dentro del hotel.",
        "Interesa priorizar campañas con margen alto y capacidad para generar reserva directa."
    ],
    "reception_notes": [
        "Recepción detecta más preguntas sobre experiencias gastronómicas y rooftops al hacer check-in.",
        "Los huéspedes de perfil cultural piden itinerarios de 48 horas y recomendaciones de barrio.",
        "Hay margen para vender upgrades y late checkout si se comunica antes de la llegada."
    ],
    "external_signals": [
        "Lisboa Design Week 2026-05-22 con alta afinidad para perfiles culturales.",
        "San Isidro Madrid 2026-05-15 aumenta el interés por escapadas urbanas de fin de semana.",
        "Sevilla concentra búsquedas de city break premium y contenido gastronómico de primavera."
    ],
}

MOMENT_WEIGHT = {"pre_arrival": 0.68, "post_stay": 0.56, "checkin_report": 0.61}
CHANNEL_WEIGHT = {"email": 0.72, "sms": 0.67, "push": 0.75, "internal_report": 0.58}
AFFINITY_BOOST = {
    "cultural": 0.08,
    "montana": 0.09,
    "gastronomico": 0.07,
    "playero": 0.06,
    "clima_calido": 0.05,
    "mediterraneo": 0.06,
    "continental": 0.05,
}


def ensure_context_file() -> Path:
    """Crea el fichero de contexto de marketing si no existe."""
    if not CONTEXT_PATH.exists():
        save_marketing_context(DEFAULT_CONTEXT)
    return CONTEXT_PATH


def load_context() -> dict:
    """Carga el contexto de marketing editable."""
    ensure_context_file()
    context = load_marketing_context(DEFAULT_CONTEXT)
    for key in ("manager_notes", "reception_notes", "external_signals"):
        value = context.get(key, [])
        if isinstance(value, str):
            context[key] = [line.strip() for line in value.splitlines() if line.strip()]
        else:
            context[key] = [str(item).strip() for item in value if str(item).strip()]
    return context


def save_context(context: dict) -> dict:
    """Persiste el contexto tras normalizarlo."""
    normalized = {
        "strategic_priority": str(context.get("strategic_priority", "")).strip(),
        "manager_notes": _normalize_lines(context.get("manager_notes", [])),
        "reception_notes": _normalize_lines(context.get("reception_notes", [])),
        "external_signals": _normalize_lines(context.get("external_signals", [])),
    }
    save_marketing_context(normalized)
    return normalized


def _normalize_lines(value: list | str) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _load_segments() -> dict:
    return load_segments_data()


def _load_campaign_log() -> list[dict]:
    return load_campaign_log_data()


def _load_customers() -> pd.DataFrame:
    return load_customers_df()


def _latest_campaigns(campaign_log: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str, str], dict] = {}
    for entry in campaign_log:
        key = (
            str(entry.get("guest_id", "")),
            str(entry.get("campaign_type", "")),
            str(entry.get("output_file", entry.get("channel", ""))),
        )
        current = latest.get(key)
        if current is None or entry.get("timestamp", "") >= current.get("timestamp", ""):
            latest[key] = entry
    return list(latest.values())


def _build_reservation_metrics(customers: pd.DataFrame) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    grouped = customers.groupby("GUEST_ID", sort=False)
    for guest_id, group in grouped:
        last_row = group.sort_values("CHECKOUT_DATE").iloc[-1]
        metrics[str(guest_id)] = {
            "reservations": int(group["RESERVATION_ID"].nunique()),
            "destinations": int(group["HOTEL_ID"].nunique()),
            "avg_leadtime": float(group["AVG_BOOKING_LEADTIME"].mean()),
            "avg_stay": float(group["AVG_LENGTH_STAY"].mean()),
            "avg_score": float(group["AVG_SCORE"].mean()),
            "avg_adr": float(group["CONFIRMED_RESERVATIONS_ADR"].mean()),
            "last_checkin": last_row["CHECKIN_DATE"].strftime("%Y-%m-%d"),
            "last_checkout": last_row["CHECKOUT_DATE"].strftime("%Y-%m-%d"),
        }
    return metrics


def _engagement_index(segment: dict, campaign: dict, reservation: dict) -> float:
    value_score = get_value_weight(segment)
    moment_score = MOMENT_WEIGHT.get(campaign.get("campaign_type", "pre_arrival"), 0.55)
    channel_score = CHANNEL_WEIGHT.get(campaign.get("channel", "email"), 0.65)
    profile_score = AFFINITY_BOOST.get(get_primary_affinity(segment), 0.04)
    quality_score = min(max((reservation.get("avg_score", 7.0) - 5.0) / 5.0, 0.0), 1.0) * 0.15
    stay_score = min(reservation.get("avg_stay", 2.0) / 5.0, 1.0) * 0.08
    leadtime = reservation.get("avg_leadtime", 15.0)
    leadtime_fit = 0.08 if 10 <= leadtime <= 35 else 0.03

    raw = value_score + moment_score * 0.35 + channel_score * 0.22 + profile_score + quality_score + stay_score + leadtime_fit
    return round(min(raw / 1.45, 0.99), 2)


def _channel_alignment(segment: dict, campaign: dict, reservation: dict) -> str:
    channel = campaign.get("channel", "email")
    age_segment = get_age_key(segment)
    leadtime = reservation.get("avg_leadtime", 15.0)
    if channel == "push" and age_segment == "JOVEN":
        return "Alta"
    if channel == "sms" and leadtime < 7:
        return "Alta"
    if channel == "email" and age_segment in {"ADULTO", "SENIOR"}:
        return "Alta"
    if channel == "internal_report":
        return "Operativa"
    return "Media"


def _build_campaign_rows(
    campaigns: list[dict],
    segments: dict,
    reservations: dict,
) -> list[dict]:
    rows = []
    for entry in campaigns:
        guest_id = str(entry.get("guest_id", ""))
        segment = segments.get(guest_id, {})
        reservation = reservations.get(guest_id, {})
        engagement = _engagement_index(segment, entry, reservation)
        primary_affinity = get_primary_affinity(segment)
        rows.append({
            "guest_id": guest_id,
            "campaign_type": entry.get("campaign_type", ""),
            "channel": entry.get("channel", ""),
            "subject": entry.get("subject", ""),
            "hotel": entry.get("hotel_recommended", ""),
            "status": entry.get("status", ""),
            "timestamp": entry.get("timestamp", ""),
            "demographic_age": get_age_key(segment),
            "primary_affinity": primary_affinity,
            "primary_affinity_label": get_primary_affinity_label(segment),
            "value_level": get_value_level(segment),
            "value_label": get_value_label(segment),
            "loyalty": get_loyalty_principal(segment),
            "segment_label": get_segment_label(segment),
            "avg_leadtime": round(reservation.get("avg_leadtime", 0.0), 1),
            "avg_stay": round(reservation.get("avg_stay", 0.0), 1),
            "avg_score": round(reservation.get("avg_score", segment.get("avg_score", 0.0)), 1),
            "avg_adr": round(reservation.get("avg_adr", 0.0), 2),
            "engagement_index": engagement,
            "channel_alignment": _channel_alignment(segment, entry, reservation),
        })
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    return rows


def _build_segment_cards(rows: list[dict], segments: dict, reservations: dict) -> list[dict]:
    cards = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = row["segment_label"]
        grouped[key].append(row)

    for key, items in grouped.items():
        guest_ids = {item["guest_id"] for item in items}
        revenue = sum(reservations.get(guest_id, {}).get("avg_adr", 0.0) for guest_id in guest_ids)
        cards.append({
            "segment_label": key,
            "demographic_age": items[0]["demographic_age"],
            "primary_affinity": items[0]["primary_affinity"],
            "primary_affinity_label": items[0]["primary_affinity_label"],
            "value_level": items[0]["value_level"],
            "value_label": items[0]["value_label"],
            "users": len(guest_ids),
            "campaigns": len(items),
            "avg_engagement_index": round(sum(item["engagement_index"] for item in items) / len(items), 2),
            "avg_adr": round(revenue / max(len(guest_ids), 1), 2),
            "dominant_channel": Counter(item["channel"] for item in items).most_common(1)[0][0],
            "dominant_moment": Counter(item["campaign_type"] for item in items).most_common(1)[0][0],
            "share_of_base": round(len(guest_ids) / max(len(segments), 1), 2),
        })

    cards.sort(
        key=lambda item: (
            -item["avg_engagement_index"],
            -item["users"],
            get_age_order({"tags": {"demografia": {"edad": item["demographic_age"].lower()}}}),
        )
    )
    return cards[:8]


def _build_kpis(rows: list[dict], segments: dict, context: dict) -> dict:
    campaigns_count = len(rows)
    active_segments = len({row["segment_label"] for row in rows})
    avg_index = round(sum(row["engagement_index"] for row in rows) / max(campaigns_count, 1), 2)
    priority_pressure = min(
        100,
        48 + len(context.get("manager_notes", [])) * 7 + len(context.get("external_signals", [])) * 4,
    )
    return {
        "total_campaigns": campaigns_count,
        "audience_size": len(segments),
        "active_segments": active_segments,
        "avg_engagement_index": avg_index,
        "priority_pressure": priority_pressure,
    }


def _build_breakdown(rows: list[dict], key: str, label: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key, "N/A"))].append(row)

    data = []
    for group_name, items in grouped.items():
        data.append({
            "label": group_name,
            "count": len(items),
            "share": round(len(items) / max(len(rows), 1), 2),
            "avg_engagement_index": round(sum(item["engagement_index"] for item in items) / len(items), 2),
            "best_channel": Counter(item["channel"] for item in items).most_common(1)[0][0],
            "top_hotel": Counter(item["hotel"] for item in items if item["hotel"]).most_common(1)[0][0] if any(item["hotel"] for item in items) else "Sin asignar",
            "group": label,
        })
    data.sort(key=lambda item: (-item["avg_engagement_index"], -item["count"], item["label"]))
    return data


def _city_mentions(rows: list[dict], context: dict) -> list[str]:
    city_counts = Counter()
    for row in rows:
        hotel = row.get("hotel", "")
        if hotel:
            city_counts[hotel] += 1
    for signal in context.get("external_signals", []):
        for city in ("Lisboa", "Sevilla", "Madrid", "Roma", "Oporto", "Granada"):
            if city.lower() in signal.lower():
                city_counts[city] += 2
    return [name for name, _ in city_counts.most_common(3)]


def _heuristic_recommendations(rows: list[dict], context: dict, segment_cards: list[dict]) -> dict:
    top_segments = segment_cards[:3]
    top_segment_names = [card["segment_label"] for card in top_segments]
    focus_cities = _city_mentions(rows, context)
    manager_priority = context.get("strategic_priority", "")
    reception_notes = context.get("reception_notes", [])
    external_signals = context.get("external_signals", [])

    rrss_summary = (
        f"Activar una línea de contenido short-form para {', '.join(top_segment_names[:2]) or 'los segmentos con más tracción'}, "
        f"con foco en {' y '.join(focus_cities[:2]) or 'los destinos urbanos principales'}. "
        f"El contenido debe mezclar escapada, gastronomía y prueba social de estancia."
    )
    rrss_actions = [
        "Lanzar una serie de Reels/TikToks con itinerarios de 48 horas para perfiles culturales y aventureros.",
        "Replicar en paid social las creatividades de los asuntos con mejor índice estimado y añadir CTA a reserva directa.",
        "Usar testimonios y UGC de check-in para reforzar confianza en segmentos de mayor ADR."
    ]

    hotel_summary = (
        f"Recepción está detectando señales convertibles en upsell: {reception_notes[0] if reception_notes else 'interés en experiencias y upgrades'}. "
        "La oportunidad está en preparar el terreno antes del check-in y rematarla en lobby y habitaciones."
    )
    hotel_actions = [
        "Crear un mini welcome journey con QR en recepción para rooftop, gastronomía y late checkout.",
        "Sincronizar el mensaje del email pre-arrival con ofertas visibles en lobby y ascensores.",
        "Activar scripts de recepción por segmento para vender upgrades sin fricción."
    ]

    ads_summary = (
        f"El esfuerzo externo debería alinearse con '{manager_priority or 'las reservas directas de alto margen'}'. "
        f"Las señales externas más útiles ahora son: {external_signals[0] if external_signals else 'los eventos urbanos de primavera'}."
    )
    ads_actions = [
        "Concentrar inversión en búsqueda y metasearch para ciudades con señales externas activas y mejor ADR medio.",
        "Abrir campañas lookalike desde segmentos premium y confort con histórico cultural y gastronómico.",
        "Separar campañas de branding y performance para medir mejor qué creatividad empuja reserva directa."
    ]

    return {
        "source": "heuristic",
        "rrss": {"summary": rrss_summary, "actions": rrss_actions},
        "hotel": {"summary": hotel_summary, "actions": hotel_actions},
        "ads": {"summary": ads_summary, "actions": ads_actions},
    }


def _generate_recommendations(payload: dict) -> dict:
    return _heuristic_recommendations(
        payload["campaign_rows"],
        payload["context"],
        payload["segment_cards"],
    )


def build_dashboard_data() -> dict:
    """Construye el payload completo del dashboard de marketing."""
    context = load_context()
    segments = _load_segments()
    customers = _load_customers()
    reservations = _build_reservation_metrics(customers)
    campaigns = _latest_campaigns(_load_campaign_log())
    campaign_rows = _build_campaign_rows(campaigns, segments, reservations)
    segment_cards = _build_segment_cards(campaign_rows, segments, reservations)
    kpis = _build_kpis(campaign_rows, segments, context)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "context": context,
        "kpis": kpis,
        "campaign_rows": campaign_rows,
        "segment_cards": segment_cards,
        "performance_by_age": _build_breakdown(campaign_rows, "demographic_age", "age"),
        "performance_by_affinity": _build_breakdown(campaign_rows, "primary_affinity_label", "affinity"),
        "performance_by_value_level": _build_breakdown(campaign_rows, "value_label", "value"),
        "performance_by_loyalty": _build_breakdown(campaign_rows, "loyalty", "loyalty"),
        "performance_by_moment": _build_breakdown(campaign_rows, "campaign_type", "moment"),
    }
    payload["recommendations"] = _generate_recommendations(payload | {"context": context})
    payload["focus_cities"] = _city_mentions(campaign_rows, context)
    payload["recent_campaigns"] = campaign_rows[:12]
    return payload


def main():
    print(json.dumps(build_dashboard_data(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
