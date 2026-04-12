"""
gemini_client.py — Wrapper minimalista sobre Gemini vía Vertex AI.

Usa la SDK unificada ``google-genai`` en modo Vertex, autenticada con la cuenta
de servicio apuntada por ``GOOGLE_APPLICATION_CREDENTIALS``. Si no hay
credenciales válidas o la llamada falla, devuelve ``None`` para que los
módulos llamantes recurran a mocks y el sistema siga funcionando en
``--dry-run``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from autonomous import config

logger = logging.getLogger("autonomous.gemini")

_CLIENT_CACHE: dict[str, Any] = {}


def _strip_json_fence(text: str) -> str:
    """Elimina bloques ```json ... ``` si el modelo los incluye."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _credentials_ok() -> bool:
    """Comprueba que la ruta de credenciales resuelta apunta a un archivo."""
    path = config.VERTEX_CREDENTIALS_PATH
    return bool(path) and path.is_file()


def is_available() -> bool:
    """Indica si Vertex AI puede usarse (credenciales válidas + SDK instalada)."""
    if not config.VERTEX_PROJECT_ID:
        return False
    if not _credentials_ok():
        return False
    try:
        import google.genai  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _get_client():
    """Instancia (y cachea) el cliente Vertex del SDK ``google-genai``."""
    if "client" in _CLIENT_CACHE:
        return _CLIENT_CACHE["client"]

    from google import genai  # type: ignore

    client = genai.Client(
        vertexai=True,
        project=config.VERTEX_PROJECT_ID,
        location=config.VERTEX_LOCATION,
    )
    _CLIENT_CACHE["client"] = client
    return client


def call_gemini(prompt: str, json_output: bool = True) -> Any:
    """
    Envía un prompt a Gemini (Vertex) y devuelve la respuesta.

    Si ``json_output`` es True devuelve un dict/list; en caso contrario texto
    plano. Si la llamada falla o las credenciales no están disponibles,
    devuelve None.
    """
    if not is_available():
        logger.debug("Vertex AI no disponible — devolviendo None")
        return None

    try:
        client = _get_client()
    except Exception as exc:  # pragma: no cover — depende del SDK
        logger.warning("No se pudo instanciar cliente Vertex: %s", exc)
        return None

    full_prompt = prompt
    if json_output:
        full_prompt += (
            "\n\nResponde ÚNICAMENTE con JSON válido, sin markdown ni comillas triples."
        )

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=full_prompt,
        )
    except Exception as exc:  # pragma: no cover — red/API
        logger.warning("Llamada a Vertex falló: %s", exc)
        return None

    raw = getattr(response, "text", None) or ""
    if not raw:
        logger.warning("Respuesta vacía de Vertex")
        return None

    if not json_output:
        return raw.strip()

    cleaned = _strip_json_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Respuesta JSON inválida de Vertex: %s", exc)
        logger.debug("Raw: %s", raw)
        return None
