"""
campaign_generator.py — Generación de campañas personalizadas.

Reutiliza módulos del pipeline existente para:
  * Segmentar al usuario y obtener su embedding.
  * Calcular la recomendación top-1 excluyendo hoteles visitados.
  * Elegir el canal (email) con el selector de canales del pipeline.
  * Generar el copy con Gemini (o un fallback determinista).
  * Renderizar el HTML con la plantilla adecuada por edad.

El módulo NO escribe en ningún archivo del pipeline original.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from autonomous import config, gemini_client
from pipeline.campaigns import campaign_engine
from pipeline.channels import channel_selector
from pipeline.rendering import email_renderer

logger = logging.getLogger("autonomous.campaign_generator")


SEGMENT_TONE = {
    "JOVEN": (
        "Tono informal y aspiracional, cercano al usuario, sin emojis. "
        "Frases directas y breves, tutea al usuario, transmite energía."
    ),
    "ADULTO": (
        "Tono equilibrado y profesional, centrado en el valor y la experiencia. "
        "Destaca confort y calidad-precio. Puede usar usted o tú según contexto."
    ),
    "SENIOR": (
        "Tono cálido, claro y sin jerga. Frases amplias, trato de usted, "
        "transmite tranquilidad y atención personalizada."
    ),
}


# ── Afinidad perfil de viaje → categoría de evento del Oráculo ──────────
# Los boost se suman a la relevancia base del evento para decidir cuál es
# el más interesante para este usuario en concreto. Los perfiles con fuerte
# componente exploradora (aventurero, explorador_cultural, gastronomia) se
# ven atraídos por eventos culturales y tendencias turísticas; los de lujo
# responden mejor a ofertas estacionales; sol_y_playa a tendencias.
PROFILE_EVENT_AFFINITY: dict[str, dict[str, int]] = {
    "EXPLORADOR_CULTURAL": {"cultural_event": 4, "tourism_trend": 3, "seasonal_offer": 1},
    "AVENTURERO":          {"cultural_event": 3, "tourism_trend": 4, "seasonal_offer": 1},
    "GASTRONOMIA_CIUDAD":  {"cultural_event": 3, "tourism_trend": 2, "seasonal_offer": 2},
    "SOL_Y_PLAYA":         {"cultural_event": 1, "tourism_trend": 3, "seasonal_offer": 2},
    "LUJO":                {"cultural_event": 2, "tourism_trend": 2, "seasonal_offer": 3},
}
_DEFAULT_AFFINITY = {"cultural_event": 2, "tourism_trend": 2, "seasonal_offer": 1}


def match_oracle_events(
    oracle_context: list[dict[str, Any]],
    hotel_city: str,
    travel_profile: str,
    max_events: int = 3,
) -> list[dict[str, Any]]:
    """
    Ordena los eventos del Oráculo relevantes para el destino y el perfil.

    * Filtra por ciudad del hotel.
    * Elimina alertas de viaje negativas (no accionables).
    * Puntúa cada evento con ``relevance + boost(perfil, categoría)``.
    * Devuelve los top-N por puntuación.
    """
    city_up = (hotel_city or "").upper()
    affinity = PROFILE_EVENT_AFFINITY.get(travel_profile, _DEFAULT_AFFINITY)

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in oracle_context:
        if entry.get("city", "").upper() != city_up:
            continue
        if entry.get("category") == "travel_alert" and not entry.get("actionable", True):
            continue
        category = entry.get("category", "")
        try:
            base = int(entry.get("relevance", 5))
        except (TypeError, ValueError):
            base = 5
        boost = affinity.get(category, 0)
        if category == "extreme_weather":
            boost -= 2  # no bloquea pero penaliza
        scored.append((base + boost, entry))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in scored[:max_events]]


def _format_preferences(prefs: list[str]) -> str:
    return ", ".join(prefs) if prefs else "diversidad de experiencias"


def _format_matched_events(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "(sin eventos relevantes detectados para este perfil)"
    lines = []
    for e in entries:
        lines.append(
            f"- [{e.get('category', '')}] {e.get('summary', '')} "
            f"(relevancia base {e.get('relevance', '?')}, fecha {e.get('date', '')})"
        )
    return "\n".join(lines)


def _build_gemini_prompt(
    campaign_data: dict[str, Any],
    matched_events: list[dict[str, Any]],
) -> str:
    seg = campaign_data["segment"]
    age_segment = seg.get("age_segment", "ADULTO")
    travel_profile = seg.get("travel_profile", "EXPLORADOR_CULTURAL")
    hotel = campaign_data["recommended_hotel"]
    prefs = campaign_data.get("preferences", [])

    tone = SEGMENT_TONE.get(age_segment, SEGMENT_TONE["ADULTO"])

    # Instrucción específica sobre cómo incorporar los eventos del oráculo
    if matched_events:
        top_event = matched_events[0]
        event_instruction = (
            f"IMPORTANTE — USO DEL ORÁCULO:\n"
            f"Este usuario tiene perfil de viaje '{travel_profile}'. El evento más\n"
            f"afín a su perfil ocurriendo ahora en {hotel['city']} es:\n"
            f"  «{top_event.get('summary', '')}» ({top_event.get('category', '')}, "
            f"{top_event.get('date', '')}).\n"
            f"DEBES mencionar este evento de forma orgánica en UNO de los body_paragraphs\n"
            f"como gancho principal: conecta explícitamente el perfil del usuario\n"
            f"({travel_profile}) con el evento, explicando por qué este momento es\n"
            f"ideal para visitar {hotel['city']}. No inventes detalles adicionales\n"
            f"del evento; usa exclusivamente la información del resumen."
        )
    else:
        event_instruction = (
            "ORÁCULO: no hay eventos específicos para este destino. Céntrate en las\n"
            "preferencias detectadas del usuario y la temporada."
        )

    return f"""Eres un copywriter experto de la cadena hotelera Eurostars.
Genera el contenido de un email pre-estancia personalizado en ESPAÑOL.

PERFIL DEL USUARIO:
- Segmento de edad: {age_segment}
- Perfil de viaje: {travel_profile}
- Valor del cliente: {seg.get('client_value', 'MID_VALUE')}
- País de origen: {seg.get('country', 'ES')}
- Patrón de viaje: {seg.get('travel_pattern', 'EXPLORADOR')}

HOTEL RECOMENDADO:
- Nombre: {hotel['name']}
- Ciudad: {hotel['city']} ({hotel['country']})
- Categoría: {hotel['stars']} estrellas
- Marca: {hotel['brand']}
- Preferencias detectadas del usuario: {_format_preferences(prefs)}

CONTEXTO TEMPORAL:
- Fecha sugerida de check-in: {campaign_data['checkin_suggested']}
- Duración sugerida: {campaign_data['stay_nights']} noches
- Temporada: {campaign_data['season']}

EVENTOS DEL ORÁCULO EN {hotel['city']} ORDENADOS POR AFINIDAD CON EL PERFIL:
{_format_matched_events(matched_events)}

{event_instruction}

INSTRUCCIONES DE TONO:
{tone}

Devuelve un JSON con EXACTAMENTE estos campos:
{{
  "subject": "Asunto del email (máx. 60 caracteres)",
  "preheader": "Texto preview (máx. 100 caracteres)",
  "headline": "Título principal",
  "subheadline": "Subtítulo complementario",
  "body_paragraphs": ["párrafo 1", "párrafo 2", "párrafo 3 opcional"],
  "cta_text": "Texto del botón CTA (máx. 30 caracteres)",
  "ps_line": "Línea PD final"
}}"""


def _fallback_copy(campaign_data: dict[str, Any]) -> dict[str, Any]:
    """Copy determinista cuando Gemini no está disponible."""
    seg = campaign_data["segment"]
    age = seg.get("age_segment", "ADULTO")
    hotel = campaign_data["recommended_hotel"]
    stay = campaign_data["stay_nights"]
    season = campaign_data["season"]

    if age == "JOVEN":
        return {
            "subject": f"{hotel['city']} te espera esta {season}",
            "preheader": f"Hemos encontrado tu próxima escapada en {hotel['name']}",
            "headline": f"¿Listo para descubrir {hotel['city']}?",
            "subheadline": f"{hotel['name']} — tu base ideal",
            "body_paragraphs": [
                f"Sabemos que te gusta explorar, y {hotel['city']} tiene todo "
                "lo que buscas en tu próxima aventura.",
                f"Planea una escapada de {stay} noches y sumérgete en su cultura, "
                "gastronomía y ritmo único.",
            ],
            "cta_text": "Reservar ahora",
            "ps_line": "PD: Las mejores habitaciones se agotan rápido.",
        }
    if age == "SENIOR":
        return {
            "subject": f"{hotel['name']} — Su escapada a {hotel['city']}",
            "preheader": "Un viaje pensado especialmente para usted",
            "headline": f"Le invitamos a descubrir {hotel['city']}",
            "subheadline": f"{hotel['name']} — confort y calidad garantizados",
            "body_paragraphs": [
                f"Nos complace sugerirle una estancia en {hotel['name']}, "
                f"un hotel de {hotel['stars']} estrellas en {hotel['city']}.",
                f"Hemos previsto una estancia de {stay} noches para que disfrute "
                f"con tranquilidad de todo lo que {hotel['city']} ofrece.",
                "Nuestro equipo estará encantado de atenderle personalmente.",
            ],
            "cta_text": "Consultar fechas",
            "ps_line": "PD: Puede llamarnos al +34 900 100 200 para cualquier consulta.",
        }
    return {
        "subject": f"{hotel['city']} — tu próximo destino ideal",
        "preheader": f"Una experiencia seleccionada en {hotel['name']}",
        "headline": f"Descubre {hotel['city']} con Eurostars",
        "subheadline": f"{hotel['name']} ★{hotel['stars']}",
        "body_paragraphs": [
            f"Hemos seleccionado {hotel['name']} en {hotel['city']} como tu "
            "próximo destino ideal, basándonos en tus preferencias.",
            f"Con una estancia recomendada de {stay} noches, disfrutarás de "
            f"todo lo que este destino ofrece durante el {season}.",
        ],
        "cta_text": "Ver disponibilidad",
        "ps_line": "PD: Como cliente Eurostars disfrutas de condiciones exclusivas.",
    }


def _validate_copy(copy: Any) -> dict[str, Any] | None:
    """Comprueba que el copy devuelto por Gemini tenga los campos obligatorios."""
    if not isinstance(copy, dict):
        return None
    required = {
        "subject",
        "preheader",
        "headline",
        "subheadline",
        "body_paragraphs",
        "cta_text",
        "ps_line",
    }
    if not required.issubset(copy.keys()):
        return None
    if not isinstance(copy["body_paragraphs"], list) or not copy["body_paragraphs"]:
        return None
    return copy


def _generate_copy(
    campaign_data: dict[str, Any],
    matched_events: list[dict[str, Any]],
    force_mock: bool = False,
) -> tuple[dict[str, Any], str]:
    """Devuelve (copy, source) donde source es 'gemini' o 'mock'."""
    if not force_mock and gemini_client.is_available():
        prompt = _build_gemini_prompt(campaign_data, matched_events)
        raw = gemini_client.call_gemini(prompt, json_output=True)
        validated = _validate_copy(raw)
        if validated:
            return validated, "gemini"
        logger.warning(
            "Gemini devolvió un copy inválido para %s — usando fallback",
            campaign_data.get("guest_id", "?"),
        )

    return _fallback_copy(campaign_data), "mock"


def _cta_suffix(campaign_data: dict[str, Any]) -> str:
    seg = campaign_data["segment"]
    age = seg.get("age_segment", "ADULTO").lower()
    season = campaign_data.get("season", "temporada")
    return (
        f"utm_source=email&utm_medium=autonomous&utm_campaign={age}_{season}_2026"
    )


def generate_campaign(
    guest_id: str,
    oracle_context: list[dict[str, Any]] | None = None,
    output_dir: Path | None = None,
    save_html: bool = True,
    force_mock: bool = False,
) -> dict[str, Any] | None:
    """
    Genera una campaña pre-arrival personalizada para un usuario.

    Devuelve un diccionario con metadatos de la campaña y la ruta del HTML
    (si se ha guardado). Devuelve None si no se puede generar (usuario sin
    datos o destino bloqueado).
    """
    oracle_context = oracle_context or []
    output_dir = Path(output_dir or config.EMAILS_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = campaign_engine.generate_all("pre_arrival", guest_id=str(guest_id))
    if not results:
        logger.warning("Sin datos de campaña para el usuario %s", guest_id)
        return None

    campaign_data = results[0]
    hotel_city = campaign_data["recommended_hotel"].get("city", "").upper()

    # Bloqueo por destino
    blocked = {
        e["city"].upper()
        for e in oracle_context
        if e.get("category") == "travel_alert" and not e.get("actionable", True)
    }
    if hotel_city in blocked:
        logger.info(
            "Usuario %s: destino %s bloqueado por el Oráculo — omitiendo",
            guest_id,
            hotel_city,
        )
        return None

    # Canal: para este sistema siempre forzamos email, pero registramos
    # la decisión del selector del pipeline para auditoría.
    channel_decision = channel_selector.select_channel(
        campaign_data["segment"],
        {"avg_booking_leadtime": campaign_data.get("avg_length_stay", 15)},
    )

    # Eventos del oráculo ordenados por afinidad con el perfil del usuario
    matched_events = match_oracle_events(
        oracle_context,
        hotel_city,
        campaign_data["segment"].get("travel_profile", ""),
    )

    copy, copy_source = _generate_copy(
        campaign_data, matched_events, force_mock=force_mock
    )
    # Aseguramos cta_url_suffix para compatibilidad con la plantilla
    copy.setdefault("cta_url_suffix", _cta_suffix(campaign_data))

    html = email_renderer.render_email(campaign_data, copy, images=[], moment="pre_arrival")

    html_path: Path | None = None
    if save_html:
        filename = f"pre_arrival_{guest_id}.html"
        html_path = output_dir / filename
        html_path.write_text(html, encoding="utf-8")
        logger.info("Email renderizado guardado en %s", html_path)

    return {
        "guest_id": str(guest_id),
        "segment": campaign_data["segment"],
        "hotel": campaign_data["recommended_hotel"],
        "channel": channel_decision,
        "copy": copy,
        "copy_source": copy_source,
        "matched_events": matched_events,
        "html_path": str(html_path) if html_path else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
    config.ensure_output_dirs()
    result = generate_campaign("1014907189")
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
