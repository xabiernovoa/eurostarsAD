#!/usr/bin/env python3
"""
text_generator.py — Fase 5: generación de texto con IA

Genera el copy del email con Gemini vía Vertex AI.
Hace fallback a copy simulado si Gemini no está disponible o si se fuerza mock.
Produce una salida JSON con subject, preheader, headline, body, CTA, etc.
"""

import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()

# ── Logs: solo WARNING+ por stderr para no contaminar stdout ─────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("text_generator")

from backend.personalization.segment_views import (
    get_age_key,
    get_affinities,
    get_loyalty_label,
    get_primary_affinity_label,
    get_segment_label,
    get_segment_slug,
    get_value_label,
)

# ── Instrucciones de tono por segmento de edad ───────────────────────────

TONE_INSTRUCTIONS = {
    "JOVEN": (
        "Tono informal, aspiracional. No uses emojis bajo ningún concepto. "
        "Frases cortas y directas. Evita formalidades. Transmite energía y ganas "
        "de vivir experiencias únicas. Tutea al usuario."
    ),
    "ADULTO": (
        "Tono equilibrado, enfocado en el valor y la experiencia. "
        "Profesional pero cercano. Destaca la calidad, el confort y la relación "
        "calidad-precio. Usa usted o tú según el contexto."
    ),
    "SENIOR": (
        "Tono cálido, claro, sin jerga. Frases amplias y bien estructuradas. "
        "Transmite tranquilidad, confianza y atención personalizada. "
        "Trate siempre de usted. Evite emojis y abreviaturas."
    ),
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _format_segment_tags(seg: dict) -> str:
    """Convierte las etiquetas enriquecidas en texto legible para el prompt."""
    tags = seg.get("tags", {}) if isinstance(seg, dict) else {}
    if not tags:
        return "- Sin etiquetas enriquecidas disponibles"

    affinities = ", ".join(tags.get("afinidades_destino", [])) or "sin afinidades claras"
    booking = tags.get("comportamiento_reserva", {}) or {}
    loyalty = tags.get("fidelidad", {}) or {}
    demographics = tags.get("demografia", {}) or {}

    secondary_loyalty = ", ".join(loyalty.get("secundarias", [])) or "ninguna"

    return (
        f"- Afinidades de destino: {affinities}\n"
        f"- Nivel de valor: {tags.get('nivel_valor', 'desconocido')}\n"
        f"- Reserva: antelación={booking.get('antelacion', 'desconocida')}, "
        f"duración={booking.get('duracion', 'desconocida')}, "
        f"frecuencia={booking.get('frecuencia', 'desconocida')}\n"
        f"- Fidelidad: principal={loyalty.get('principal', 'desconocida')}, "
        f"secundarias={secondary_loyalty}\n"
        f"- Demografía: edad={demographics.get('edad', 'desconocida')}, "
        f"género={demographics.get('genero', '')}, país={demographics.get('pais', '')}"
    )


def _build_prompt(campaign_data: dict, moment: str) -> str:
    """Construye el prompt para el modelo de IA."""
    seg = campaign_data["segment"]
    age_segment = get_age_key(seg)
    country = seg.get("country", "ES")
    gender = seg.get("gender", "")
    primary_affinity = get_primary_affinity_label(seg)
    destination_tags = ", ".join(get_affinities(seg)) or "sin afinidades claras"
    value_level = get_value_label(seg)
    loyalty = get_loyalty_label(seg)

    tone = TONE_INSTRUCTIONS.get(age_segment, TONE_INSTRUCTIONS["ADULTO"])

    if moment == "pre_arrival":
        hotel = campaign_data["recommended_hotel"]
        events = campaign_data.get("events", [])
        events_text = ""
        if events:
            events_text = "Eventos en el destino: " + ", ".join(
                f"{e['name']} ({e['date']})" for e in events
            )

        prompt = f"""Eres un copywriter experto de la cadena hotelera Eurostars. 
Genera el contenido de un email pre-estancia personalizado en español.

PERFIL DEL USUARIO:
- Edad: {age_segment}
- Etiqueta principal: {get_segment_label(seg)}
- Afinidad principal de destino: {primary_affinity}
- Afinidades detectadas: {destination_tags}
- Nivel de valor: {value_level}
- Fidelidad principal: {loyalty}
- País de origen: {country}
- Género: {gender}
- Puntuación media que da: {seg.get('avg_score', 7)}

ETIQUETAS ENRIQUECIDAS:
{_format_segment_tags(seg)}

HOTEL RECOMENDADO:
- Nombre: {hotel['name']}
- Ciudad: {hotel['city']}
- País: {hotel['country']}
- Estrellas: {hotel['stars']}
- Marca: {hotel['brand']}

CONTEXTO:
- Fecha sugerida de check-in: {campaign_data['checkin_suggested']}
- Duración sugerida: {campaign_data['stay_nights']} noches
- Temporada: {campaign_data['season']}
- Preferencias del usuario: {', '.join(campaign_data.get('preferences', []))}
{events_text}

INSTRUCCIONES DE TONO:
{tone}

La marca Eurostars es aspiracional, europea, cercana pero elegante.

Genera un JSON con esta estructura exacta:
{{
    "subject": "Asunto del email (máx 60 caracteres)",
    "preheader": "Texto preview del email (máx 100 caracteres)",
    "headline": "Título principal del email",
    "subheadline": "Subtítulo que complementa el headline",
    "body_paragraphs": ["párrafo 1", "párrafo 2", "párrafo 3 opcional"],
    "cta_text": "Texto del botón CTA",
    "cta_url_suffix": "utm_source=email&utm_medium=pre_arrival&utm_campaign=personalized_2025",
    "ps_line": "Línea PS final del email"
}}

IMPORTANTE: Devuelve SOLO el JSON, sin markdown ni explicaciones."""

    elif moment == "post_stay":
        last = campaign_data["last_stay"]
        next_hotel = campaign_data.get("recommended_hotel", {})

        prompt = f"""Eres un copywriter experto de la cadena hotelera Eurostars.
Genera el contenido de un email post-estancia personalizado en español.

PERFIL DEL USUARIO:
- Edad: {age_segment}
- Etiqueta principal: {get_segment_label(seg)}
- Afinidad principal de destino: {primary_affinity}
- Afinidades detectadas: {destination_tags}
- Nivel de valor: {value_level}
- Fidelidad principal: {loyalty}
- País: {country}

ETIQUETAS ENRIQUECIDAS:
{_format_segment_tags(seg)}

ÚLTIMA ESTANCIA:
- Hotel: {last['hotel_name']}
- Ciudad: {last['city']}
- Entrada: {last['checkin']}
- Salida: {last['checkout']}

PRÓXIMO DESTINO RECOMENDADO:
- Hotel: {next_hotel.get('HOTEL_NAME', 'por descubrir')}
- Ciudad: {next_hotel.get('CITY_NAME', '')}
- Estrellas: {next_hotel.get('STARS', '')}

INSTRUCCIONES DE TONO:
{tone}

Genera un JSON con esta estructura exacta:
{{
    "subject": "Asunto del email (máx 60 caracteres)",
    "preheader": "Texto preview (máx 100 caracteres)",
    "headline": "Título principal — rememorar la estancia",
    "subheadline": "Subtítulo con gancho hacia el próximo viaje",
    "body_paragraphs": ["párrafo nostálgico sobre la estancia", "párrafo sobre el próximo destino"],
    "cta_text": "Texto del botón CTA",
    "cta_url_suffix": "utm_source=email&utm_medium=post_stay&utm_campaign=personalized_2025",
    "ps_line": "Línea PS"
}}

IMPORTANTE: Devuelve SOLO el JSON, sin markdown ni explicaciones."""

    else:
        prompt = "Genera un saludo genérico para un email de Eurostars Hotels."

    return prompt


def _mock_copy(campaign_data: dict, moment: str) -> dict:
    """Genera copy simulado sin llamar a la API."""
    seg = campaign_data["segment"]
    age = get_age_key(seg)
    segment_slug = get_segment_slug(seg)

    if moment == "pre_arrival":
        hotel = campaign_data["recommended_hotel"]
        stay = campaign_data["stay_nights"]
        season = campaign_data["season"]

        copies = {
            "JOVEN": {
                "subject": f"{hotel['city']} te espera — tu próxima escapada",
                "preheader": f"Hemos encontrado el hotel perfecto para ti en {hotel['city']}",
                "headline": f"¿Preparado para descubrir {hotel['city']}?",
                "subheadline": f"{hotel['name']} — tu base perfecta este {season}",
                "body_paragraphs": [
                    f"Sabemos que te encanta explorar y vivir nuevas experiencias. "
                    f"Por eso hemos seleccionado {hotel['name']} en {hotel['city']} "
                    f"especialmente para ti.",
                    f"Tu escapada perfecta suele durar {stay} noches — justo lo que "
                    f"necesitas para sumergirte en todo lo que {hotel['city']} tiene "
                    f"para ofrecer este {season}.",
                    f"Desde patrimonio cultural hasta la mejor gastronomía local, "
                    f"{hotel['city']} lo tiene todo.",
                ],
                "cta_text": "Reservar ahora",
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign={segment_slug}_{season}_2025",
                "ps_line": "PD: Las mejores habitaciones vuelan rápido. ¡No te quedes sin la tuya!",
            },
            "ADULTO": {
                "subject": f"{hotel['city']} — tu próximo destino ideal",
                "preheader": f"Una experiencia seleccionada para usted en {hotel['name']}",
                "headline": f"Descubra {hotel['city']} con Eurostars",
                "subheadline": f"{hotel['name']} ★{'★' * (hotel['stars'] - 1)} — {season}",
                "body_paragraphs": [
                    f"Estimado viajero, hemos seleccionado {hotel['name']} en "
                    f"{hotel['city']} como su próximo destino ideal, basándonos "
                    f"en sus preferencias y experiencias anteriores con nosotros.",
                    f"Con una estancia recomendada de {stay} noches, podrá disfrutar "
                    f"de todo lo que este destino ofrece: cultura, gastronomía y el "
                    f"confort que usted merece.",
                ],
                "cta_text": "Ver disponibilidad",
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign={segment_slug}_{season}_2025",
                "ps_line": f"PD: Como cliente Eurostars, disfruta de condiciones exclusivas en {hotel['name']}.",
            },
            "SENIOR": {
                "subject": f"{hotel['name']} — Su escapada a {hotel['city']}",
                "preheader": f"Un viaje pensado especialmente para usted",
                "headline": f"Le invitamos a descubrir {hotel['city']}",
                "subheadline": f"{hotel['name']} — confort y calidad asegurados",
                "body_paragraphs": [
                    f"Estimado/a viajero/a, nos complace sugerirle una estancia en "
                    f"{hotel['name']}, un hotel de {hotel['stars']} estrellas ubicado "
                    f"en el corazón de {hotel['city']}.",
                    f"Hemos pensado en una estancia de {stay} noches para que pueda "
                    f"disfrutar con tranquilidad de todo lo que este maravilloso "
                    f"destino tiene para ofrecerle.",
                    f"Nuestro equipo estará encantado de atenderle personalmente "
                    f"para cualquier necesidad que pueda tener durante su visita.",
                ],
                "cta_text": "Consultar fechas y precios",
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign={segment_slug}_{season}_2025",
                "ps_line": f"PD: Para reservas telefónicas, llámenos al +34 900 100 200. Estaremos encantados de ayudarle.",
            },
        }
        return copies.get(age, copies["ADULTO"])

    elif moment == "post_stay":
        last = campaign_data["last_stay"]
        next_h = campaign_data.get("recommended_hotel", {})
        next_name = next_h.get("HOTEL_NAME", "un nuevo destino")
        next_city = next_h.get("CITY_NAME", "")

        copies = {
            "JOVEN": {
                "subject": f"¿Ya echas de menos {last['city']}?",
                "preheader": f"Tu estancia en {last['hotel_name']} fue especial",
                "headline": f"Gracias por elegir {last['hotel_name']}",
                "subheadline": f"Tu próxima aventura podría ser {next_city}",
                "body_paragraphs": [
                    f"Del {last['checkin']} al {last['checkout']} viviste algo "
                    f"especial en {last['city']}. Esperamos que cada momento haya "
                    f"sido inolvidable.",
                    f"¿Y si tu próxima escapada es a {next_city}? "
                    f"{next_name} te espera con una oferta exclusiva solo para ti.",
                ],
                "cta_text": f"Descubrir {next_city}",
                "cta_url_suffix": f"utm_source=email&utm_medium=post_stay&utm_campaign={segment_slug}_2025",
                "ps_line": "PD: Reserva en las próximas 48h y consigue un 15% de descuento",
            },
            "ADULTO": {
                "subject": f"Gracias por su estancia en {last['city']}",
                "preheader": f"Su opinión nos importa — y su próximo viaje también",
                "headline": f"Esperamos que haya disfrutado de {last['hotel_name']}",
                "subheadline": f"Su próximo destino ideal: {next_city}",
                "body_paragraphs": [
                    f"Queremos agradecerle su estancia del {last['checkin']} al "
                    f"{last['checkout']} en {last['hotel_name']}, {last['city']}. "
                    f"Esperamos que la experiencia haya cumplido con sus expectativas.",
                    f"Basándonos en sus preferencias, creemos que {next_name} en "
                    f"{next_city} será su próximo destino perfecto. ¿Le gustaría "
                    f"conocer las condiciones especiales que tenemos para usted?",
                ],
                "cta_text": "Ver oferta exclusiva",
                "cta_url_suffix": f"utm_source=email&utm_medium=post_stay&utm_campaign={segment_slug}_2025",
                "ps_line": f"PD: Como cliente Eurostars, disfruta de un 10% de descuento en {next_name}.",
            },
            "SENIOR": {
                "subject": f"Gracias por elegirnos en {last['city']}",
                "preheader": f"Ha sido un placer tenerle con nosotros",
                "headline": f"Gracias por confiar en {last['hotel_name']}",
                "subheadline": f"Su próximo viaje, a su medida",
                "body_paragraphs": [
                    f"Estimado/a cliente, ha sido un verdadero placer recibirle "
                    f"en {last['hotel_name']} del {last['checkin']} al {last['checkout']}. "
                    f"Esperamos que su estancia en {last['city']} haya sido cómoda "
                    f"y agradable en todos los sentidos.",
                    f"Si le apetece seguir viajando, le sugerimos {next_name} "
                    f"en {next_city}, un destino que creemos puede encantarle. "
                    f"Nuestro equipo estará encantado de ayudarle con la reserva.",
                ],
                "cta_text": "Más información",
                "cta_url_suffix": f"utm_source=email&utm_medium=post_stay&utm_campaign={segment_slug}_2025",
                "ps_line": "PD: Puede llamarnos al +34 900 100 200 para reservar cómodamente por teléfono.",
            },
        }
        return copies.get(age, copies["ADULTO"])

    return _default_copy()


def _default_copy() -> dict:
    return {
        "subject": "Eurostars Hotels — Tu próximo viaje",
        "preheader": "Descubre destinos pensados para ti",
        "headline": "Bienvenido a Eurostars",
        "subheadline": "Viajes personalizados para ti",
        "body_paragraphs": ["Descubre nuestros destinos seleccionados."],
        "cta_text": "Ver hoteles",
        "cta_url_suffix": "utm_source=email&utm_medium=generic&utm_campaign=2025",
        "ps_line": "",
    }


def _log_generation_source(source: str, guest_id: str, moment: str) -> None:
    """Mantiene el diagnóstico fuera de stdout sin perder trazabilidad."""
    logger.debug(
        "Copy de email generado vía %s para guest=%s moment=%s",
        source,
        guest_id,
        moment,
    )


def _call_gemini(prompt: str) -> dict:
    """Llama a Gemini vía Vertex AI y devuelve el copy parseado."""
    from backend.ai.gemini import call_gemini

    full_prompt = (
        "Eres un copywriter de alto rendimiento para emails de Eurostars. "
        "Responde únicamente con JSON válido y conciso ajustado al esquema "
        "indicado en las instrucciones.\n\n"
        f"{prompt}"
    )
    result = call_gemini(full_prompt, json_output=True)
    if not isinstance(result, dict):
        raise ValueError("Gemini no disponible o respuesta vacía/invalida")
    return result


def generate_copy(
    campaign_data: dict,
    moment: str,
    dry_run: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Genera el copy de email para una campaña.

    Parámetros
    ----------
    campaign_data : dict
        Payload de campaña tal como lo produce campaign_engine.
    moment : str
        'pre_arrival' o 'post_stay'.
    dry_run : bool
        Si es True, la campaña se mantiene en modo simulación para entrega.
        El copy seguirá siendo mock salvo que ``GEMINI_COPY_IN_DRY_RUN=true``.
    verbose : bool
        Indicador obsoleto que se mantiene por compatibilidad hacia atrás.

    Devuelve
    --------
    dict
        Copy estructurado del email.
    """
    guest_id = str(campaign_data.get("guest_id", "?"))
    use_gemini = (not dry_run) or _env_bool("GEMINI_COPY_IN_DRY_RUN", False)

    if not use_gemini:
        copy = _mock_copy(campaign_data, moment)
        if verbose:
            _log_generation_source("mock", guest_id, moment)
        return copy

    prompt = _build_prompt(campaign_data, moment)

    try:
        copy = _call_gemini(prompt)
        if verbose:
            _log_generation_source("gemini", guest_id, moment)
        return copy

    except Exception as exc:
        logger.warning("Ha fallado la generación con Gemini: %s. Se usará copy simulado.", exc)
        copy = _mock_copy(campaign_data, moment)
        if verbose:
            _log_generation_source("mock", guest_id, moment)
        return copy


def generate_sms(campaign_data: dict, dry_run: bool = True) -> str:
    """Genera un SMS ultracorto para la campaña (máximo 160 caracteres)."""

    if campaign_data.get("campaign_type") == "pre_arrival":
        hotel = campaign_data.get("recommended_hotel", {})
        name = hotel.get("name", "Eurostars")
        city = hotel.get("city", "")
        msg = f"Eurostars: Tu hotel ideal en {city} te espera. {name}. Reserva ahora con -10%: eurostars.com/r"
    else:
        last = campaign_data.get("last_stay", {})
        msg = f"Eurostars: Gracias por tu estancia en {last.get('city', '')}. -15% en tu próximo viaje: eurostars.com/r"

    # Recortar a 160 caracteres
    if len(msg) > 160:
        msg = msg[:157] + "..."
    return msg


def main():
    """
    Comprobación rápida: genera un copy pre-arrival usando la API real
    (usa DRY_RUN=1 para forzar el modo simulado).
    """
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    from backend.campaigns import planner as campaign_engine

    results = campaign_engine.generate_all("pre_arrival", "1014907189")
    if not results:
        logger.warning("No se han obtenido resultados de campaña.")
        return

    copy = generate_copy(results[0], "pre_arrival", dry_run=dry_run, verbose=True)
    sms = generate_sms(results[0])
    logger.info(
        "Se han generado activos de ejemplo para el huésped %s usando el modelo %s",
        results[0].get("guest_id", "?"),
        "mock" if dry_run else "gemini",
    )
    logger.debug("Copy de ejemplo: %s", json.dumps(copy, ensure_ascii=False))
    logger.debug("SMS de ejemplo: %s", sms)
    # print(json.dumps(copy, indent=2, ensure_ascii=False))
    # print(f"\nSMS: {sms}")


if __name__ == "__main__":
    main()
