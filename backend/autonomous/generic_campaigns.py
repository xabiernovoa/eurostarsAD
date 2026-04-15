"""
generic_campaigns.py — Campañas genéricas por segmento y tendencia.

A diferencia de ``generator.py`` (que apunta a un usuario concreto),
este módulo produce propuestas de campaña para segmentos amplios. Se activa
periódicamente y usa el Oráculo para elegir destinos con tendencias positivas.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend import config
from backend.ai import gemini as gemini_client
from backend.autonomous import oracle
from backend.personalization.segment_views import (
    get_age_key,
    get_primary_affinity,
    get_primary_affinity_label,
    get_segment_label,
    get_value_label,
    get_value_level,
)
from backend.storage.embeddings import load_embeddings
from backend.storage.segments import load_segments as load_segments_data

logger = logging.getLogger("autonomous.generic_campaigns")


def _load_segments() -> dict[str, dict[str, Any]]:
    return load_segments_data()


def _load_hotel_info() -> dict[str, dict[str, Any]]:
    return load_embeddings().get("hotel_info", {})


def _largest_segments(
    segments: dict[str, dict[str, Any]],
    min_size: int,
) -> list[tuple[str, int]]:
    """Agrupa por edad + afinidad principal + nivel de valor y devuelve los mayores."""
    counter: Counter[tuple[str, str, str]] = Counter()
    for seg in segments.values():
        key = (
            get_age_key(seg),
            get_primary_affinity(seg),
            get_value_level(seg),
        )
        counter[key] += 1

    ordered = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    labeled = [
        (f"{age}|{affinity}|{value}", count) for (age, affinity, value), count in ordered if count >= min_size
    ]
    return labeled


def _segment_key_to_parts(key: str) -> tuple[str, str, str]:
    parts = key.split("|")
    if len(parts) != 3:
        return "ADULTO", "cultural", "confort"
    return parts[0], parts[1], parts[2]


def _pick_hotel_for_city(
    city: str,
    hotel_info: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    matches = [
        (hid, info)
        for hid, info in hotel_info.items()
        if info.get("CITY_NAME", "").upper() == city.upper()
    ]
    if not matches:
        return None
    # Priorizamos mayor categoría
    matches.sort(key=lambda kv: kv[1].get("STARS", 0), reverse=True)
    return matches[0]


def _build_gemini_prompt(
    segment_key: str,
    segment_size: int,
    hotel: dict[str, Any],
    city: str,
    oracle_city_context: list[dict[str, Any]],
) -> str:
    age, affinity, value = _segment_key_to_parts(segment_key)
    segment_label = f"{age.title()} · {get_primary_affinity_label({'tags': {'afinidades_destino': [affinity]}})} · {get_value_label({'tags': {'nivel_valor': value}})}"
    context_lines = "\n".join(
        f"- [{e.get('category')}] {e.get('summary')} (rel {e.get('relevance')})"
        for e in oracle_city_context[:4]
    ) or "- (sin contexto específico)"

    return f"""Eres un estratega de marketing para la cadena hotelera Eurostars.
Diseña una propuesta de campaña GENÉRICA en español dirigida al segmento "{segment_label}".

DATOS DEL SEGMENTO:
- Edad: {age}
- Afinidad principal: {affinity}
- Nivel de valor: {value}
- Tamaño estimado: {segment_size} usuarios

DESTINO SUGERIDO:
- Ciudad: {city}
- Hotel propuesto: {hotel.get('HOTEL_NAME', '')} ({hotel.get('STARS', 4)}★, {hotel.get('BRAND', 'EUROSTARS')})

CONTEXTO DEL ORÁCULO (tendencias y eventos en {city}):
{context_lines}

Devuelve un JSON con EXACTAMENTE estos campos:
{{
  "campaign_name": "Nombre interno de la campaña",
  "target_segment": "{segment_label}",
  "hotel_id": "{hotel.get('id', '')}",
  "subject": "Asunto del email (máx 60 car.)",
  "headline": "Título principal",
  "body_summary": "Resumen de 2-3 frases del cuerpo del email",
  "recommended_dates": "Rango de fechas sugerido (texto libre)",
  "rationale": "Explicación breve (por qué este segmento, este destino, este momento)"
}}"""


def _fallback_proposal(
    segment_key: str,
    segment_size: int,
    hotel_id: str,
    hotel: dict[str, Any],
    city: str,
    oracle_city_context: list[dict[str, Any]],
) -> dict[str, Any]:
    age, affinity, value = _segment_key_to_parts(segment_key)
    segment_label = f"{age.title()} · {get_primary_affinity_label({'tags': {'afinidades_destino': [affinity]}})} · {get_value_label({'tags': {'nivel_valor': value}})}"
    headline = f"{city.title()} te espera"
    if age == "SENIOR":
        headline = f"Descubra {city.title()} con todo el confort"
    elif age == "JOVEN":
        headline = f"Haz las maletas: {city.title()} es tu próximo plan"

    oracle_hook = ""
    if oracle_city_context:
        oracle_hook = oracle_city_context[0].get("summary", "")

    body = (
        f"Proponemos al segmento {segment_label} una escapada a {city.title()} "
        f"alojada en {hotel.get('HOTEL_NAME', 'nuestros hoteles')}. "
    )
    if oracle_hook:
        body += f"Contexto actual: {oracle_hook}"

    return {
        "campaign_name": f"{age.lower()}_{affinity}_{value}_{city.upper()}_auto",
        "target_segment": segment_label,
        "hotel_id": hotel_id,
        "subject": f"{city.title()}: una experiencia pensada para ti",
        "headline": headline,
        "body_summary": body,
        "recommended_dates": "Próximas 4-6 semanas",
        "rationale": (
            f"Segmento {segment_label} con {segment_size} usuarios y tendencia positiva "
            f"del Oráculo en {city.title()}."
        ),
    }


def _validate_proposal(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    required = {
        "campaign_name",
        "target_segment",
        "hotel_id",
        "subject",
        "headline",
        "body_summary",
        "recommended_dates",
        "rationale",
    }
    if not required.issubset(data.keys()):
        return None
    return data


def generate_generic_campaigns(
    oracle_context: list[dict[str, Any]] | None = None,
    output_dir: Path | None = None,
    max_campaigns: int = 3,
    min_segment_size: int | None = None,
    save_report: bool = True,
    force_mock: bool = False,
) -> list[dict[str, Any]]:
    """
    Produce propuestas de campaña genéricas y las guarda como JSON en disco.

    Devuelve la lista de propuestas generadas.
    """
    oracle_context = oracle_context or []
    output_dir = Path(output_dir or config.GENERIC_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    min_size = (
        min_segment_size
        if min_segment_size is not None
        else config.MIN_SEGMENT_SIZE_FOR_GENERIC
    )

    segments = _load_segments()
    hotel_info = _load_hotel_info()

    top_segments = _largest_segments(segments, min_size=min_size)
    if not top_segments:
        logger.info("No hay segmentos grandes suficientes para campañas genéricas")
        return []

    trending = oracle.get_trending_destinations(oracle_context, limit=max_campaigns * 2)
    if not trending:
        # Recurso de respaldo: usar las ciudades configuradas si no hay contexto
        trending = [(city, 5) for city in config.ORACLE_CITIES]

    proposals: list[dict[str, Any]] = []
    used_cities: set[str] = set()
    segment_idx = 0

    for city, _score in trending:
        if segment_idx >= len(top_segments) or len(proposals) >= max_campaigns:
            break
        if city in used_cities:
            continue

        hotel_match = _pick_hotel_for_city(city, hotel_info)
        if not hotel_match:
            continue
        hotel_id, hotel = hotel_match
        hotel_with_id = {**hotel, "id": hotel_id}
        segment_key, segment_size = top_segments[segment_idx]
        segment_idx += 1

        city_ctx = oracle.get_context_for_city(oracle_context, city)

        proposal: dict[str, Any] | None = None
        source = "mock"
        if not force_mock and gemini_client.is_available():
            prompt = _build_gemini_prompt(
                segment_key, segment_size, hotel_with_id, city, city_ctx
            )
            raw = gemini_client.call_gemini(prompt, json_output=True)
            proposal = _validate_proposal(raw)
            if proposal:
                source = "gemini"

        if proposal is None:
            proposal = _fallback_proposal(
                segment_key, segment_size, hotel_id, hotel, city, city_ctx
            )

        proposal["generated_at"] = datetime.now().isoformat(timespec="seconds")
        proposal["source"] = source
        proposal["segment_size"] = segment_size
        proposal["destination_city"] = city
        proposal["oracle_context_used"] = city_ctx
        proposals.append(proposal)
        used_cities.add(city)

    if save_report and proposals:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"generic_campaigns_{timestamp}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False, indent=2)
        logger.info("Informe de campañas genéricas guardado en %s", path)

    return proposals


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    config.ensure_output_dirs()
    ctx = oracle.refresh_oracle()
    proposals = generate_generic_campaigns(oracle_context=ctx, max_campaigns=2)
    print(json.dumps(proposals, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
