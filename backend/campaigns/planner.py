#!/usr/bin/env python3
"""
campaign_engine.py — Fase 3: motor de campañas

Gestiona tres momentos del ciclo de vida del cliente:
  - pre_arrival: email antes de la ventana de viaje prevista
  - checkin_report: briefing de recepción en el check-in
  - post_stay: email de seguimiento tras el checkout
"""

import json
import logging
import sys
from functools import lru_cache
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.personalization import embeddings as emb_module
from backend.personalization.segment_views import (
    get_affinities,
    get_loyalty_principal,
    get_value_level,
    summarize_segment,
)
from backend.personalization.travel_prediction import predict_next_trip
from backend.storage.customers import load_customers_df
from backend.storage.embeddings import load_embeddings
from backend.storage.events import load_events
from backend.storage.segments import load_segments as load_segments_data
from backend.storage.upsells import load_upsells

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


def _load_data() -> tuple[dict, dict, pd.DataFrame]:
    """Carga embeddings, segmentos y reservas de clientes."""
    return load_embeddings(), load_segments_data(), load_customers_df()


@lru_cache(maxsize=1)
def _load_events_catalog() -> dict[str, list[dict[str, str]]]:
    """Carga y normaliza el catálogo de eventos desde data/raw."""
    try:
        raw_events = load_events()
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo cargar data/raw/city_events.json: %s", exc)
        return {}

    normalized: dict[str, list[dict[str, str]]] = {}
    for city, events in raw_events.items():
        city_key = str(city).strip().upper()
        if not city_key or not isinstance(events, list):
            continue

        valid_events: list[dict[str, str]] = []
        for event in events:
            if not isinstance(event, dict):
                continue

            name = str(event.get("name", "")).strip()
            event_date = str(event.get("date", "")).strip()
            event_type = str(event.get("type", "")).strip()
            if not name or not event_date:
                continue

            valid_events.append(
                {
                    "name": name,
                    "date": event_date,
                    "type": event_type,
                }
            )

        if valid_events:
            normalized[city_key] = valid_events

    return normalized


def _project_event_date(event_date: str, target_date: datetime) -> tuple[datetime, int] | None:
    """Reubica un evento recurrente al año más cercano a la fecha objetivo."""
    try:
        base_date = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None

    candidates: list[tuple[int, datetime]] = []
    for year in (target_date.year - 1, target_date.year, target_date.year + 1):
        try:
            occurrence = base_date.replace(year=year)
        except ValueError:
            continue
        distance = abs((occurrence - target_date).days)
        candidates.append((distance, occurrence))

    if not candidates:
        return None

    distance, occurrence = min(candidates, key=lambda item: item[0])
    return occurrence, distance


def _get_events(city: str, target_date: datetime) -> list[dict[str, Any]]:
    """Obtiene eventos de la ciudad cercanos a la fecha prevista de viaje."""
    city_key = str(city).strip().upper()
    eventos = _load_events_catalog().get(city_key, [])
    coincidencias: list[dict[str, Any]] = []
    for ev in eventos:
        projected = _project_event_date(ev["date"], target_date)
        if projected is None:
            continue
        occurrence, distance = projected
        if distance > 45:
            continue
        coincidencias.append(
            {
                **ev,
                "date": occurrence.strftime("%Y-%m-%d"),
                "days_from_checkin": distance,
            }
        )
    coincidencias.sort(
        key=lambda event: (
            event.get("days_from_checkin", 9999),
            event.get("name", ""),
        )
    )
    return coincidencias


def _get_embedding_preferences(embedding: dict[str, float]) -> list[str]:
    """Traduce las dimensiones del embedding a preferencias legibles."""
    preferencias = []
    if embedding.get("HERITAGE", 0) > 0.6:
        preferencias.append("patrimonio histórico y cultural")
    if embedding.get("GASTRONOMY", 0) > 0.6:
        preferencias.append("gastronomía local")
    if embedding.get("BEACH", 0) > 0.5:
        preferencias.append("playa y actividades al aire libre")
    if embedding.get("MOUNTAIN", 0) > 0.5:
        preferencias.append("montaña y naturaleza")
    if embedding.get("PRICE_LEVEL", 0) > 0.7:
        preferencias.append("experiencias premium y exclusivas")
    if embedding.get("STARS_NORM", 0) > 0.7:
        preferencias.append("alojamientos de alta categoría")
    if embedding.get("TEMP_NORM", 0) > 0.7:
        preferencias.append("destinos cálidos y soleados")
    if not preferencias:
        preferencias.append("diversidad de experiencias")
    return preferencias


@lru_cache(maxsize=1)
def _load_upsell_catalog() -> dict[str, dict[str, str]]:
    """Carga y normaliza el catalogo de upsells desde data/raw."""
    try:
        raw_upsells = load_upsells()
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo cargar data/raw/upsell_catalog.json: %s", exc)
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for code, offer in raw_upsells.items():
        if not isinstance(offer, dict):
            continue

        title = str(offer.get("title", "")).strip()
        description = str(offer.get("description", "")).strip()
        price_label = str(offer.get("price_label", "")).strip()
        if not title or not price_label:
            continue

        normalized[str(code).strip()] = {
            "code": str(code).strip(),
            "title": title,
            "description": description,
            "price_label": price_label,
        }

    return normalized


def _materialize_upsells(offer_codes: list[str]) -> list[dict[str, str]]:
    """Convierte codigos de oferta en upsells estructurados y deduplicados."""
    catalog = _load_upsell_catalog()
    recommendations: list[dict[str, str]] = []
    seen: set[str] = set()

    for code in offer_codes:
        if code in seen:
            continue
        offer = catalog.get(code)
        if not offer:
            continue
        recommendations.append(dict(offer))
        seen.add(code)

    return recommendations


def _upsell_recommendations(segment: dict) -> list[dict[str, str]]:
    """Genera recomendaciones de upsell a partir del segmento y un catalogo estructurado."""
    value_level = get_value_level(segment)
    affinities = set(get_affinities(segment))
    loyalty = get_loyalty_principal(segment)

    if value_level in {"premium", "lujo"}:
        offer_codes = [
            "suite_upgrade",
            "spa_access_premium",
        ]
    elif value_level == "confort":
        offer_codes = [
            "breakfast_buffet",
            "covered_parking",
        ]
    else:  # Esencial o fallback
        offer_codes = [
            "standard_room_upgrade",
            "late_checkout_light",
        ]

    if "cultural" in affinities:
        offer_codes.append("museum_pass")
    if "gastronomico" in affinities:
        offer_codes.append("local_tasting")
    if "playero" in affinities or "clima_calido" in affinities or "mediterraneo" in affinities:
        offer_codes.append("terrace_pool_pack")
    if "montana" in affinities:
        offer_codes.append("nature_excursion")
    if loyalty in {"repetidor", "fiel_pocos_hoteles"}:
        offer_codes.append("welcome_pack")

    if value_level in {"premium", "lujo"}:
        offer_codes.extend(
            [
                "late_checkout_premium",
                "chef_experience",
                "premium_minibar",
            ]
        )
    elif value_level == "confort":
        offer_codes.extend(
            [
                "city_guided_tour",
                "restaurant_tasting_menu",
                "late_checkout_light",
            ]
        )
    else:
        offer_codes.extend(
            [
                "breakfast_buffet",
                "covered_parking",
                "welcome_pack",
            ]
        )

    return _materialize_upsells(offer_codes)


# ── Generadores de campañas ──────────────────────────────────────────────

def generate_pre_arrival(
    guest_id: str,
    embeddings: dict,
    segments: dict,
    customers: pd.DataFrame,
    *,
    timing_mode: str | None = None,
    send_offset_days: int | None = None,
) -> dict | None:
    """Genera los datos pre-arrival para un huésped concreto."""
    seg = segments.get(str(guest_id))
    if seg is None:
        logger.warning("No se ha encontrado segmento para el huésped %s", guest_id)
        return None

    user_rows = customers[customers["GUEST_ID"] == str(guest_id)]
    if user_rows.empty:
        return None

    # Obtener recomendación
    recs = emb_module.recommend_hotel(str(guest_id), embeddings, top_n=1, segment=seg)
    if not recs:
        return None

    rec_hotel_id, similarity = recs[0]
    hotel = embeddings["hotel_info"].get(rec_hotel_id, {})
    user_emb = embeddings["user_embeddings"].get(str(guest_id), {})

    # Ventana de viaje
    timing = predict_next_trip(
        user_rows,
        mode=timing_mode,
        send_offset_days=send_offset_days,
        today=datetime.now(),
    )
    send_date = timing["send_date"]
    checkin_suggested = timing["predicted_checkin_date"]
    stay_nights = timing["stay_nights"]
    checkin_dt = datetime.strptime(checkin_suggested, "%Y-%m-%d")
    season = SEASON_MAP.get(checkin_dt.month, "primavera")

    # Eventos
    events = _get_events(hotel.get("CITY_NAME", ""), checkin_dt)

    # Preferencias
    preferences = _get_embedding_preferences(user_emb)

    return {
        "campaign_type": "pre_arrival",
        "guest_id": str(guest_id),
        "segment": seg,
        "segment_overview": summarize_segment(seg),
        "recommended_hotel": {
            "id": rec_hotel_id,
            "name": hotel.get("HOTEL_NAME", ""),
            "city": hotel.get("CITY_NAME", ""),
            "country": hotel.get("COUNTRY_ID", ""),
            "stars": hotel.get("STARS", 4),
            "brand": hotel.get("BRAND", "EUROSTARS"),
            "similarity_score": round(similarity, 4),
            "recommendation_score": round(similarity, 4),
        },
        "send_date": send_date,
        "checkin_suggested": checkin_suggested,
        "stay_nights": stay_nights,
        "season": season,
        "events": events,
        "preferences": preferences,
        "avg_length_stay": float(user_rows["AVG_LENGTH_STAY"].iloc[0]),
        "avg_booking_leadtime": float(user_rows["AVG_BOOKING_LEADTIME"].iloc[0]),
        "travel_prediction": timing,
    }


def generate_checkin_report(guest_id: str, embeddings: dict, segments: dict,
                            customers: pd.DataFrame) -> dict | None:
    """Genera el informe de check-in de recepción para un huésped."""
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
    upsells = _upsell_recommendations(seg)

    # Hoteles visitados
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
        "segment_overview": summarize_segment(seg),
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
    """Genera los datos de campaña post-stay."""
    seg = segments.get(str(guest_id))
    if seg is None:
        return None

    user_rows = customers[customers["GUEST_ID"] == str(guest_id)]
    if user_rows.empty:
        return None

    # Última estancia
    last = user_rows.sort_values("CHECKOUT_DATE").iloc[-1]
    last_hotel = embeddings["hotel_info"].get(str(last["HOTEL_ID"]), {})

    # Siguiente recomendación
    recs = emb_module.recommend_hotel(str(guest_id), embeddings, top_n=1, segment=seg)
    next_hotel = None
    if recs:
        hid, sim = recs[0]
        next_hotel = {
            "id": hid,
            **embeddings["hotel_info"].get(hid, {}),
            "similarity_score": round(sim, 4),
            "recommendation_score": round(sim, 4),
        }

    send_date = (last["CHECKOUT_DATE"] + timedelta(days=7)).strftime("%Y-%m-%d")

    return {
        "campaign_type": "post_stay",
        "guest_id": str(guest_id),
        "segment": seg,
        "segment_overview": summarize_segment(seg),
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


# ── Generadores batch ────────────────────────────────────────────────────

def generate_all(
    moment: str,
    guest_id: str | None = None,
    *,
    timing_mode: str | None = None,
    send_offset_days: int | None = None,
) -> list[dict]:
    """Genera datos de campaña para todos los usuarios o para uno concreto."""
    embeddings, segments, customers = _load_data()

    generator_names = ["pre_arrival", "checkin_report", "post_stay"]
    if moment == "pre_arrival":
        def gen_fn(uid: str, emb: dict, segs: dict, cust: pd.DataFrame) -> dict | None:
            return generate_pre_arrival(
                uid,
                emb,
                segs,
                cust,
                timing_mode=timing_mode,
                send_offset_days=send_offset_days,
            )
    else:
        generators = {
            "checkin_report": generate_checkin_report,
            "post_stay": generate_post_stay,
        }
        gen_fn = generators.get(moment)

    if gen_fn is None:
        raise ValueError(f"Momento desconocido: {moment}. Elige entre: {generator_names}")

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

    logger.info("Se han generado %d campañas de tipo %s", len(results), moment)
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
