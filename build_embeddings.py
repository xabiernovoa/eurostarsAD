#!/usr/bin/env python3
"""
build_embeddings.py — Phase 1: Hotel & User Embedding Generator

Converts hotel features into 11-dimensional vectors and computes
user embeddings as the weighted average (by AVG_SCORE) of visited
hotel vectors. Outputs embeddings.json.
"""

import json
import logging
import os
import sys

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("build_embeddings")

# ── Feature specification ────────────────────────────────────────────────
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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ── Helpers ──────────────────────────────────────────────────────────────

def _load_hotels(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(DATA_DIR, "hotel_data.csv")
    df = pd.read_csv(path, sep=";", dtype={"ID": str})
    df["ID"] = df["ID"].str.strip().str.strip('"')
    logger.info("Loaded %d hotels from %s", len(df), path)
    return df


def _load_customers(path: str | None = None) -> pd.DataFrame:
    path = path or os.path.join(DATA_DIR, "customer_data_200.csv")
    df = pd.read_csv(path, sep=";", dtype={"GUEST_ID": str, "HOTEL_ID": str})
    df["GUEST_ID"] = df["GUEST_ID"].str.strip().str.strip('"')
    df["HOTEL_ID"] = df["HOTEL_ID"].str.strip().str.strip('"')
    df["CHECKIN_DATE"] = pd.to_datetime(df["CHECKIN_DATE"])
    df["CHECKOUT_DATE"] = pd.to_datetime(df["CHECKOUT_DATE"])
    logger.info("Loaded %d reservation rows from %s", len(df), path)
    return df


def _build_hotel_vectors(hotels: pd.DataFrame) -> pd.DataFrame:
    """Create normalised feature vectors for every hotel."""
    h = hotels.copy()

    # Stars normalisation (min-max)
    stars = h["STARS"].astype(float)
    h["STARS_NORM"] = (stars - stars.min()) / (stars.max() - stars.min())

    # Temperature normalisation (min-max)
    temp = h["CITY_AVG_TEMPERATURE"].astype(float)
    h["TEMP_NORM"] = (temp - temp.min()) / (temp.max() - temp.min())

    # Ordinal mappings
    h["RAIN_RISK_NUM"] = h["CITY_RAIN_RISK"].map(ORDINAL_MAP)
    h["HERITAGE"] = h["CITY_HISTORICAL_HERITAGE"].map(ORDINAL_MAP)
    h["PRICE_LEVEL"] = h["CITY_PRICE_LEVEL"].map(ORDINAL_MAP)
    h["GASTRONOMY"] = h["CITY_GASTRONOMY"].map(ORDINAL_MAP)

    # Binary flags
    h["BEACH"] = h["CITY_BEACH_FLAG"].map(YESNO_MAP)
    h["MOUNTAIN"] = h["CITY_MOUNTAIN_FLAG"].map(YESNO_MAP)

    # One-hot climate
    h["CLIMATE_ATLANTIC"] = (h["CITY_CLIMATE"] == "ATLANTIC").astype(float)
    h["CLIMATE_CONTINENTAL"] = (h["CITY_CLIMATE"] == "CONTINENTAL").astype(float)
    h["CLIMATE_MEDITERRANEAN"] = (h["CITY_CLIMATE"] == "MEDITERRANEAN").astype(float)

    return h


def _compute_user_embedding(
    user_hotels: list[str],
    user_scores: list[float],
    hotel_vectors: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Weighted average of hotel vectors by AVG_SCORE."""
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


# ── Main ─────────────────────────────────────────────────────────────────

def build(hotel_path: str | None = None, customer_path: str | None = None) -> dict:
    """Build all embeddings and return the full data structure."""
    hotels = _load_hotels(hotel_path)
    customers = _load_customers(customer_path)

    # Hotel vectors
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

    logger.info("Built embeddings for %d hotels", len(hotel_embeddings))

    # User embeddings
    user_embeddings: dict[str, dict[str, float]] = {}
    user_info_list: list[dict] = []

    grouped = customers.groupby("GUEST_ID")
    for guest_id, grp in grouped:
        first = grp.iloc[0]
        visited_hotels = grp["HOTEL_ID"].tolist()
        # Use the same AVG_SCORE for weighting (it's per-reservation but same per user)
        scores = [float(first["AVG_SCORE"])] * len(visited_hotels)

        emb = _compute_user_embedding(visited_hotels, scores, hotel_embeddings)
        user_embeddings[str(guest_id)] = emb

        user_info_list.append({
            "id": int(guest_id) if str(guest_id).isdigit() else guest_id,
            "COUNTRY": first["COUNTRY_GUEST"],
            "GENDER": first["GENDER_ID"],
            "AGE": first["AGE_RANGE"],
            "AVG_SCORE": float(first["AVG_SCORE"]),
            "HOTELS_VISITED": sorted(set(int(h) for h in visited_hotels)),
        })

    logger.info("Built embeddings for %d users", len(user_embeddings))

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
) -> list[tuple[str, float]]:
    """Return top-N hotels by cosine similarity, excluding already visited."""
    from sklearn.metrics.pairwise import cosine_similarity

    user_emb = embeddings_data["user_embeddings"].get(str(user_id))
    if user_emb is None:
        return []

    # Hotels visited by this user
    visited = set()
    for ui in embeddings_data["user_info"]:
        if str(ui["id"]) == str(user_id):
            visited = set(str(h) for h in ui["HOTELS_VISITED"])
            break

    user_vec = np.array([user_emb[c] for c in FEATURE_COLS]).reshape(1, -1)

    candidates = []
    for hid, hvec in embeddings_data["hotel_embeddings"].items():
        if hid in visited:
            continue
        h_vec = np.array([hvec[c] for c in FEATURE_COLS]).reshape(1, -1)
        sim = cosine_similarity(user_vec, h_vec)[0][0]
        candidates.append((hid, float(sim)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]


def save(data: dict, path: str | None = None) -> str:
    path = path or os.path.join(DATA_DIR, "embeddings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Saved embeddings to %s", path)
    return path


def main():
    data = build()
    save(data)

    # Quick sanity check
    test_user = "1014907189"
    recs = recommend_hotel(test_user, data, top_n=3)
    logger.info("Top recommendations for user %s:", test_user)
    for hid, sim in recs:
        info = data["hotel_info"][hid]
        logger.info("  %s — %s (%.4f)", hid, info["HOTEL_NAME"], sim)


if __name__ == "__main__":
    main()
