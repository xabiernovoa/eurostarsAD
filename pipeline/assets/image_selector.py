#!/usr/bin/env python3
"""
image_selector.py — Phase 4: Intelligent Image Selection

Selects 3-5 images per email based on the user's profile, embedding,
and segment by matching image tags with user preferences.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.paths import DATA_DIR, IMAGES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("image_selector")

# Placeholder image for hotels without images
PLACEHOLDER_IMAGE = "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=600"

# ── Tag priority rules ───────────────────────────────────────────────────

TAG_RULES = [
    # (condition_fn, priority_tags, weight)
    (lambda emb, seg: emb.get("BEACH", 0) > 0.7,
     ["piscina", "playa", "terraza"], 3.0),
    (lambda emb, seg: emb.get("MOUNTAIN", 0) > 0.7,
     ["paisaje", "naturaleza", "senderismo"], 3.0),
    (lambda emb, seg: emb.get("HERITAGE", 0) > 0.7,
     ["exterior histórico", "sala clásica", "fachada", "histórico"], 3.0),
    (lambda emb, seg: seg.get("client_value") == "HIGH_VALUE",
     ["suite", "spa", "minibar", "experiencias premium", "premium"], 2.5),
    (lambda emb, seg: emb.get("TEMP_NORM", 0) > 0.7,
     ["exterior soleado", "piscina", "terraza"], 2.0),
    (lambda emb, seg: seg.get("age_segment") == "JOVEN",
     ["lifestyle", "social", "moderno"], 2.0),
    (lambda emb, seg: seg.get("age_segment") == "SENIOR",
     ["comfort", "tranquilidad", "restaurante"], 2.0),
    (lambda emb, seg: emb.get("GASTRONOMY", 0) > 0.7,
     ["restaurante", "platos", "bar", "gastronomía"], 2.5),
]


def _load_image_metadata(hotel_id: str) -> list[dict]:
    """Load image metadata for a hotel."""
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
    """Score an image based on tag matches with user profile."""
    score = 0.0
    image_tags = set(t.lower() for t in image.get("tags", []))
    image_audience = set(a.lower() for a in image.get("audience", []))

    for condition_fn, priority_tags, weight in TAG_RULES:
        if condition_fn(user_embedding, segment):
            for tag in priority_tags:
                if tag.lower() in image_tags:
                    score += weight

    # Audience matching
    age_seg = segment.get("age_segment", "").lower()
    if age_seg == "joven" and "joven" in image_audience:
        score += 1.5
    elif age_seg == "senior" and any(a in image_audience for a in ["senior", "familia"]):
        score += 1.5

    # Premium bonus for high-value clients
    if segment.get("client_value") == "HIGH_VALUE" and image.get("premium", False):
        score += 2.0

    # Mood bonus
    mood = image.get("mood", "").lower()
    if segment.get("age_segment") == "JOVEN" and mood == "aspiracional":
        score += 1.0
    elif segment.get("age_segment") == "SENIOR" and mood == "cálido":
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
    Select and rank images for a user/hotel combination.
    Returns list of {filename, path, score} dicts.
    """
    metadata = _load_image_metadata(hotel_id)

    if not metadata:
        logger.info("No images found for hotel %s, using placeholder", hotel_id)
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

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Return between min and max images
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
    """Test with sample user."""
    emb_path = DATA_DIR / "embeddings.json"
    seg_path = DATA_DIR / "segments.json"

    with open(emb_path) as f:
        embeddings = json.load(f)
    with open(seg_path) as f:
        segments = json.load(f)

    test_user = "1014907189"
    user_emb = embeddings["user_embeddings"].get(test_user, {})
    seg = segments.get(test_user, {})

    # Get recommended hotel
    from pipeline.embeddings import build_embeddings
    recs = build_embeddings.recommend_hotel(test_user, embeddings, top_n=1)
    if recs:
        hotel_id = recs[0][0]
        images = select_images(hotel_id, user_emb, seg)
        logger.info("Selected %d images for user %s, hotel %s:",
                     len(images), test_user, hotel_id)
        for img in images:
            logger.info("  %s (score=%.1f, placeholder=%s)",
                        img["filename"], img["score"], img["is_placeholder"])


if __name__ == "__main__":
    main()
