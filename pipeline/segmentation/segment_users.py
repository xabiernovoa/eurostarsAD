#!/usr/bin/env python3
"""
segment_users.py — Phase 2: User Segmentation

Computes four segmentation axes for every user:
  1. Age segment   → JOVEN / ADULTO / SENIOR  (drives email layout)
  2. Travel profile → archetype based on embedding dimensions (drives tone)
  3. Client value   → HIGH_VALUE / MID_VALUE / STANDARD  (drives service)
  4. Travel pattern  → RECURRENTE_DESTINO / EXPLORADOR / FIEL_CADENA
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.paths import DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("segment_users")

# ── Age mapping ──────────────────────────────────────────────────────────
AGE_SEGMENT_MAP = {
    "19-25": "JOVEN",
    "26-35": "JOVEN",
    "36-45": "ADULTO",
    "46-65": "ADULTO",
    ">65": "SENIOR",
}


def _age_segment(age_range: str) -> str:
    return AGE_SEGMENT_MAP.get(age_range, "ADULTO")


# ── Travel profile (from embedding dimensions, priority order) ───────────
def _travel_profile(emb: dict[str, float]) -> str:
    if emb.get("HERITAGE", 0) > 0.7 and emb.get("PRICE_LEVEL", 0) < 0.7:
        return "EXPLORADOR_CULTURAL"
    if emb.get("PRICE_LEVEL", 0) > 0.7 and emb.get("STARS_NORM", 0) > 0.7:
        return "LUJO"
    if emb.get("BEACH", 0) > 0.5 and emb.get("TEMP_NORM", 0) > 0.6:
        return "SOL_Y_PLAYA"
    if emb.get("MOUNTAIN", 0) > 0.5:
        return "AVENTURERO"
    if (
        emb.get("GASTRONOMY", 0) > 0.7
        and emb.get("BEACH", 0) < 0.3
        and emb.get("MOUNTAIN", 0) < 0.3
    ):
        return "GASTRONOMIA_CIUDAD"
    # Default: choose the strongest signal
    return "EXPLORADOR_CULTURAL"


# ── Client value (ADR percentiles) ───────────────────────────────────────
def _compute_value_tiers(customers: pd.DataFrame) -> dict[str, str]:
    """Assign HIGH_VALUE / MID_VALUE / STANDARD based on ADR percentiles."""
    adr_by_user = customers.groupby("GUEST_ID")["CONFIRMED_RESERVATIONS_ADR"].first()
    p25 = np.percentile(adr_by_user.values, 25)
    p75 = np.percentile(adr_by_user.values, 75)
    logger.info("ADR percentiles — P25=%.2f  P75=%.2f", p25, p75)

    tiers: dict[str, str] = {}
    for uid, adr in adr_by_user.items():
        if adr > p75:
            tiers[str(uid)] = "HIGH_VALUE"
        elif adr < p25:
            tiers[str(uid)] = "STANDARD"
        else:
            tiers[str(uid)] = "MID_VALUE"
    return tiers


# ── Travel pattern ───────────────────────────────────────────────────────
def _travel_pattern(
    guest_id: str,
    reservations: pd.DataFrame,
    hotel_info: dict[str, dict],
) -> str:
    user_rows = reservations[reservations["GUEST_ID"] == guest_id]

    # RECURRENTE_DESTINO: same hotel more than once
    hotel_counts = Counter(user_rows["HOTEL_ID"].tolist())
    if any(c > 1 for c in hotel_counts.values()):
        return "RECURRENTE_DESTINO"

    # EXPLORADOR: high hotel diversity
    n_distinct = user_rows["HOTEL_ID"].nunique()
    n_reservations = len(user_rows)
    if n_reservations > 0 and (n_distinct / n_reservations) > 0.8:
        return "EXPLORADOR"

    # FIEL_CADENA: different hotels but same brand
    brands = set()
    for hid in user_rows["HOTEL_ID"].unique():
        info = hotel_info.get(str(hid))
        if info:
            brands.add(info.get("BRAND", ""))
    if len(brands) == 1 and n_distinct > 1:
        return "FIEL_CADENA"

    return "EXPLORADOR"


# ── Main ─────────────────────────────────────────────────────────────────

def segment(
    embeddings_path: str | None = None,
    customers_path: str | None = None,
) -> dict[str, dict]:
    """Build segments for all users. Returns {guest_id: {segment dict}}."""
    embeddings_path = embeddings_path or DATA_DIR / "embeddings.json"
    customers_path = customers_path or DATA_DIR / "customer_data_200.csv"

    with open(embeddings_path, "r", encoding="utf-8") as f:
        emb_data = json.load(f)

    customers = pd.read_csv(customers_path, sep=";", dtype={"GUEST_ID": str, "HOTEL_ID": str})
    customers["GUEST_ID"] = customers["GUEST_ID"].str.strip().str.strip('"')
    customers["HOTEL_ID"] = customers["HOTEL_ID"].str.strip().str.strip('"')

    value_tiers = _compute_value_tiers(customers)

    segments: dict[str, dict] = {}

    for user_info in emb_data["user_info"]:
        uid = str(user_info["id"])
        age = user_info.get("AGE", "36-45")
        emb = emb_data["user_embeddings"].get(uid, {})

        segments[uid] = {
            "guest_id": uid,
            "age_segment": _age_segment(age),
            "travel_profile": _travel_profile(emb),
            "client_value": value_tiers.get(uid, "MID_VALUE"),
            "travel_pattern": _travel_pattern(uid, customers, emb_data["hotel_info"]),
            "country": user_info.get("COUNTRY", ""),
            "gender": user_info.get("GENDER", ""),
            "age_range": age,
            "avg_score": user_info.get("AVG_SCORE", 0),
        }

    logger.info("Segmented %d users", len(segments))
    return segments


def save(segments: dict, path: str | None = None) -> str:
    path = path or DATA_DIR / "segments.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    logger.info("Saved segments to %s", path)
    return path


def main():
    segs = segment()
    save(segs)

    # Distribution summary
    from collections import Counter as C
    for axis in ["age_segment", "travel_profile", "client_value", "travel_pattern"]:
        dist = C(s[axis] for s in segs.values())
        logger.info("%s distribution: %s", axis, dict(dist))


if __name__ == "__main__":
    main()
