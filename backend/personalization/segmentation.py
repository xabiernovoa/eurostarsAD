#!/usr/bin/env python3
"""
segment_users.py — Fase 2: segmentación de usuarios

Calcula etiquetas útiles y simples para cada usuario a partir de:
  1. Afinidades de destino
  2. Nivel de valor percibido
  3. Comportamiento de reserva
  4. Fidelidad / patrón de exploración
  5. Demografía básica
"""

from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.customers import load_customers_df
from backend.storage.embeddings import load_embeddings
from backend.storage.segments import save_segments as save_segments_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("segment_users")

# ── Mapa de edad ─────────────────────────────────────────────────────────
AGE_SEGMENT_MAP = {
    "19-25": "JOVEN",
    "26-35": "JOVEN",
    "36-45": "ADULTO",
    "46-65": "ADULTO",
    ">65": "SENIOR",
}

DESTINATION_TAG_RULES = [
    ("playero", "BEACH", 0.55),
    ("montana", "MOUNTAIN", 0.55),
    ("cultural", "HERITAGE", 0.60),
    ("gastronomico", "GASTRONOMY", 0.60),
    ("clima_calido", "TEMP_NORM", 0.65),
]

CLIMATE_TAG_RULES = [
    ("mediterraneo", "CLIMATE_MEDITERRANEAN", 0.45),
    ("continental", "CLIMATE_CONTINENTAL", 0.45),
]


def _age_segment(age_range: str) -> str:
    return AGE_SEGMENT_MAP.get(age_range, "ADULTO")


def _build_user_metrics(
    customers: pd.DataFrame,
    hotel_info: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Agrega métricas operativas por usuario para alimentar las etiquetas."""
    metrics: dict[str, dict[str, Any]] = {}

    for guest_id, group in customers.groupby("GUEST_ID", sort=False):
        ordered = group.sort_values(["CHECKIN_DATE", "CHECKOUT_DATE"])
        hotel_ids = [str(hid) for hid in ordered["HOTEL_ID"].tolist()]
        reservation_count = int(ordered["RESERVATION_ID"].nunique())

        hotel_counts = Counter(hotel_ids)
        city_counts: Counter[str] = Counter()
        country_counts: Counter[str] = Counter()
        brand_counts: Counter[str] = Counter()
        hotel_stars: list[float] = []

        for hotel_id in hotel_ids:
            info = hotel_info.get(hotel_id, {})
            city = str(info.get("CITY_NAME", "")).strip()
            country = str(info.get("COUNTRY_ID", "")).strip()
            brand = str(info.get("BRAND", "")).strip()
            stars = info.get("STARS")

            if city:
                city_counts[city] += 1
            if country:
                country_counts[country] += 1
            if brand:
                brand_counts[brand] += 1
            if stars is not None:
                try:
                    hotel_stars.append(float(stars))
                except (TypeError, ValueError):
                    pass

        top_hotel_share = max(hotel_counts.values()) / max(len(hotel_ids), 1)
        top_brand_share = max(brand_counts.values()) / max(len(hotel_ids), 1) if brand_counts else 0.0
        avg_stars = sum(hotel_stars) / len(hotel_stars) if hotel_stars else 4.0

        def _safe_first_int(column: str, default: int) -> int:
            series = pd.to_numeric(ordered[column], errors="coerce").dropna()
            return int(series.iloc[0]) if not series.empty else default

        metrics[str(guest_id)] = {
            "reservations": reservation_count,
            "confirmed_reservations": _safe_first_int("CONFIRMED_RESERVATIONS", reservation_count),
            "last_2_years_stays": _safe_first_int("LAST_2_YEARS_STAYS", reservation_count),
            "distinct_hotels": int(ordered["HOTEL_ID"].nunique()),
            "distinct_cities": len(city_counts),
            "distinct_countries": len(country_counts),
            "distinct_brands": len(brand_counts),
            "top_hotel_share": round(top_hotel_share, 4),
            "top_brand_share": round(top_brand_share, 4),
            "preferred_brand": brand_counts.most_common(1)[0][0] if brand_counts else "",
            "preferred_country": country_counts.most_common(1)[0][0] if country_counts else "",
            "visited_hotel_ids": sorted(set(hotel_ids)),
            "visited_cities": sorted(city_counts.keys()),
            "visited_countries": sorted(country_counts.keys()),
            "visited_brands": sorted(brand_counts.keys()),
            "avg_adr": float(pd.to_numeric(ordered["CONFIRMED_RESERVATIONS_ADR"], errors="coerce").mean()),
            "avg_leadtime": float(pd.to_numeric(ordered["AVG_BOOKING_LEADTIME"], errors="coerce").mean()),
            "avg_stay": float(pd.to_numeric(ordered["AVG_LENGTH_STAY"], errors="coerce").mean()),
            "avg_stars": round(avg_stars, 2),
        }

    return metrics


def _destination_affinities(emb: dict[str, float]) -> list[str]:
    """Selecciona hasta 3 afinidades claras de destino a partir del embedding."""
    scored: list[tuple[str, float]] = []

    for tag, feature, threshold in DESTINATION_TAG_RULES:
        value = float(emb.get(feature, 0.0))
        if value >= threshold:
            scored.append((tag, value))

    climate_candidates = []
    for tag, feature, threshold in CLIMATE_TAG_RULES:
        value = float(emb.get(feature, 0.0))
        if value >= threshold:
            climate_candidates.append((tag, value))
    if climate_candidates:
        scored.append(max(climate_candidates, key=lambda item: item[1]))

    if not scored:
        fallback_features = [
            ("cultural", float(emb.get("HERITAGE", 0.0))),
            ("gastronomico", float(emb.get("GASTRONOMY", 0.0))),
            ("clima_calido", float(emb.get("TEMP_NORM", 0.0))),
            ("playero", float(emb.get("BEACH", 0.0))),
            ("montana", float(emb.get("MOUNTAIN", 0.0))),
        ]
        fallback_features.sort(key=lambda item: item[1], reverse=True)
        if fallback_features and fallback_features[0][1] > 0.25:
            scored.append(fallback_features[0])

    scored.sort(key=lambda item: item[1], reverse=True)
    tags: list[str] = []
    for tag, _value in scored:
        if tag not in tags:
            tags.append(tag)
        if len(tags) >= 3:
            break
    return tags


def _compute_value_levels(user_metrics: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Combina ADR y estrellas medias para producir 4 niveles de valor simples."""
    table = pd.DataFrame.from_dict(user_metrics, orient="index")
    adr_rank = table["avg_adr"].rank(pct=True, method="average")
    stars_rank = table["avg_stars"].rank(pct=True, method="average")
    value_score = 0.7 * adr_rank + 0.3 * stars_rank

    logger.info(
        "Modelo de valor recalibrado sobre %d usuarios (ADR medio %.2f, estrellas medias %.2f)",
        len(table),
        table["avg_adr"].mean(),
        table["avg_stars"].mean(),
    )

    value_levels: dict[str, str] = {}
    for uid, score in value_score.items():
        if score < 0.25:
            level = "esencial"
        elif score < 0.55:
            level = "confort"
        elif score < 0.82:
            level = "premium"
        else:
            level = "lujo"
        value_levels[str(uid)] = level

    return value_levels


def _booking_behavior(metrics: dict[str, Any]) -> dict[str, str]:
    """Resume el comportamiento de reserva en tres etiquetas simples."""
    leadtime = float(metrics.get("avg_leadtime", 0.0))
    stay = float(metrics.get("avg_stay", 0.0))
    last_2_years_stays = int(metrics.get("last_2_years_stays", 0))
    confirmed_reservations = int(metrics.get("confirmed_reservations", metrics.get("reservations", 0)))

    if leadtime <= 7:
        advance_tag = "ultimo_minuto"
    elif leadtime >= 30:
        advance_tag = "planificador"
    else:
        advance_tag = "estandar"

    if stay <= 2:
        stay_tag = "escapada_corta"
    elif stay >= 4:
        stay_tag = "estancia_larga"
    else:
        stay_tag = "estancia_media"

    if last_2_years_stays >= 3 or confirmed_reservations >= 4:
        frequency_tag = "frecuente"
    elif last_2_years_stays >= 2 or confirmed_reservations >= 2:
        frequency_tag = "regular"
    else:
        frequency_tag = "ocasional"

    return {
        "antelacion": advance_tag,
        "duracion": stay_tag,
        "frecuencia": frequency_tag,
    }


def _loyalty_tags(metrics: dict[str, Any]) -> dict[str, Any]:
    """Clasifica la fidelidad con una etiqueta principal y secundarias opcionales."""
    reservations = int(metrics.get("reservations", 0))
    distinct_hotels = int(metrics.get("distinct_hotels", 0))
    distinct_cities = int(metrics.get("distinct_cities", 0))
    distinct_countries = int(metrics.get("distinct_countries", 0))
    distinct_brands = int(metrics.get("distinct_brands", 0))
    top_hotel_share = float(metrics.get("top_hotel_share", 0.0))
    top_brand_share = float(metrics.get("top_brand_share", 0.0))

    if reservations <= 1:
        principal = "explorador"
    elif distinct_hotels == 1:
        principal = "repetidor"
    elif distinct_countries >= 2 or distinct_cities >= 3:
        principal = "multidestino"
    elif distinct_hotels <= 2 and top_hotel_share >= 0.70:
        principal = "fiel_pocos_hoteles"
    else:
        principal = "explorador"

    secondary: list[str] = []
    if principal != "multidestino" and (distinct_countries >= 2 or distinct_cities >= 3):
        secondary.append("multidestino")
    if principal != "explorador" and distinct_hotels == reservations and reservations > 1:
        secondary.append("explorador")
    if principal != "repetidor" and distinct_hotels == 1 and reservations > 1:
        secondary.append("repetidor")
    if (
        principal != "fiel_pocos_hoteles"
        and reservations > 1
        and distinct_hotels <= 2
        and distinct_brands <= 2
        and top_brand_share >= 0.70
    ):
        secondary.append("fiel_pocos_hoteles")

    return {
        "principal": principal,
        "secundarias": secondary[:2],
    }


def _demographic_tags(age_segment: str, user_info: dict[str, Any]) -> dict[str, str]:
    """Genera un bloque demográfico simple para consumo del copy y la UI."""
    return {
        "edad": age_segment.lower(),
        "genero": str(user_info.get("GENDER", "")).strip(),
        "pais": str(user_info.get("COUNTRY", "")).strip(),
    }


# ── Flujo principal ──────────────────────────────────────────────────────

def segment(
    embeddings_path: str | None = None,
    customers_path: str | None = None,
) -> dict[str, dict]:
    """Construye segmentos y etiquetas enriquecidas para todos los usuarios."""
    emb_data = load_embeddings(embeddings_path)
    customers = load_customers_df(customers_path)

    user_metrics = _build_user_metrics(customers, emb_data["hotel_info"])
    value_levels = _compute_value_levels(user_metrics)

    segments: dict[str, dict] = {}

    for user_info in emb_data["user_info"]:
        uid = str(user_info["id"])
        age_range = str(user_info.get("AGE", "36-45"))
        age_segment = _age_segment(age_range)
        emb = emb_data["user_embeddings"].get(uid, {})
        metrics = user_metrics.get(uid, {})

        destination_tags = _destination_affinities(emb)
        value_level = value_levels.get(uid, "confort")
        booking_behavior = _booking_behavior(metrics)
        loyalty = _loyalty_tags(metrics)
        tags = {
            "afinidades_destino": destination_tags,
            "nivel_valor": value_level,
            "comportamiento_reserva": booking_behavior,
            "fidelidad": loyalty,
            "demografia": _demographic_tags(age_segment, user_info),
        }

        segments[uid] = {
            "guest_id": uid,
            "country": user_info.get("COUNTRY", ""),
            "gender": user_info.get("GENDER", ""),
            "age_range": age_range,
            "avg_score": user_info.get("AVG_SCORE", 0),
            "tags": tags,
            "metrics": {
                "avg_adr": round(float(metrics.get("avg_adr", 0.0)), 2),
                "avg_stars": round(float(metrics.get("avg_stars", 0.0)), 2),
                "avg_leadtime": round(float(metrics.get("avg_leadtime", 0.0)), 1),
                "avg_stay": round(float(metrics.get("avg_stay", 0.0)), 1),
                "reservations": int(metrics.get("reservations", 0)),
                "distinct_hotels": int(metrics.get("distinct_hotels", 0)),
                "distinct_cities": int(metrics.get("distinct_cities", 0)),
                "distinct_countries": int(metrics.get("distinct_countries", 0)),
            },
        }

    logger.info("Segmentados %d usuarios con etiquetas enriquecidas", len(segments))
    return segments


def save(segments: dict, path: str | None = None) -> str:
    path = save_segments_data(segments, path)
    logger.info("Segmentos guardados en %s", path)
    return str(path)


def main():
    segs = segment()
    save(segs)

    from collections import Counter as C

    age_dist = C(s["tags"]["demografia"]["edad"] for s in segs.values())
    affinity_dist = C(tag for s in segs.values() for tag in s["tags"]["afinidades_destino"])
    value_dist = C(s["tags"]["nivel_valor"] for s in segs.values())
    loyalty_dist = C(s["tags"]["fidelidad"]["principal"] for s in segs.values())
    logger.info("Distribución de edad: %s", dict(age_dist))
    logger.info("Distribución de afinidades: %s", dict(affinity_dist))
    logger.info("Distribución de nivel_valor: %s", dict(value_dist))
    logger.info("Distribución de fidelidad principal: %s", dict(loyalty_dist))


if __name__ == "__main__":
    main()
