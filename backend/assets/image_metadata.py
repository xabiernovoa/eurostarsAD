#!/usr/bin/env python3
"""
auto_tag_images.py — Genera metadatos simples de imágenes a partir del nombre.

Recorre los directorios images/{hotel_id}/ y extrae una categoría estable desde
el nombre de archivo. A partir de esa categoría solo persiste dos señales
realmente fiables en este dataset:
  * ``category``: tipo de imagen deducido del naming
  * ``premium``: si esa categoría suele representar una experiencia premium

Uso:
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

from backend.paths import IMAGES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("auto_tag_images")

# ── Extracción de categoría desde el nombre de archivo ───────────────────

# Prefijos conocidos de nombre de hotel que se eliminan para obtener la categoría
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

# Ordenar por longitud descendente para que el match codicioso funcione
HOTEL_PREFIXES.sort(key=len, reverse=True)


def _extract_category(filename: str) -> str:
    """
    Extrae la categoría de nombres de archivo como:
        eurostars-torre-sevilla-restauracion-03.jpeg -> restauracion
        aurea-museum-spa-04.jpeg -> spa
        exe-madrid-norte-piscina-y-fitness-02.jpeg -> piscina-y-fitness
    """
    name = Path(filename).stem
    for prefix in HOTEL_PREFIXES:
        if name.startswith(prefix + "-"):
            remainder = name[len(prefix) + 1:]
            # Eliminar el sufijo numérico final -NN
            cat = re.sub(r"-\d+$", "", remainder)
            return cat
    # Recurso de respaldo: intentar el patrón genérico
    cat = re.sub(r"-\d+$", "", name)
    return cat


# ── Metadatos mínimos por categoría ─────────────────────────────────────

CATEGORY_METADATA = {
    "habitaciones": {"premium": False},
    "el-hotel": {"premium": False},
    "cerca-del-hotel": {"premium": False},
    "restauracion": {"premium": False},
    "spa": {"premium": True},
    "piscina": {"premium": False},
    "piscina-y-fitness": {"premium": False},
    "salones": {"premium": False},
    "terraza-atalaya": {"premium": True},
    "balneario-y-club-termal": {"premium": True},
    "museo": {"premium": False},
    "aurea-moments": {"premium": True},
    "ocio-y-wellness": {"premium": False},
}

DEFAULT_METADATA = {"premium": False}

# Extensiones de archivo válidas para imágenes
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def generate_metadata():
    """Recorre todos los directorios de imágenes de hotel y genera metadata.json."""
    hotel_dirs = sorted([
        d for d in os.listdir(IMAGES_DIR)
        if (IMAGES_DIR / d).is_dir()
    ])

    total_images = 0

    for hotel_id in hotel_dirs:
        hotel_dir = IMAGES_DIR / hotel_id

        # Buscar todos los archivos de imagen
        image_files = sorted([
            f for f in os.listdir(hotel_dir)
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        ])

        if not image_files:
            logger.warning("No se han encontrado imágenes en %s", hotel_dir)
            continue

        metadata = []
        categories_found = set()

        for filename in image_files:
            category = _extract_category(filename)
            categories_found.add(category)

            metadata_info = CATEGORY_METADATA.get(category, DEFAULT_METADATA)

            entry = {
                "filename": filename,
                "category": category,
                "premium": metadata_info["premium"],
            }
            metadata.append(entry)

        # Escribir metadata.json
        meta_path = hotel_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        total_images += len(image_files)
        logger.info(
            "Hotel %s: %d imágenes, categorías: %s",
            hotel_id, len(image_files), sorted(categories_found)
        )

    logger.info("Total: %d imágenes repartidas en %d hoteles", total_images, len(hotel_dirs))


def main():
    generate_metadata()


if __name__ == "__main__":
    main()
