#!/usr/bin/env python3
"""
image_selector.py — Fase 4: selección inteligente de imágenes

Selecciona entre 3 y 5 imágenes por email según el perfil del usuario, su
embedding y el segmento, cruzando las etiquetas de imagen con sus preferencias.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import EMBEDDINGS_PATH, IMAGES_DIR, SEGMENTS_PATH
from backend.personalization.segment_views import get_age_key, is_high_value

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("image_selector")

# Imagen de respaldo para hoteles sin imágenes
PLACEHOLDER_IMAGE = "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600"

# ── Reglas de prioridad por etiquetas ────────────────────────────────────

TAG_RULES = [
    # (función_condición, etiquetas_prioritarias, peso)
    (lambda emb, seg: emb.get("BEACH", 0) > 0.7,
     ["piscina", "playa", "terraza"], 3.0),
    (lambda emb, seg: emb.get("MOUNTAIN", 0) > 0.7,
     ["paisaje", "naturaleza", "senderismo"], 3.0),
    (lambda emb, seg: emb.get("HERITAGE", 0) > 0.7,
     ["exterior histórico", "sala clásica", "fachada", "histórico"], 3.0),
    (lambda emb, seg: is_high_value(seg),
     ["suite", "spa", "minibar", "experiencias premium", "premium"], 2.5),
    (lambda emb, seg: emb.get("TEMP_NORM", 0) > 0.7,
     ["exterior soleado", "piscina", "terraza"], 2.0),
    (lambda emb, seg: get_age_key(seg) == "JOVEN",
     ["lifestyle", "social", "moderno"], 2.0),
    (lambda emb, seg: get_age_key(seg) == "SENIOR",
     ["comfort", "tranquilidad", "restaurante"], 2.0),
    (lambda emb, seg: emb.get("GASTRONOMY", 0) > 0.7,
     ["restaurante", "platos", "bar", "gastronomía"], 2.5),
]

TAG_DESTINO_A_IMAGEN = {
    "playero": ["piscina", "playa", "terraza", "exterior soleado"],
    "montana": ["paisaje", "naturaleza", "senderismo"],
    "cultural": ["exterior histórico", "fachada", "histórico", "museo"],
    "gastronomico": ["restaurante", "platos", "bar", "gastronomía"],
    "clima_calido": ["exterior soleado", "terraza", "piscina"],
    "mediterraneo": ["terraza", "vistas", "exterior soleado"],
    "continental": ["interior", "salón", "arquitectura"],
}


def _load_image_metadata(hotel_id: str) -> list[dict]:
    """Carga los metadatos de imagen de un hotel."""
    meta_path = IMAGES_DIR / str(hotel_id) / "metadata.json"
    if not meta_path.exists():
        return []
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score_image(
    image: dict,
    user_embedding: dict[str, float],
    segment: dict,
) -> float:
    """Puntúa una imagen según el encaje entre sus tags y el perfil del usuario."""
    score = 0.0
    image_tags = set(t.lower() for t in image.get("tags", []))
    image_audience = set(a.lower() for a in image.get("audience", []))

    for condition_fn, priority_tags, weight in TAG_RULES:
        if condition_fn(user_embedding, segment):
            for tag in priority_tags:
                if tag.lower() in image_tags:
                    score += weight

    segment_tags = segment.get("tags", {}) if isinstance(segment, dict) else {}
    destination_tags = segment_tags.get("afinidades_destino", [])
    for destination_tag in destination_tags:
        for preferred_image_tag in TAG_DESTINO_A_IMAGEN.get(destination_tag, []):
            if preferred_image_tag.lower() in image_tags:
                score += 1.8

    value_level = str(segment_tags.get("nivel_valor", "")).strip().lower()
    if value_level in {"premium", "lujo"} and image.get("premium", False):
        score += 2.0
    elif value_level == "esencial" and "premium" in image_tags:
        score -= 0.5

    # Ajuste por audiencia
    age_seg = get_age_key(segment).lower()
    if age_seg == "joven" and "joven" in image_audience:
        score += 1.5
    elif age_seg == "senior" and any(a in image_audience for a in ["senior", "familia"]):
        score += 1.5

    # Bonus premium para clientes de alto valor
    if is_high_value(segment) and image.get("premium", False):
        score += 2.0

    # Bonus de mood
    mood = image.get("mood", "").lower()
    if get_age_key(segment) == "JOVEN" and mood == "aspiracional":
        score += 1.0
    elif get_age_key(segment) == "SENIOR" and mood == "cálido":
        score += 1.0

    return score


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
            "path": str(img_path) if img_path.exists() else PLACEHOLDER_IMAGE,
            "score": score,
            "tags": img.get("tags", []),
            "is_placeholder": not img_path.exists(),
        })

    # Ordenar por puntuación descendente
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Devolver entre min_images y max_images
    result = scored[:max_images]
    while len(result) < min_images:
        result.append({
            "filename": "placeholder.jpg",
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
            logger.info("  %s (score=%.1f, placeholder=%s)",
                        img["filename"], img["score"], img["is_placeholder"])


if __name__ == "__main__":
    main()
