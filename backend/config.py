"""
config.py — Configuración del sistema autónomo.

Todos los valores se pueden sobreescribir mediante variables de entorno
(prefijo ``AUTONOMOUS_``) para facilitar pruebas y despliegues.
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.paths import AUTONOMOUS_OUTPUT_DIR, AUTONOMOUS_STATE_PATH, ORACLE_CONTEXT_PATH, PROJECT_ROOT

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(PROJECT_ROOT / ".env")
except ModuleNotFoundError:
    pass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


# ── Rutas base ───────────────────────────────────────────────────────────
OUTPUT_DIR = AUTONOMOUS_OUTPUT_DIR
EMAILS_DIR = OUTPUT_DIR / "emails"
GENERIC_DIR = OUTPUT_DIR / "generic_campaigns"
ORACLE_FILE = Path(os.environ.get("AUTONOMOUS_ORACLE_FILE", ORACLE_CONTEXT_PATH))
STATE_FILE = Path(os.environ.get("AUTONOMOUS_STATE_FILE", AUTONOMOUS_STATE_PATH))
LOG_FILE = OUTPUT_DIR / "autonomous.log"

# ── Intervalos de ejecución ──────────────────────────────────────────────
ORACLE_INTERVAL_HOURS = _env_int("AUTONOMOUS_ORACLE_INTERVAL_HOURS", 6)
HEARTBEAT_INTERVAL_MINUTES = _env_int("AUTONOMOUS_HEARTBEAT_INTERVAL_MINUTES", 30)
GENERIC_CAMPAIGN_INTERVAL_HOURS = _env_int("AUTONOMOUS_GENERIC_CAMPAIGN_INTERVAL_HOURS", 48)

# ── Reglas de negocio ────────────────────────────────────────────────────
USER_COOLDOWN_DAYS = _env_int("AUTONOMOUS_USER_COOLDOWN_DAYS", 14)
SEND_WINDOW_DAYS = _env_int("AUTONOMOUS_SEND_WINDOW_DAYS", 7)
MAX_USERS_PER_TICK = _env_int("AUTONOMOUS_MAX_USERS_PER_TICK", 25)
MIN_SEGMENT_SIZE_FOR_GENERIC = _env_int("AUTONOMOUS_MIN_SEGMENT_SIZE_FOR_GENERIC", 10)

# ── Modo de ejecución ────────────────────────────────────────────────────
DRY_RUN = _env_bool("AUTONOMOUS_DRY_RUN", True)

# ── API Vertex AI (Gemini) ───────────────────────────────────────────────
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
GEMINI_MODEL = os.environ.get("AUTONOMOUS_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TEMPERATURE = _env_float("AUTONOMOUS_GEMINI_TEMPERATURE", 0.7)


def _resolve_credentials_path() -> Path | None:
    """
    Resuelve ``GOOGLE_APPLICATION_CREDENTIALS`` contra la raíz del proyecto.

    El valor en ``.env`` se escribe como ruta relativa al proyecto
    (p. ej. ``.secrets/vertex-service-account.json``) para que el repositorio
    sea portable entre máquinas. Aquí lo convertimos SIEMPRE a una ruta
    absoluta y la reescribimos en el entorno, de forma que el SDK de Google
    la encuentre con independencia del ``cwd`` desde el que se arranque
    el proceso (``python -m backend.autonomous.cli``, ``python demos/marketing/server.py``,
    tests, etc.).
    """
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not raw:
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    return path


VERTEX_CREDENTIALS_PATH = _resolve_credentials_path()
VERTEX_CREDENTIALS_FILE = str(VERTEX_CREDENTIALS_PATH) if VERTEX_CREDENTIALS_PATH else ""

# ── Formato de logs (mismo que el pipeline existente) ────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

# ── Ciudades objetivo del Oráculo ────────────────────────────────────────
ORACLE_CITIES = [
    "SEVILLA",
    "GRANADA",
    "LISBOA",
    "OPORTO",
    "ROMA",
    "MADRID",
    "EL GROVE",
]


def ensure_output_dirs() -> None:
    """Crea los directorios de salida si no existen."""
    for directory in (OUTPUT_DIR, EMAILS_DIR, GENERIC_DIR):
        directory.mkdir(parents=True, exist_ok=True)
