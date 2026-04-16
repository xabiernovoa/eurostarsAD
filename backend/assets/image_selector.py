#!/usr/bin/env python3
"""
image_selector.py — Fase 4: selección inteligente de imágenes

Selecciona entre 3 y 5 imágenes por email según el perfil del usuario, su
embedding y el segmento, usando categorías reales deducidas del nombre de
archivo. La lógica prioriza simplicidad y diversidad frente a taxonomías
artificiales de tags.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.assets.image_metadata import _extract_category
from backend.paths import EMBEDDINGS_PATH, IMAGES_DIR, SEGMENTS_PATH
from backend.personalization.segment_views import get_age_key, is_high_value

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("image_selector")

# Imagen de respaldo para hoteles sin imágenes
PLACEHOLDER_IMAGE = "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600"

# ── Reglas de prioridad por categoría ───────────────────────────────────

CATEGORY_BASE_SCORES = {
    "habitaciones": 1.8,
    "el-hotel": 1.4,
    "cerca-del-hotel": 1.7,
    "restauracion": 1.6,
    "spa": 1.8,
    "piscina": 1.8,
    "piscina-y-fitness": 1.7,
    "salones": 0.8,
    "terraza-atalaya": 1.9,
    "balneario-y-club-termal": 1.9,
    "museo": 1.8,
    "aurea-moments": 1.8,
    "ocio-y-wellness": 1.5,
}

EMBEDDING_CATEGORY_RULES = [
    (
        lambda emb, seg: emb.get("BEACH", 0) > 0.7,
        {"piscina": 3.0, "piscina-y-fitness": 2.5, "terraza-atalaya": 2.5, "cerca-del-hotel": 1.4},
    ),
    (
        lambda emb, seg: emb.get("MOUNTAIN", 0) > 0.7,
        {"cerca-del-hotel": 2.5},
    ),
    (
        lambda emb, seg: emb.get("HERITAGE", 0) > 0.7,
        {"cerca-del-hotel": 3.0, "museo": 2.8, "el-hotel": 1.3},
    ),
    (
        lambda emb, seg: emb.get("GASTRONOMY", 0) > 0.7,
        {"restauracion": 3.2},
    ),
    (
        lambda emb, seg: emb.get("TEMP_NORM", 0) > 0.7,
        {"piscina": 2.0, "piscina-y-fitness": 1.8, "terraza-atalaya": 1.8, "cerca-del-hotel": 1.0},
    ),
]

AFFINITY_CATEGORY_BOOSTS = {
    "playero": {"piscina": 2.8, "piscina-y-fitness": 2.2, "terraza-atalaya": 2.0, "cerca-del-hotel": 1.2},
    "montana": {"cerca-del-hotel": 2.5},
    "cultural": {"cerca-del-hotel": 2.7, "museo": 2.7, "el-hotel": 1.2},
    "gastronomico": {"restauracion": 3.0},
    "clima_calido": {"piscina": 2.0, "piscina-y-fitness": 1.8, "terraza-atalaya": 1.7, "cerca-del-hotel": 1.0},
    "mediterraneo": {"terraza-atalaya": 2.0, "cerca-del-hotel": 1.8, "piscina": 1.4},
    "continental": {"el-hotel": 1.4, "salones": 1.0, "habitaciones": 0.8},
}

AGE_CATEGORY_BOOSTS = {
    "JOVEN": {"terraza-atalaya": 1.8, "piscina": 1.5, "piscina-y-fitness": 1.5, "cerca-del-hotel": 1.0},
    "ADULTO": {"habitaciones": 0.6, "restauracion": 0.6, "el-hotel": 0.4},
    "SENIOR": {"habitaciones": 1.4, "spa": 1.8, "balneario-y-club-termal": 1.8, "ocio-y-wellness": 1.5, "restauracion": 1.0},
}


def _load_image_metadata(hotel_id: str) -> list[dict]:
    """Carga los metadatos de imagen de un hotel."""
    meta_path = IMAGES_DIR / str(hotel_id) / "metadata.json"
    if not meta_path.exists():
        return []
    with open(meta_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    normalized = []
    for image in raw:
        if not isinstance(image, dict):
            continue
        filename = str(image.get("filename", "")).strip()
        if not filename:
            continue
        category = str(image.get("category", "")).strip() or _extract_category(filename)
        normalized.append(
            {
                "filename": filename,
                "category": category,
                "premium": bool(image.get("premium", False)),
            }
        )
    return normalized


def _category_boost(category: str, weights: dict[str, float]) -> float:
    return float(weights.get(category, 0.0))


def _score_image(
    image: dict,
    user_embedding: dict[str, float],
    segment: dict,
) -> float:
    """Puntúa una imagen con una lógica simple basada en categorías reales."""
    category = str(image.get("category", "")).strip()
    score = CATEGORY_BASE_SCORES.get(category, 1.0)

    for condition_fn, category_boosts in EMBEDDING_CATEGORY_RULES:
        if condition_fn(user_embedding, segment):
            score += _category_boost(category, category_boosts)

    segment_tags = segment.get("tags", {}) if isinstance(segment, dict) else {}
    for affinity in segment_tags.get("afinidades_destino", []):
        score += _category_boost(category, AFFINITY_CATEGORY_BOOSTS.get(str(affinity).strip(), {}))

    age_segment = get_age_key(segment)
    score += _category_boost(category, AGE_CATEGORY_BOOSTS.get(age_segment, {}))

    value_level = str(segment_tags.get("nivel_valor", "")).strip().lower()
    if image.get("premium", False):
        if is_high_value(segment):
            score += 2.2
        elif value_level == "esencial":
            score -= 1.0

    return score


def _select_diverse_images(scored: list[dict], max_images: int) -> list[dict]:
    """Prioriza la mejor imagen de cada categoría antes de repetir categoría."""
    if not scored:
        return []

    result: list[dict] = []
    seen_categories: set[str] = set()
    seen_filenames: set[str] = set()

    for image in scored:
        category = str(image.get("category", "")).strip()
        filename = str(image.get("filename", "")).strip()
        if category and category in seen_categories:
            continue
        result.append(image)
        if category:
            seen_categories.add(category)
        if filename:
            seen_filenames.add(filename)
        if len(result) >= max_images:
            return result

    for image in scored:
        filename = str(image.get("filename", "")).strip()
        if filename and filename in seen_filenames:
            continue
        result.append(image)
        if filename:
            seen_filenames.add(filename)
        if len(result) >= max_images:
            break

    return result


def select_images(
    hotel_id: str,
    user_embedding: dict[str, float],
    segment: dict,
    max_images: int = 5,
    min_images: int = 3,
) -> list[dict]:
    """
    Selecciona y ordena imágenes para una combinación usuario/hotel.
    Devuelve una lista de diccionarios con filename, path y score.
    """
    metadata = _load_image_metadata(hotel_id)

    if not metadata:
        logger.info("No se han encontrado imágenes para el hotel %s; se usará el placeholder", hotel_id)
        return [{"filename": "placeholder.jpg", "path": PLACEHOLDER_IMAGE,
                 "score": 0, "is_placeholder": True}] * min_images

    scored = []
    for img in metadata:
        score = _score_image(img, user_embedding, segment)
        img_path = IMAGES_DIR / str(hotel_id) / img["filename"]
        scored.append({
            "filename": img["filename"],
            "category": img.get("category", ""),
            "premium": img.get("premium", False),
            "path": str(img_path) if img_path.exists() else PLACEHOLDER_IMAGE,
            "score": score,
            "is_placeholder": not img_path.exists(),
        })

    # Ordenar por puntuación descendente
    scored.sort(key=lambda x: (x["score"], x["filename"]), reverse=True)

    # Devolver entre min_images y max_images priorizando diversidad de categorías
    result = _select_diverse_images(scored, max_images)
    while len(result) < min_images:
        result.append({
            "filename": "placeholder.jpg",
            "category": "placeholder",
            "premium": False,
            "path": PLACEHOLDER_IMAGE,
            "score": 0,
            "is_placeholder": True,
        })

    return result


def main():
    """Prueba la selección con un usuario de ejemplo."""
    emb_path = EMBEDDINGS_PATH
    seg_path = SEGMENTS_PATH

    with open(emb_path) as f:
        embeddings = json.load(f)
    with open(seg_path) as f:
        segments = json.load(f)

    test_user = "1014907189"
    user_emb = embeddings["user_embeddings"].get(test_user, {})
    seg = segments.get(test_user, {})

    # Obtener el hotel recomendado
    from backend.personalization import embeddings as build_embeddings
    recs = build_embeddings.recommend_hotel(test_user, embeddings, top_n=1, segment=seg)
    if recs:
        hotel_id = recs[0][0]
        images = select_images(hotel_id, user_emb, seg)
        logger.info("Seleccionadas %d imágenes para el usuario %s y el hotel %s:",
                     len(images), test_user, hotel_id)
        for img in images:
            logger.info("  %s [%s] (score=%.1f, placeholder=%s)",
                        img["filename"], img.get("category", ""), img["score"], img["is_placeholder"])


if __name__ == "__main__":
    main()
