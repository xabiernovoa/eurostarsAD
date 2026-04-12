"""
oracle.py — Consulta y clasifica eventos/noticias relevantes para los destinos.

El Oráculo es la única fuente de contexto externo del sistema. Puede usar
Gemini para resumir y clasificar, pero en modo ``--dry-run`` o sin clave API
genera datos mock realistas basados en las ciudades del catálogo.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from autonomous import config, gemini_client

logger = logging.getLogger("autonomous.oracle")

VALID_CATEGORIES = {
    "cultural_event",
    "extreme_weather",
    "travel_alert",
    "seasonal_offer",
    "tourism_trend",
}


# ── Base de datos mock: entradas plausibles por ciudad ───────────────────
_MOCK_POOL: dict[str, list[dict[str, Any]]] = {
    "SEVILLA": [
        {
            "category": "cultural_event",
            "summary": "La Feria de Abril alcanza su apogeo con casetas abiertas al público.",
            "relevance": 9,
            "actionable": True,
        },
        {
            "category": "seasonal_offer",
            "summary": "Los hoteles del centro ofrecen descuentos tras Semana Santa.",
            "relevance": 7,
            "actionable": True,
        },
    ],
    "GRANADA": [
        {
            "category": "cultural_event",
            "summary": "Conciertos al atardecer en la Alhambra durante el festival de primavera.",
            "relevance": 8,
            "actionable": True,
        },
        {
            "category": "tourism_trend",
            "summary": "Incremento notable de visitas internacionales al barrio del Albaicín.",
            "relevance": 6,
            "actionable": True,
        },
    ],
    "LISBOA": [
        {
            "category": "cultural_event",
            "summary": "Las Fiestas de Lisboa empiezan a calentar motores con eventos en Alfama.",
            "relevance": 8,
            "actionable": True,
        },
        {
            "category": "seasonal_offer",
            "summary": "Compañías aéreas lanzan tarifas reducidas desde el sur de Europa.",
            "relevance": 7,
            "actionable": True,
        },
    ],
    "OPORTO": [
        {
            "category": "tourism_trend",
            "summary": "Las bodegas de Vila Nova de Gaia baten récord de reservas para primavera.",
            "relevance": 8,
            "actionable": True,
        },
        {
            "category": "cultural_event",
            "summary": "Festival de jazz en la Ribeira durante el fin de semana largo.",
            "relevance": 7,
            "actionable": True,
        },
    ],
    "ROMA": [
        {
            "category": "cultural_event",
            "summary": "Nueva exposición del Caravaggio en los Museos Capitolinos.",
            "relevance": 9,
            "actionable": True,
        },
        {
            "category": "tourism_trend",
            "summary": "El Jubileo atrae más visitantes de lo previsto a la Ciudad Eterna.",
            "relevance": 8,
            "actionable": True,
        },
    ],
    "MADRID": [
        {
            "category": "cultural_event",
            "summary": "Arco cierra con récord de asistencia y exposiciones paralelas.",
            "relevance": 8,
            "actionable": True,
        },
        {
            "category": "seasonal_offer",
            "summary": "Promociones gastronómicas en torno a la Semana del Cocido.",
            "relevance": 6,
            "actionable": True,
        },
    ],
    "EL GROVE": [
        {
            "category": "tourism_trend",
            "summary": "Aumento de reservas en resorts de las Rías Baixas para primavera.",
            "relevance": 7,
            "actionable": True,
        },
        {
            "category": "seasonal_offer",
            "summary": "Menús de marisco con descuentos entre semana en la ría de Arousa.",
            "relevance": 7,
            "actionable": True,
        },
    ],
}


def _mock_oracle_context(
    cities: list[str] | None = None,
    limit: int = 10,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Genera entradas plausibles sin llamar a ningún API."""
    cities = cities or config.ORACLE_CITIES
    rng = random.Random(seed if seed is not None else 42)

    today = datetime.now()
    entries: list[dict[str, Any]] = []
    for city in cities:
        pool = _MOCK_POOL.get(city.upper())
        if not pool:
            continue
        for item in pool:
            offset_days = rng.randint(0, 30)
            entries.append(
                {
                    "city": city.upper(),
                    "category": item["category"],
                    "summary": item["summary"],
                    "relevance": item["relevance"],
                    "date": (today + timedelta(days=offset_days)).strftime("%Y-%m-%d"),
                    "actionable": item["actionable"],
                }
            )

    # Añadimos alguna alerta puntual para simular casos negativos
    if rng.random() < 0.25:
        blocked = rng.choice(cities).upper()
        entries.append(
            {
                "city": blocked,
                "category": "travel_alert",
                "summary": f"Huelga puntual en transporte público de {blocked.title()} "
                "durante 48 horas.",
                "relevance": 8,
                "date": (today + timedelta(days=rng.randint(1, 7))).strftime("%Y-%m-%d"),
                "actionable": False,
            }
        )

    rng.shuffle(entries)
    return entries[:limit]


def _gemini_oracle_context(cities: list[str], limit: int) -> list[dict[str, Any]] | None:
    """Pide a Gemini un contexto actualizado para las ciudades dadas."""
    if not gemini_client.is_available():
        return None

    categories = ", ".join(sorted(VALID_CATEGORIES))
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""Eres un analista de inteligencia turística para la cadena hotelera Eurostars.
Genera {limit} entradas de contexto relevantes para las siguientes ciudades: {', '.join(cities)}.

Fecha actual: {today}.

Cada entrada debe clasificarse en una de estas categorías: {categories}.

Devuelve un array JSON donde cada elemento tenga EXACTAMENTE estos campos:
- "city": string en MAYÚSCULAS (una de las ciudades indicadas).
- "category": una de las categorías válidas.
- "summary": resumen breve en español (máximo 160 caracteres).
- "relevance": entero 1-10 (10 = máxima relevancia para marketing hotelero).
- "date": fecha ISO YYYY-MM-DD cercana a hoy.
- "actionable": booleano. False SOLO si es una alerta negativa que desaconseja viajar.

Distribuye las entradas entre distintas ciudades. Incluye al menos una travel_alert
realista si procede. No inventes emergencias graves."""

    raw = gemini_client.call_gemini(prompt, json_output=True)
    if not isinstance(raw, list):
        return None

    cleaned: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        city = str(item.get("city", "")).upper().strip()
        category = str(item.get("category", "")).strip()
        if not city or category not in VALID_CATEGORIES:
            continue
        try:
            relevance = int(item.get("relevance", 5))
        except (TypeError, ValueError):
            relevance = 5
        cleaned.append(
            {
                "city": city,
                "category": category,
                "summary": str(item.get("summary", "")).strip(),
                "relevance": max(1, min(10, relevance)),
                "date": str(item.get("date", datetime.now().strftime("%Y-%m-%d"))),
                "actionable": bool(item.get("actionable", True)),
            }
        )
    return cleaned or None


def refresh_oracle(
    cities: list[str] | None = None,
    limit: int = 10,
    use_gemini: bool = True,
) -> list[dict[str, Any]]:
    """Genera o actualiza el contexto del Oráculo."""
    cities = cities or config.ORACLE_CITIES
    context: list[dict[str, Any]] | None = None

    if use_gemini:
        context = _gemini_oracle_context(cities, limit)
        if context:
            logger.info("Oráculo actualizado vía Gemini con %d entradas", len(context))

    if not context:
        context = _mock_oracle_context(cities=cities, limit=limit)
        logger.info("Oráculo actualizado con datos mock (%d entradas)", len(context))

    return context


def save_oracle_context(context: list[dict[str, Any]], path: Path | None = None) -> Path:
    """Guarda el contexto en disco para que otros módulos lo inspeccionen."""
    path = Path(path or config.ORACLE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    logger.info("Contexto del Oráculo guardado en %s", path)
    return path


def get_blocked_destinations(context: list[dict[str, Any]]) -> set[str]:
    """Devuelve las ciudades bloqueadas por alertas negativas."""
    return {
        entry["city"].upper()
        for entry in context
        if entry.get("category") == "travel_alert" and not entry.get("actionable", True)
    }


def get_context_for_city(context: list[dict[str, Any]], city: str) -> list[dict[str, Any]]:
    """Filtra el contexto para una ciudad concreta."""
    city_up = city.upper()
    return [entry for entry in context if entry.get("city", "").upper() == city_up]


def get_trending_destinations(
    context: list[dict[str, Any]],
    limit: int = 5,
) -> list[tuple[str, int]]:
    """Devuelve ciudades con tendencias positivas ordenadas por relevancia."""
    scores: dict[str, int] = {}
    for entry in context:
        if entry.get("category") == "travel_alert" and not entry.get("actionable", True):
            continue
        if entry.get("category") not in {"tourism_trend", "cultural_event", "seasonal_offer"}:
            continue
        city = entry.get("city", "").upper()
        scores[city] = max(scores.get(city, 0), int(entry.get("relevance", 0)))

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ordered[:limit]


def main() -> None:  # pragma: no cover — utilidad manual
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    config.ensure_output_dirs()
    ctx = refresh_oracle()
    save_oracle_context(ctx)


if __name__ == "__main__":  # pragma: no cover
    main()
