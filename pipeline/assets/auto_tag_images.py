#!/usr/bin/env python3
"""
auto_tag_images.py — Generate image metadata from filenames.

Scans images/{hotel_id}/ directories, extracts the category from each
filename (e.g. "eurostars-torre-sevilla-restauracion-03.jpeg" → "restauracion"),
and assigns appropriate tags, audience, mood and premium flags.

Usage:
    python auto_tag_images.py
"""

import json
import os
import re
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.common.paths import IMAGES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("auto_tag_images")

# ── Category extraction from filename ─────────────────────────────────────

# Known hotel name prefixes (will be stripped to find the category)
HOTEL_PREFIXES = [
    "eurostars-torre-sevilla",
    "eurostars-sevilla-boutique",
    "eurostars-madrid-gran-via",
    "eurostars-isla-de-la-toja",
    "eurostars-aliados",
    "aurea-museum",
    "aurea-catedral",
    "exe-international-palace",
    "exe-domus-aurea",
    "exe-madrid-norte",
]

# Sort longest first so greedy match works
HOTEL_PREFIXES.sort(key=len, reverse=True)


def _extract_category(filename: str) -> str:
    """
    Extract the category from a filename like:
        eurostars-torre-sevilla-restauracion-03.jpeg → restauracion
        aurea-museum-spa-04.jpeg → spa
        exe-madrid-norte-piscina-y-fitness-02.jpeg → piscina-y-fitness
    """
    name = Path(filename).stem
    for prefix in HOTEL_PREFIXES:
        if name.startswith(prefix + "-"):
            remainder = name[len(prefix) + 1:]
            # Strip trailing -NN number
            cat = re.sub(r"-\d+$", "", remainder)
            return cat
    # Fallback: try generic pattern
    cat = re.sub(r"-\d+$", "", name)
    return cat


# ── Tag mapping per category ──────────────────────────────────────────────

CATEGORY_TAG_MAP = {
    "habitaciones": {
        "tags": ["habitación", "comfort", "descanso", "interior"],
        "audience": ["pareja", "profesional", "familia"],
        "mood": "cálido",
        "premium": False,
    },
    "el-hotel": {
        "tags": ["fachada", "exterior", "arquitectura", "lobby"],
        "audience": ["pareja", "profesional", "senior"],
        "mood": "aspiracional",
        "premium": False,
    },
    "cerca-del-hotel": {
        "tags": ["paisaje", "exterior histórico", "vistas", "entorno", "ciudad"],
        "audience": ["joven", "pareja", "senior", "familia"],
        "mood": "aspiracional",
        "premium": False,
    },
    "restauracion": {
        "tags": ["restaurante", "platos", "gastronomía", "bar", "gourmet"],
        "audience": ["pareja", "senior", "profesional"],
        "mood": "cálido",
        "premium": False,
    },
    "spa": {
        "tags": ["spa", "wellness", "relax", "premium", "tranquilidad"],
        "audience": ["senior", "pareja"],
        "mood": "cálido",
        "premium": True,
    },
    "piscina": {
        "tags": ["piscina", "exterior soleado", "relax", "verano"],
        "audience": ["joven", "pareja", "familia"],
        "mood": "aspiracional",
        "premium": False,
    },
    "piscina-y-fitness": {
        "tags": ["piscina", "fitness", "exterior soleado", "relax", "deporte"],
        "audience": ["joven", "pareja", "familia"],
        "mood": "aspiracional",
        "premium": False,
    },
    "salones": {
        "tags": ["salón", "eventos", "interior", "elegante", "reuniones"],
        "audience": ["profesional"],
        "mood": "aspiracional",
        "premium": False,
    },
    "terraza-atalaya": {
        "tags": ["terraza", "vistas", "exterior soleado", "social", "rooftop"],
        "audience": ["joven", "pareja"],
        "mood": "aspiracional",
        "premium": True,
    },
    "balneario-y-club-termal": {
        "tags": ["spa", "wellness", "termal", "relax", "premium", "tranquilidad"],
        "audience": ["senior", "pareja"],
        "mood": "cálido",
        "premium": True,
    },
    "museo": {
        "tags": ["museo", "histórico", "patrimonio", "cultura", "interior"],
        "audience": ["senior", "pareja", "familia"],
        "mood": "cálido",
        "premium": False,
    },
    "aurea-moments": {
        "tags": ["experiencia", "premium", "lifestyle", "exclusivo", "lujo"],
        "audience": ["pareja", "profesional"],
        "mood": "aspiracional",
        "premium": True,
    },
    "ocio-y-wellness": {
        "tags": ["ocio", "wellness", "relax", "comfort", "tranquilidad"],
        "audience": ["senior", "pareja"],
        "mood": "cálido",
        "premium": False,
    },
}

# Default for unknown categories
DEFAULT_TAGS = {
    "tags": ["hotel", "interior"],
    "audience": ["pareja", "profesional"],
    "mood": "cálido",
    "premium": False,
}

# Image file extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def generate_metadata():
    """Scan all hotel image directories and generate metadata.json."""
    hotel_dirs = sorted([
        d for d in os.listdir(IMAGES_DIR)
        if (IMAGES_DIR / d).is_dir()
    ])

    total_images = 0

    for hotel_id in hotel_dirs:
        hotel_dir = IMAGES_DIR / hotel_id

        # Find all image files
        image_files = sorted([
            f for f in os.listdir(hotel_dir)
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        ])

        if not image_files:
            logger.warning("No images found in %s", hotel_dir)
            continue

        metadata = []
        categories_found = set()

        for filename in image_files:
            category = _extract_category(filename)
            categories_found.add(category)

            tag_info = CATEGORY_TAG_MAP.get(category, DEFAULT_TAGS)

            entry = {
                "filename": filename,
                "category": category,
                "tags": tag_info["tags"],
                "audience": tag_info["audience"],
                "mood": tag_info["mood"],
                "premium": tag_info["premium"],
            }
            metadata.append(entry)

        # Write metadata.json
        meta_path = hotel_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        total_images += len(image_files)
        logger.info(
            "Hotel %s: %d images, categories: %s",
            hotel_id, len(image_files), sorted(categories_found)
        )

    logger.info("Total: %d images across %d hotels", total_images, len(hotel_dirs))


def main():
    generate_metadata()


if __name__ == "__main__":
    main()
