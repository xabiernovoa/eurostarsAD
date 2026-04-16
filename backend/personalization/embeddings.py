#!/usr/bin/env python3
"""
build_embeddings.py — Fase 1: generador de embeddings de hotel y usuario

Convierte las características de los hoteles en vectores de 11 dimensiones y
calcula embeddings de usuario como media ponderada por AVG_SCORE de los hoteles
visitados. La salida se guarda en embeddings.json.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from backend.storage.customers import load_customers_df
from backend.storage.embeddings import save_embeddings as save_embeddings_data
from backend.storage.hotels import load_hotels_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("build_embeddings")

# ── Especificación de variables ──────────────────────────────────────────
FEATURE_COLS = [
    "STARS_NORM",
    "TEMP_NORM",
    "RAIN_RISK_NUM",
    "BEACH",
    "MOUNTAIN",
    "HERITAGE",
    "PRICE_LEVEL",
    "GASTRONOMY",
    "CLIMATE_ATLANTIC",
    "CLIMATE_CONTINENTAL",
    "CLIMATE_MEDITERRANEAN",
]

FEATURE_LABELS = {
    "STARS_NORM": "Estrellas",
    "TEMP_NORM": "Temperatura",
    "RAIN_RISK_NUM": "Riesgo de lluvia",
    "BEACH": "Playa",
    "MOUNTAIN": "Montaña",
    "HERITAGE": "Patrimonio histórico",
    "PRICE_LEVEL": "Nivel de precio",
    "GASTRONOMY": "Gastronomía",
    "CLIMATE_ATLANTIC": "Clima atlántico",
    "CLIMATE_CONTINENTAL": "Clima continental",
    "CLIMATE_MEDITERRANEAN": "Clima mediterráneo",
}

ORDINAL_MAP = {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.0}
YESNO_MAP = {"NO": 0.0, "YES": 1.0}

AFFINITY_TO_FEATURE = {
    "playero": "BEACH",
    "montana": "MOUNTAIN",
    "cultural": "HERITAGE",
    "gastronomico": "GASTRONOMY",
    "clima_calido": "TEMP_NORM",
    "mediterraneo": "CLIMATE_MEDITERRANEAN",
    "continental": "CLIMATE_CONTINENTAL",
}

VALUE_LEVEL_TARGETS = {
    "esencial": 0.20,
    "confort": 0.45,
    "premium": 0.72,
    "lujo": 0.95,
}

# ── Utilidades ───────────────────────────────────────────────────────────

def _load_hotels(path: str | None = None) -> pd.DataFrame:
    df = load_hotels_df(path)
    logger.info("Cargados %d hoteles desde %s", len(df), path or "data/raw/hotel_data.csv")
    return df


def _load_customers(path: str | None = None) -> pd.DataFrame:
    df = load_customers_df(path)
    logger.info(
        "Cargadas %d filas de reservas desde %s",
        len(df),
        path or "data/raw/customer_data.csv",
    )
    return df


def _build_hotel_vectors(hotels: pd.DataFrame) -> pd.DataFrame:
    """Crea vectores de variables normalizadas para cada hotel."""
    h = hotels.copy()

    # Normalización de estrellas (min-max)
    stars = h["STARS"].astype(float)
    h["STARS_NORM"] = (stars - stars.min()) / (stars.max() - stars.min())

    # Normalización de temperatura (min-max)
    temp = h["CITY_AVG_TEMPERATURE"].astype(float)
    h["TEMP_NORM"] = (temp - temp.min()) / (temp.max() - temp.min())

    # Mapeos ordinales
    h["RAIN_RISK_NUM"] = h["CITY_RAIN_RISK"].map(ORDINAL_MAP)
    h["HERITAGE"] = h["CITY_HISTORICAL_HERITAGE"].map(ORDINAL_MAP)
    h["PRICE_LEVEL"] = h["CITY_PRICE_LEVEL"].map(ORDINAL_MAP)
    h["GASTRONOMY"] = h["CITY_GASTRONOMY"].map(ORDINAL_MAP)

    # Indicadores binarios
    h["BEACH"] = h["CITY_BEACH_FLAG"].map(YESNO_MAP)
    h["MOUNTAIN"] = h["CITY_MOUNTAIN_FLAG"].map(YESNO_MAP)

    # Clima one-hot
    h["CLIMATE_ATLANTIC"] = (h["CITY_CLIMATE"] == "ATLANTIC").astype(float)
    h["CLIMATE_CONTINENTAL"] = (h["CITY_CLIMATE"] == "CONTINENTAL").astype(float)
    h["CLIMATE_MEDITERRANEAN"] = (h["CITY_CLIMATE"] == "MEDITERRANEAN").astype(float)

    return h


def _compute_user_embedding(
    user_hotels: list[str],
    user_scores: list[float],
    hotel_vectors: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Calcula la media ponderada de vectores de hotel por AVG_SCORE."""
    weights = np.array(user_scores, dtype=float)
    if weights.sum() == 0:
        weights = np.ones_like(weights)
    weights = weights / weights.sum()

    embedding = {col: 0.0 for col in FEATURE_COLS}
    for hotel_id, w in zip(user_hotels, weights):
        vec = hotel_vectors.get(hotel_id)
        if vec is None:
            continue
        for col in FEATURE_COLS:
            embedding[col] += vec[col] * w

    return {k: round(v, 6) for k, v in embedding.items()}


def _normalize_hotel_id(raw_hotel_id: object, hotel_info: dict[str, dict]) -> str:
    """Normaliza IDs de hotel preservando ceros a la izquierda si existen."""
    hotel_id = str(raw_hotel_id).strip()
    if hotel_id in hotel_info:
        return hotel_id

    if hotel_id.isdigit():
        for width in (3, 4):
            padded = hotel_id.zfill(width)
            if padded in hotel_info:
                return padded

    return hotel_id


def _collect_visited_context(user_id: str, embeddings_data: dict) -> dict[str, object]:
    """Recupera el contexto histórico del usuario a partir de los hoteles visitados."""
    visited_hotels: set[str] = set()
    hotel_visit_counts: dict[str, int] = {}
    hotel_info = embeddings_data.get("hotel_info", {})
    for user_info in embeddings_data.get("user_info", []):
        if str(user_info.get("id")) == str(user_id):
            visited_hotels = {
                _normalize_hotel_id(hotel_id, hotel_info)
                for hotel_id in user_info.get("HOTELS_VISITED", [])
            }
            raw_counts = user_info.get("HOTEL_VISIT_COUNTS", {}) or {}
            if isinstance(raw_counts, dict):
                hotel_visit_counts = {
                    _normalize_hotel_id(hotel_id, hotel_info): int(count)
                    for hotel_id, count in raw_counts.items()
                    if str(hotel_id).strip()
                }
            break

    visited_cities: set[str] = set()
    visited_countries: set[str] = set()
    visited_brands: set[str] = set()
    for hotel_id in visited_hotels:
        info = hotel_info.get(hotel_id, {})
        city = str(info.get("CITY_NAME", "")).strip()
        country = str(info.get("COUNTRY_ID", "")).strip()
        brand = str(info.get("BRAND", "")).strip()
        if city:
            visited_cities.add(city)
        if country:
            visited_countries.add(country)
        if brand:
            visited_brands.add(brand)

    favorite_hotels: set[str] = set()
    if hotel_visit_counts:
        max_visits = max(hotel_visit_counts.values())
        if max_visits > 1:
            favorite_hotels = {
                hotel_id for hotel_id, count in hotel_visit_counts.items() if count == max_visits
            }

    return {
        "hotels": visited_hotels,
        "cities": visited_cities,
        "countries": visited_countries,
        "brands": visited_brands,
        "hotel_visit_counts": hotel_visit_counts,
        "favorite_hotels": favorite_hotels,
    }


def _loyalty_labels(segment: dict | None) -> set[str]:
    """Devuelve todas las etiquetas de fidelidad disponibles para el segmento."""
    if not isinstance(segment, dict):
        return set()

    tags = segment.get("tags", {})
    if not isinstance(tags, dict):
        return set()

    loyalty = tags.get("fidelidad", {})
    if not isinstance(loyalty, dict):
        return set()

    labels: set[str] = set()
    principal = str(loyalty.get("principal", "")).strip()
    if principal:
        labels.add(principal)

    secondary = loyalty.get("secundarias", [])
    if isinstance(secondary, list):
        labels.update(str(label).strip() for label in secondary if str(label).strip())

    return labels


def _allow_visited_hotels(segment: dict | None) -> bool:
    """Permite recomendar hoteles ya visitados solo a perfiles con fidelidad clara."""
    return bool(_loyalty_labels(segment) & {"repetidor", "fiel_pocos_hoteles"})


def _hotel_level_score(hotel_vector: dict[str, float]) -> float:
    """Resume el nivel del hotel combinando estrellas y nivel de precio."""
    stars_score = float(hotel_vector.get("STARS_NORM", 0.0))
    price_score = float(hotel_vector.get("PRICE_LEVEL", 0.0))
    return min(max(0.6 * stars_score + 0.4 * price_score, 0.0), 1.0)


def _tag_rerank_score(
    hotel_id: str,
    hotel_vector: dict[str, float],
    embeddings_data: dict,
    segment: dict | None,
    visited_context: dict[str, object],
) -> float:
    """Calcula un score 0-1 a partir de etiquetas para reordenar recomendaciones."""
    if not segment:
        return 0.0

    tags = segment.get("tags", {})
    if not tags:
        return 0.0

    affinities = tags.get("afinidades_destino", [])
    affinity_values = [
        float(hotel_vector.get(AFFINITY_TO_FEATURE[tag], 0.0))
        for tag in affinities
        if tag in AFFINITY_TO_FEATURE
    ]
    affinity_score = sum(affinity_values) / len(affinity_values) if affinity_values else 0.5

    value_level = str(tags.get("nivel_valor", "")).strip().lower()
    value_target = VALUE_LEVEL_TARGETS.get(value_level)
    if value_target is None:
        value_score = 0.5
    else:
        value_score = max(0.0, 1.0 - abs(_hotel_level_score(hotel_vector) - value_target) / 0.8)

    hotel_info = embeddings_data.get("hotel_info", {}).get(hotel_id, {})
    hotel_brand = str(hotel_info.get("BRAND", "")).strip()
    hotel_country = str(hotel_info.get("COUNTRY_ID", "")).strip()
    hotel_city = str(hotel_info.get("CITY_NAME", "")).strip()

    loyalty_labels = _loyalty_labels(segment)
    visited_hotels = visited_context.get("hotels", set())
    favorite_hotels = visited_context.get("favorite_hotels", set())
    if not isinstance(visited_hotels, set):
        visited_hotels = set()
    if not isinstance(favorite_hotels, set):
        favorite_hotels = set()

    if not any(visited_context.values()):
        loyalty_score = 0.5
    elif loyalty_labels & {"repetidor", "fiel_pocos_hoteles"}:
        hotel_match = 1.0 if hotel_id in visited_hotels else 0.0
        favorite_hotel_bonus = 1.0 if hotel_id in favorite_hotels else 0.0
        brand_match = 1.0 if hotel_brand and hotel_brand in visited_context["brands"] else 0.0
        country_match = 1.0 if hotel_country and hotel_country in visited_context["countries"] else 0.0
        city_match = 1.0 if hotel_city and hotel_city in visited_context["cities"] else 0.0
        loyalty_score = min(
            1.0,
            0.45 * hotel_match
            + 0.25 * brand_match
            + 0.15 * country_match
            + 0.05 * city_match
            + 0.10 * favorite_hotel_bonus,
        )
    else:
        brand_novelty = 1.0 if hotel_brand and hotel_brand not in visited_context["brands"] else 0.0
        country_novelty = 1.0 if hotel_country and hotel_country not in visited_context["countries"] else 0.0
        city_novelty = 1.0 if hotel_city and hotel_city not in visited_context["cities"] else 0.0
        loyalty_score = 0.20 * brand_novelty + 0.45 * country_novelty + 0.35 * city_novelty

    behavior = tags.get("comportamiento_reserva", {}) or {}
    duration_tag = str(behavior.get("duracion", "")).strip()
    advance_tag = str(behavior.get("antelacion", "")).strip()

    if duration_tag == "escapada_corta":
        duration_score = (float(hotel_vector.get("HERITAGE", 0.0)) + float(hotel_vector.get("GASTRONOMY", 0.0))) / 2
    elif duration_tag == "estancia_larga":
        duration_score = (
            float(hotel_vector.get("BEACH", 0.0))
            + float(hotel_vector.get("MOUNTAIN", 0.0))
            + float(hotel_vector.get("TEMP_NORM", 0.0))
        ) / 3
    else:
        duration_score = (
            float(hotel_vector.get("HERITAGE", 0.0))
            + float(hotel_vector.get("GASTRONOMY", 0.0))
            + float(hotel_vector.get("TEMP_NORM", 0.0))
        ) / 3

    if not any(visited_context.values()):
        proximity_score = 0.5
    else:
        country_match = 1.0 if hotel_country and hotel_country in visited_context["countries"] else 0.0
        brand_match = 1.0 if hotel_brand and hotel_brand in visited_context["brands"] else 0.0
        proximity_score = 0.6 * country_match + 0.4 * brand_match

    if advance_tag == "ultimo_minuto":
        behavior_score = 0.6 * duration_score + 0.4 * proximity_score
    elif advance_tag == "planificador":
        behavior_score = 0.5 * duration_score + 0.5 * _hotel_level_score(hotel_vector)
    else:
        behavior_score = duration_score

    return min(
        max(
            0.45 * affinity_score
            + 0.30 * value_score
            + 0.15 * loyalty_score
            + 0.10 * behavior_score,
            0.0,
        ),
        1.0,
    )


# ── Flujo principal ──────────────────────────────────────────────────────

def build(hotel_path: str | None = None, customer_path: str | None = None) -> dict:
    """Construye todos los embeddings y devuelve la estructura completa."""
    hotels = _load_hotels(hotel_path)
    customers = _load_customers(customer_path)

    # Vectores de hotel
    h = _build_hotel_vectors(hotels)
    hotel_embeddings: dict[str, dict[str, float]] = {}
    hotel_info: dict[str, dict] = {}

    for _, row in h.iterrows():
        hid = str(row["ID"])
        hotel_embeddings[hid] = {col: round(float(row[col]), 6) for col in FEATURE_COLS}
        hotel_info[hid] = {
            "HOTEL_NAME": row["HOTEL_NAME"],
            "CITY_NAME": row["CITY_NAME"],
            "BRAND": row["BRAND"],
            "STARS": int(row["STARS"]),
            "COUNTRY_ID": row["COUNTRY_ID"],
        }

    logger.info("Construidos embeddings para %d hoteles", len(hotel_embeddings))

    # Embeddings de usuario
    user_embeddings: dict[str, dict[str, float]] = {}
    user_info_list: list[dict] = []

    grouped = customers.groupby("GUEST_ID")
    for guest_id, grp in grouped:
        first = grp.iloc[0]
        visited_hotels = grp["HOTEL_ID"].tolist()
        # Se usa el mismo AVG_SCORE como peso; cambia por reserva pero aquí se mantiene por usuario
        scores = [float(first["AVG_SCORE"])] * len(visited_hotels)

        emb = _compute_user_embedding(visited_hotels, scores, hotel_embeddings)
        user_embeddings[str(guest_id)] = emb

        user_info_list.append({
            "id": int(guest_id) if str(guest_id).isdigit() else guest_id,
            "COUNTRY": first["COUNTRY_GUEST"],
            "GENDER": first["GENDER_ID"],
            "AGE": first["AGE_RANGE"],
            "AVG_SCORE": float(first["AVG_SCORE"]),
            "HOTELS_VISITED": sorted(set(str(h) for h in visited_hotels)),
            "HOTEL_VISIT_COUNTS": {
                str(hotel_id): int(count)
                for hotel_id, count in grp["HOTEL_ID"].value_counts().to_dict().items()
            },
        })

    logger.info("Construidos embeddings para %d usuarios", len(user_embeddings))

    result = {
        "feature_cols": FEATURE_COLS,
        "feature_labels": FEATURE_LABELS,
        "hotel_embeddings": hotel_embeddings,
        "hotel_info": hotel_info,
        "user_embeddings": user_embeddings,
        "user_info": user_info_list,
    }
    return result


def recommend_hotel(
    user_id: str,
    embeddings_data: dict,
    top_n: int = 1,
    segment: dict | None = None,
) -> list[tuple[str, float]]:
    """
    Devuelve los top-N hoteles recomendados.

    Usa la similitud coseno como base y, si recibe ``segment``, reordena con una
    segunda capa basada en etiquetas de afinidad, nivel, comportamiento y fidelidad.
    Los hoteles ya visitados solo se excluyen para perfiles sin señales claras de repetición.
    """
    user_emb = embeddings_data["user_embeddings"].get(str(user_id))
    if user_emb is None:
        return []

    visited_context = _collect_visited_context(user_id, embeddings_data)
    visited = visited_context["hotels"]
    allow_revisits = _allow_visited_hotels(segment)

    user_vec = np.array([user_emb[c] for c in FEATURE_COLS]).reshape(1, -1)
    user_norm = np.linalg.norm(user_vec)
    if user_norm == 0:
        return []

    candidates = []
    for hid, hvec in embeddings_data["hotel_embeddings"].items():
        if hid in visited and not allow_revisits:
            continue
        h_vec = np.array([hvec[c] for c in FEATURE_COLS]).reshape(1, -1)
        hotel_norm = np.linalg.norm(h_vec)
        if hotel_norm == 0:
            sim = 0.0
        else:
            sim = float(np.dot(user_vec, h_vec.T)[0][0] / (user_norm * hotel_norm))
        if segment and segment.get("tags"):
            tag_score = _tag_rerank_score(hid, hvec, embeddings_data, segment, visited_context)
            final_score = 0.72 * float(sim) + 0.28 * tag_score
        else:
            final_score = float(sim)
        candidates.append((hid, final_score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]


def save(data: dict, path: str | None = None) -> str:
    path = save_embeddings_data(data, path)
    logger.info("Embeddings guardados en %s", path)
    return str(path)


def main():
    data = build()
    save(data)

    # Comprobación rápida
    test_user = "1014907189"
    recs = recommend_hotel(test_user, data, top_n=3)
    logger.info("Principales recomendaciones para el usuario %s:", test_user)
    for hid, sim in recs:
        info = data["hotel_info"][hid]
        logger.info("  %s — %s (%.4f)", hid, info["HOTEL_NAME"], sim)


if __name__ == "__main__":
    main()
