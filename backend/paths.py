from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
GENERATED_DATA_DIR = DATA_DIR / "generated"
RUNTIME_DATA_DIR = DATA_DIR / "runtime"
IMAGES_DIR = PROJECT_ROOT / "images"
OUTPUT_DIR = PROJECT_ROOT / "output"
AUTONOMOUS_OUTPUT_DIR = OUTPUT_DIR / "autonomous"
TEMPLATES_DIR = BACKEND_DIR / "campaigns" / "templates"

CUSTOMERS_PATH = RAW_DATA_DIR / "customer_data.csv"
HOTELS_PATH = RAW_DATA_DIR / "hotel_data.csv"
EMBEDDINGS_PATH = GENERATED_DATA_DIR / "embeddings.json"
SEGMENTS_PATH = GENERATED_DATA_DIR / "segments.json"
CAMPAIGN_LOG_PATH = GENERATED_DATA_DIR / "campaign_log.json"
MARKETING_SNAPSHOT_PATH = GENERATED_DATA_DIR / "marketing_dashboard_snapshot.json"
MARKETING_CONTEXT_PATH = RUNTIME_DATA_DIR / "marketing_context.json"
AUTONOMOUS_STATE_PATH = RUNTIME_DATA_DIR / "autonomous_state.json"
ORACLE_CONTEXT_PATH = RUNTIME_DATA_DIR / "oracle_context.json"
