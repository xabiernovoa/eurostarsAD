#!/usr/bin/env python3
"""
campaign_engine.py — Phase 3: Campaign Engine

Manages three moments in the customer lifecycle:
  - pre_arrival: email before the predicted travel window
  - checkin_report: receptionist brief at check-in
  - post_stay: follow-up email after checkout
"""

import json
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.personalization import embeddings as emb_module
from backend.storage.customers import load_customers_df
from backend.storage.embeddings import load_embeddings
from backend.storage.segments import load_segments as load_segments_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("campaign_engine")

SEASON_MAP = {
    12: "invierno", 1: "invierno", 2: "invierno",
    3: "primavera", 4: "primavera", 5: "primavera",
    6: "verano", 7: "verano", 8: "verano",
    9: "otoño", 10: "otoño", 11: "otoño",
}

# Mock events database (hook for real API integration)
MOCK_EVENTS = {
    "SEVILLA": [
        {"name": "Festival de las Naciones", "date": "2025-10-01", "type": "cultural"},
        {"name": "Bienal de Flamenco", "date": "2025-09-15", "type": "cultural"},
    ],
    "GRANADA": [
        {"name": "Festival Internacional de Música", "date": "2025-06-20", "type": "cultural"},
    ],
    "LISBOA": [
        {"name": "Festival de Fado", "date": "2025-06-10", "type": "música"},
        {"name": "Festas de Lisboa", "date": "2025-06-13", "type": "cultural"},
    ],
    "OPORTO": [
        {"name": "São João Festival", "date": "2025-06-23", "type": "fiesta"},
    ],
    "ROMA": [
        {"name": "Estate Romana", "date": "2025-06-01", "type": "cultural"},
        {"name": "Notte Bianca", "date": "2025-09-15", "type": "cultural"},
    ],
    "MADRID": [
        {"name": "Madrid Design Festival", "date": "2025-02-10", "type": "diseño"},
        {"name": "San Isidro", "date": "2025-05-15", "type": "fiesta"},
    ],
    "EL GROVE": [
        {"name": "Fiesta del Marisco", "date": "2025-10-01", "type": "gastronomía"},
    ],
}


def _load_data() -> tuple[dict, dict, pd.DataFrame]:
    """Load embeddings, segments, and customer reservations."""
    return load_embeddings(), load_segments_data(), load_customers_df()


def _predict_travel_window(customer_rows: pd.DataFrame) -> tuple[str, str, int]:
    """
    Predict the most likely travel month and send date.
    Returns (send_date, checkin_suggested, stay_nights).
    """
    months = customer_rows["CHECKIN_DATE"].dt.month.tolist()
    most_common_month = Counter(months).most_common(1)[0][0]

    avg_leadtime = customer_rows["AVG_BOOKING_LEADTIME"].iloc[0]
    avg_stay = customer_rows["AVG_LENGTH_STAY"].iloc[0]

    # Suggested checkin: 15th of the most common month, next occurrence
    now = datetime.now()
    year = now.year if most_common_month >= now.month else now.year + 1
    checkin = datetime(year, most_common_month, 15)

    # Send date: checkin minus leadtime (at least 14 days before)
    send_offset = max(int(avg_leadtime), 14)
    send_date = checkin - timedelta(days=send_offset)

    return (
        send_date.strftime("%Y-%m-%d"),
        checkin.strftime("%Y-%m-%d"),
        max(1, int(round(avg_stay))),
    )


def _get_events(city: str, month: int) -> list[dict]:
    """Get events in city near the predicted month. Mock implementation."""
    events = MOCK_EVENTS.get(city.upper(), [])
    matching = []
    for ev in events:
        ev_date = datetime.strptime(ev["date"], "%Y-%m-%d")
        if ev_date.month == month or abs(ev_date.month - month) <= 1:
            matching.append(ev)
    return matching


def _get_embedding_preferences(embedding: dict[str, float]) -> list[str]:
    """Translate embedding dimensions to natural-language preferences."""
    prefs = []
    if embedding.get("HERITAGE", 0) > 0.6:
        prefs.append("patrimonio histórico y cultural")
    if embedding.get("GASTRONOMY", 0) > 0.6:
        prefs.append("gastronomía local")
    if embedding.get("BEACH", 0) > 0.5:
        prefs.append("playa y actividades al aire libre")
    if embedding.get("MOUNTAIN", 0) > 0.5:
        prefs.append("montaña y naturaleza")
    if embedding.get("PRICE_LEVEL", 0) > 0.7:
        prefs.append("experiencias premium y exclusivas")
    if embedding.get("STARS_NORM", 0) > 0.7:
        prefs.append("alojamientos de alta categoría")
    if embedding.get("TEMP_NORM", 0) > 0.7:
        prefs.append("destinos cálidos y soleados")
    if not prefs:
        prefs.append("diversidad de experiencias")
    return prefs


def _upsell_recommendations(value_tier: str, travel_profile: str) -> list[str]:
    """Generate upsell recommendations based on client value."""
    if value_tier == "HIGH_VALUE":
        recs = [
            "Upgrade a suite con vistas",
            "Acceso premium al spa y zona wellness",
            "Minibar premium (agua Fiji, champán Moët)",
            "Late checkout hasta las 14:00",
            "Experiencia gastronómica exclusiva del chef",
        ]
    elif value_tier == "MID_VALUE":
        recs = [
            "Desayuno buffet incluido",
            "Parking gratuito durante la estancia",
            "Visita guiada por la ciudad",
            "Descuento del 15% en restaurante del hotel",
        ]
    else:  # STANDARD
        recs = [
            "Inscripción en programa de fidelización Eurostars Loyalty",
            "Descuento del 10% en próxima reserva directa",
            "Upgrade de habitación sujeto a disponibilidad",
        ]

    # Add profile-specific suggestions
    profile_recs = {
        "EXPLORADOR_CULTURAL": "Entrada a museos y monumentos cercanos",
        "LUJO": "Transfer privado aeropuerto-hotel",
        "SOL_Y_PLAYA": "Kit de playa premium (toalla, crema solar)",
        "AVENTURERO": "Excursión guiada de senderismo o naturaleza",
        "GASTRONOMIA_CIUDAD": "Reserva en restaurantes locales con estrella Michelin",
    }
    if travel_profile in profile_recs:
        recs.append(profile_recs[travel_profile])

    return recs


# ── Campaign generators ──────────────────────────────────────────────────

def generate_pre_arrival(guest_id: str, embeddings: dict, segments: dict,
                         customers: pd.DataFrame) -> dict | None:
    """Generate pre-arrival campaign data for a specific guest."""
    seg = segments.get(str(guest_id))
    if seg is None:
        logger.warning("No segment found for guest %s", guest_id)
        return None

    user_rows = customers[customers["GUEST_ID"] == str(guest_id)]
    if user_rows.empty:
        return None

    # Get recommendation
    recs = emb_module.recommend_hotel(str(guest_id), embeddings, top_n=1)
    if not recs:
        return None

    rec_hotel_id, similarity = recs[0]
    hotel = embeddings["hotel_info"].get(rec_hotel_id, {})
    user_emb = embeddings["user_embeddings"].get(str(guest_id), {})

    # Travel window
    send_date, checkin_suggested, stay_nights = _predict_travel_window(user_rows)
    checkin_dt = datetime.strptime(checkin_suggested, "%Y-%m-%d")
    season = SEASON_MAP.get(checkin_dt.month, "primavera")

    # Events
    events = _get_events(hotel.get("CITY_NAME", ""), checkin_dt.month)

    # Preferences
    preferences = _get_embedding_preferences(user_emb)

    return {
        "campaign_type": "pre_arrival",
        "guest_id": str(guest_id),
        "segment": seg,
        "recommended_hotel": {
            "id": rec_hotel_id,
            "name": hotel.get("HOTEL_NAME", ""),
            "city": hotel.get("CITY_NAME", ""),
            "country": hotel.get("COUNTRY_ID", ""),
            "stars": hotel.get("STARS", 4),
            "brand": hotel.get("BRAND", "EUROSTARS"),
            "similarity_score": round(similarity, 4),
        },
        "send_date": send_date,
        "checkin_suggested": checkin_suggested,
        "stay_nights": stay_nights,
        "season": season,
        "events": events,
        "preferences": preferences,
        "avg_length_stay": float(user_rows["AVG_LENGTH_STAY"].iloc[0]),
        "avg_booking_leadtime": float(user_rows["AVG_BOOKING_LEADTIME"].iloc[0]),
    }


def generate_checkin_report(guest_id: str, embeddings: dict, segments: dict,
                            customers: pd.DataFrame) -> dict | None:
    """Generate receptionist check-in report for a guest."""
    seg = segments.get(str(guest_id))
    if seg is None:
        return None

    user_rows = customers[customers["GUEST_ID"] == str(guest_id)]
    if user_rows.empty:
        return None

    ordered_rows = user_rows.sort_values(["CHECKIN_DATE", "CHECKOUT_DATE"])
    first = ordered_rows.iloc[0]
    last = ordered_rows.iloc[-1]
    user_emb = embeddings["user_embeddings"].get(str(guest_id), {})
    preferences = _get_embedding_preferences(user_emb)
    upsells = _upsell_recommendations(seg["client_value"], seg["travel_profile"])

    # Hotels visited
    visited = []
    for _, row in ordered_rows.iterrows():
        hinfo = embeddings["hotel_info"].get(str(row["HOTEL_ID"]), {})
        visited.append({
            "hotel_id": str(row["HOTEL_ID"]),
            "hotel_name": hinfo.get("HOTEL_NAME", ""),
            "checkin": row["CHECKIN_DATE"].strftime("%Y-%m-%d"),
            "checkout": row["CHECKOUT_DATE"].strftime("%Y-%m-%d"),
        })

    last_hotel_info = embeddings["hotel_info"].get(str(last["HOTEL_ID"]), {})

    return {
        "campaign_type": "checkin_report",
        "guest_id": str(guest_id),
        "segment": seg,
        "profile_summary": {
            "country": seg["country"],
            "gender": seg["gender"],
            "age_range": seg["age_range"],
            "total_stays": int(first["CONFIRMED_RESERVATIONS"]),
            "distinct_hotels": int(first["NUM_DISTINCT_HOTELS"]),
            "avg_score_given": float(first["AVG_SCORE"]),
            "avg_daily_rate": float(first["CONFIRMED_RESERVATIONS_ADR"]),
            "avg_stay_length": float(first["AVG_LENGTH_STAY"]),
            "last_checkin": last["CHECKIN_DATE"].strftime("%Y-%m-%d"),
            "last_hotel": last_hotel_info.get("HOTEL_NAME", ""),
        },
        "preferences": preferences,
        "upsell_recommendations": upsells,
        "visit_history": visited,
    }


def generate_post_stay(guest_id: str, embeddings: dict, segments: dict,
                       customers: pd.DataFrame) -> dict | None:
    """Generate post-stay campaign data."""
    seg = segments.get(str(guest_id))
    if seg is None:
        return None

    user_rows = customers[customers["GUEST_ID"] == str(guest_id)]
    if user_rows.empty:
        return None

    # Last stay
    last = user_rows.sort_values("CHECKOUT_DATE").iloc[-1]
    last_hotel = embeddings["hotel_info"].get(str(last["HOTEL_ID"]), {})

    # Next recommendation
    recs = emb_module.recommend_hotel(str(guest_id), embeddings, top_n=1)
    next_hotel = None
    if recs:
        hid, sim = recs[0]
        next_hotel = {
            "id": hid,
            **embeddings["hotel_info"].get(hid, {}),
            "similarity_score": round(sim, 4),
        }

    send_date = (last["CHECKOUT_DATE"] + timedelta(days=7)).strftime("%Y-%m-%d")

    return {
        "campaign_type": "post_stay",
        "guest_id": str(guest_id),
        "segment": seg,
        "last_stay": {
            "hotel_id": str(last["HOTEL_ID"]),
            "hotel_name": last_hotel.get("HOTEL_NAME", ""),
            "city": last_hotel.get("CITY_NAME", ""),
            "checkin": last["CHECKIN_DATE"].strftime("%Y-%m-%d"),
            "checkout": last["CHECKOUT_DATE"].strftime("%Y-%m-%d"),
        },
        "recommended_hotel": next_hotel,
        "send_date": send_date,
        "season": SEASON_MAP.get(last["CHECKOUT_DATE"].month, "primavera"),
        "preferences": _get_embedding_preferences(
            embeddings["user_embeddings"].get(str(guest_id), {})
        ),
    }


# ── Batch generators ─────────────────────────────────────────────────────

def generate_all(moment: str, guest_id: str | None = None) -> list[dict]:
    """Generate campaign data for all users (or a specific one)."""
    embeddings, segments, customers = _load_data()

    generators = {
        "pre_arrival": generate_pre_arrival,
        "checkin_report": generate_checkin_report,
        "post_stay": generate_post_stay,
    }

    gen_fn = generators.get(moment)
    if gen_fn is None:
        raise ValueError(f"Unknown moment: {moment}. Choose: {list(generators.keys())}")

    results = []
    if guest_id:
        result = gen_fn(str(guest_id), embeddings, segments, customers)
        if result:
            results.append(result)
    else:
        for uid in segments:
            result = gen_fn(uid, embeddings, segments, customers)
            if result:
                results.append(result)

    logger.info("Generated %d %s campaigns", len(results), moment)
    return results


def main():
    import sys
    moment = sys.argv[1] if len(sys.argv) > 1 else "pre_arrival"
    guest_id = sys.argv[2] if len(sys.argv) > 2 else "1014907189"

    results = generate_all(moment, guest_id)
    if results:
        print(json.dumps(results[0], indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
