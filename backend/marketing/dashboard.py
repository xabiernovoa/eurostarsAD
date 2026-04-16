#!/usr/bin/env python3
"""
dashboard_engine.py — Motor factual del dashboard de marketing.

Construye un panel ejecutivo a partir de:
- logs de ejecución de campañas
- segmentación de audiencia
- histórico de reservas
- contexto de dirección, recepción y señales externas
"""

from __future__ import annotations

import json
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
    get_age_label,
    get_primary_affinity_label,
    get_segment_label,
    get_value_label,
)
from backend.storage.campaign_log import load_campaign_log as load_campaign_log_data
from backend.storage.customers import load_customers_df
from backend.storage.marketing_context import (
    load_marketing_context,
    save_marketing_context,
)
from backend.storage.segments import load_segments as load_segments_data

load_dotenv()

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

MOMENT_LABELS = {
    "pre_arrival": "Prellegada",
    "checkin_report": "Recepción",
    "post_stay": "Postestancia",
}

CHANNEL_LABELS = {
    "email": "Email",
    "sms": "SMS",
    "push": "Push",
    "internal_report": "Informe interno",
}

COUNTRY_LABELS = {
    "ES": "España",
    "PT": "Portugal",
    "IT": "Italia",
}

KNOWN_SIGNAL_CITIES = (
    "Lisboa",
    "Sevilla",
    "Madrid",
    "Roma",
    "Oporto",
    "Granada",
    "El Grove",
)


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


def _share(count: int, total: int) -> float:
    return round(count / max(total, 1), 2)


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
        rows.append({
            "guest_id": guest_id,
            "campaign_type": entry.get("campaign_type", ""),
            "channel": entry.get("channel", ""),
            "subject": entry.get("subject", ""),
            "hotel": entry.get("hotel_recommended", ""),
            "status": entry.get("status", ""),
            "timestamp": entry.get("timestamp", ""),
            "segment_label": get_segment_label(segment),
            "avg_leadtime": round(reservation.get("avg_leadtime", 0.0), 1),
            "avg_stay": round(reservation.get("avg_stay", 0.0), 1),
            "avg_score": round(reservation.get("avg_score", segment.get("avg_score", 0.0)), 1),
            "avg_adr": round(reservation.get("avg_adr", 0.0), 2),
        })
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    return rows


def _segment_country(segment: dict | None) -> str:
    segment = segment if isinstance(segment, dict) else {}
    tags = segment.get("tags", {})
    demographics = tags.get("demografia", {}) if isinstance(tags, dict) else {}
    country = str(segment.get("country") or demographics.get("pais") or "").strip().upper()
    return country or "N/D"


def _build_real_distribution(items: list[tuple[str, dict]], label_key: str) -> list[dict]:
    total = len(items)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for label, reservation in items:
        grouped[label].append(reservation)

    data = []
    for label, reservations in grouped.items():
        count = len(reservations)
        data.append({
            "label": label,
            "count": count,
            "share": _share(count, total),
            "avg_adr": round(sum(item.get("avg_adr", 0.0) for item in reservations) / max(count, 1), 2),
            "avg_stay": round(sum(item.get("avg_stay", 0.0) for item in reservations) / max(count, 1), 1),
            "avg_leadtime": round(sum(item.get("avg_leadtime", 0.0) for item in reservations) / max(count, 1), 1),
            "group": label_key,
        })
    data.sort(key=lambda item: (-item["count"], item["label"]))
    return data


def _build_audience_facts(segments: dict, reservations: dict) -> dict:
    age_items = []
    value_items = []
    affinity_items = []
    country_items = []

    for guest_id, segment in segments.items():
        reservation = reservations.get(str(guest_id), {})
        age_items.append((get_age_label(segment), reservation))
        value_items.append((get_value_label(segment), reservation))
        affinity_items.append((get_primary_affinity_label(segment), reservation))
        country_code = _segment_country(segment)
        country_items.append((COUNTRY_LABELS.get(country_code, country_code), reservation))

    return {
        "by_age": _build_real_distribution(age_items, "age"),
        "by_value": _build_real_distribution(value_items, "value"),
        "by_affinity": _build_real_distribution(affinity_items, "affinity"),
        "by_country": _build_real_distribution(country_items, "country"),
    }


def _build_channel_distribution(rows: list[dict]) -> list[dict]:
    total = len(rows)
    counts = Counter(str(row.get("channel") or "unknown") for row in rows)
    order = ["email", "sms", "push", "internal_report"]
    data = []
    for channel in order:
        count = counts.get(channel, 0)
        if count == 0:
            continue
        data.append({
            "key": channel,
            "label": CHANNEL_LABELS.get(channel, channel),
            "count": count,
            "share": _share(count, total),
        })
    return data


def _build_moment_distribution(rows: list[dict]) -> list[dict]:
    total = len(rows)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("campaign_type") or "unknown")].append(row)

    order = ["pre_arrival", "checkin_report", "post_stay"]
    data = []
    for moment in order:
        items = grouped.get(moment, [])
        if not items:
            continue
        with_hotel = sum(1 for item in items if item.get("hotel"))
        with_subject = sum(1 for item in items if item.get("subject"))
        counts_by_channel = Counter(str(item.get("channel") or "unknown") for item in items)
        data.append({
            "key": moment,
            "label": MOMENT_LABELS.get(moment, moment),
            "count": len(items),
            "share": _share(len(items), total),
            "with_hotel": with_hotel,
            "without_hotel": len(items) - with_hotel,
            "with_subject": with_subject,
            "without_subject": len(items) - with_subject,
            "channels": [
                {
                    "key": channel,
                    "label": CHANNEL_LABELS.get(channel, channel),
                    "count": counts_by_channel[channel],
                    "share": _share(counts_by_channel[channel], len(items)),
                }
                for channel in ("email", "sms", "push", "internal_report")
                if counts_by_channel.get(channel, 0) > 0
            ],
        })
    return data


def _build_top_hotels(rows: list[dict]) -> list[dict]:
    counts = Counter(str(row.get("hotel") or "").strip() for row in rows if str(row.get("hotel") or "").strip())
    total = sum(counts.values())
    return [
        {
            "hotel": hotel,
            "count": count,
            "share": _share(count, total),
        }
        for hotel, count in counts.most_common(8)
    ]


def _build_signal_facts(context: dict) -> dict:
    signals = []
    city_counts = Counter()

    for raw in context.get("external_signals", []):
        matched_city = next((city for city in KNOWN_SIGNAL_CITIES if city.lower() in raw.lower()), "")
        if matched_city:
            city_counts[matched_city] += 1
        signals.append({
            "text": raw,
            "city": matched_city,
        })

    return {
        "signals": signals,
        "cities": [
            {"city": city, "count": count}
            for city, count in city_counts.most_common(6)
        ],
    }


def _build_segment_facts(
    segments: dict,
    reservations: dict,
    campaign_rows: list[dict],
) -> list[dict]:
    grouped_users: dict[str, list[dict]] = defaultdict(list)
    grouped_countries: dict[str, Counter] = defaultdict(Counter)
    grouped_channels: dict[str, Counter] = defaultdict(Counter)
    grouped_moments: dict[str, Counter] = defaultdict(Counter)

    for guest_id, segment in segments.items():
        label = get_segment_label(segment)
        grouped_users[label].append(reservations.get(str(guest_id), {}))
        grouped_countries[label][_segment_country(segment)] += 1

    for row in campaign_rows:
        label = str(row.get("segment_label") or "Sin segmento")
        grouped_channels[label][str(row.get("channel") or "unknown")] += 1
        grouped_moments[label][str(row.get("campaign_type") or "unknown")] += 1

    data = []
    total_users = len(segments)
    for label, users in grouped_users.items():
        count = len(users)
        top_country = grouped_countries[label].most_common(1)[0][0] if grouped_countries[label] else "N/D"
        top_channel = grouped_channels[label].most_common(1)[0][0] if grouped_channels[label] else ""
        top_moment = grouped_moments[label].most_common(1)[0][0] if grouped_moments[label] else ""
        data.append({
            "segment_label": label,
            "users": count,
            "share": _share(count, total_users),
            "avg_adr": round(sum(item.get("avg_adr", 0.0) for item in users) / max(count, 1), 2),
            "avg_stay": round(sum(item.get("avg_stay", 0.0) for item in users) / max(count, 1), 1),
            "avg_leadtime": round(sum(item.get("avg_leadtime", 0.0) for item in users) / max(count, 1), 1),
            "avg_reservations": round(sum(item.get("reservations", 0.0) for item in users) / max(count, 1), 1),
            "message_count": sum(grouped_channels[label].values()),
            "top_country": COUNTRY_LABELS.get(top_country, top_country),
            "top_channel": CHANNEL_LABELS.get(top_channel, top_channel),
            "top_moment": MOMENT_LABELS.get(top_moment, top_moment),
        })
    return data


def _build_factual_overview(
    campaign_rows: list[dict],
    segments: dict,
    context: dict,
    audience_facts: dict,
    top_hotels: list[dict],
) -> dict:
    valid_timestamps = [str(row.get("timestamp")) for row in campaign_rows if row.get("timestamp")]
    first_activity = min(valid_timestamps) if valid_timestamps else ""
    last_activity = max(valid_timestamps) if valid_timestamps else ""
    rows_with_hotel = sum(1 for row in campaign_rows if row.get("hotel"))
    rows_with_subject = sum(1 for row in campaign_rows if row.get("subject"))

    return {
        "guest_count": len(segments),
        "message_count": len(campaign_rows),
        "country_count": len(audience_facts["by_country"]),
        "hotel_count": len({str(row.get("hotel") or "").strip() for row in campaign_rows if str(row.get("hotel") or "").strip()}),
        "signal_count": len(context.get("external_signals", [])),
        "rows_with_hotel": rows_with_hotel,
        "rows_without_hotel": len(campaign_rows) - rows_with_hotel,
        "rows_with_subject": rows_with_subject,
        "rows_without_subject": len(campaign_rows) - rows_with_subject,
        "first_activity_at": first_activity,
        "last_activity_at": last_activity,
    }


def build_dashboard_data() -> dict:
    """Construye el payload completo del dashboard de marketing."""
    context = load_context()
    segments = _load_segments()
    customers = _load_customers()
    reservations = _build_reservation_metrics(customers)
    campaigns = _latest_campaigns(_load_campaign_log())
    campaign_rows = _build_campaign_rows(campaigns, segments, reservations)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "context": context,
        "campaign_rows": campaign_rows,
    }
    audience_facts = _build_audience_facts(segments, reservations)
    top_hotels = _build_top_hotels(campaign_rows)
    segment_facts = _build_segment_facts(segments, reservations, campaign_rows)
    signal_facts = _build_signal_facts(context)

    payload["overview_facts"] = _build_factual_overview(
        campaign_rows,
        segments,
        context,
        audience_facts,
        top_hotels,
    )
    payload["audience_facts"] = audience_facts
    payload["channel_distribution"] = _build_channel_distribution(campaign_rows)
    payload["moment_distribution"] = _build_moment_distribution(campaign_rows)
    payload["top_hotels"] = top_hotels
    payload["signal_facts"] = signal_facts
    payload["segment_rankings"] = {
        "by_size": sorted(
            segment_facts,
            key=lambda item: (-item["users"], -item["avg_adr"], item["segment_label"]),
        )[:10],
        "by_adr": sorted(
            [item for item in segment_facts if item["users"] >= 3],
            key=lambda item: (-item["avg_adr"], -item["users"], item["segment_label"]),
        )[:10],
    }
    payload["recent_messages"] = campaign_rows[:40]
    return payload


def main():
    print(json.dumps(build_dashboard_data(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
