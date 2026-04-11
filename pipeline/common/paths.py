from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = PROJECT_ROOT / "images"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMPLATES_DIR = PIPELINE_DIR / "rendering" / "templates"
