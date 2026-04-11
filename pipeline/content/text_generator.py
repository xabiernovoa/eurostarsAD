#!/usr/bin/env python3
"""
text_generator.py — Phase 5: AI Text Generation

Generates email copy using the OpenAI API.
Falls back to structured mock copy in dry-run mode.
Produces structured JSON output: subject, preheader, headline, body, CTA, etc.
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

# ── Logging — only WARNING+ to stderr to avoid polluting stdout output ───────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("text_generator")

# ── Model config ─────────────────────────────────────────────────────────────
OPENAI_EMAIL_MODEL = os.environ.get("OPENAI_EMAIL_MODEL", "gpt-5.4-nano")
OPENAI_EMAIL_MAX_OUTPUT_TOKENS = int(
    os.environ.get("OPENAI_EMAIL_MAX_OUTPUT_TOKENS", "320")
)

EMAIL_COPY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "email_copy",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "preheader": {"type": "string"},
                "headline": {"type": "string"},
                "subheadline": {"type": "string"},
                "body_paragraphs": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "cta_text": {"type": "string"},
                "cta_url_suffix": {"type": "string"},
                "ps_line": {"type": "string"},
            },
            "required": [
                "subject",
                "preheader",
                "headline",
                "subheadline",
                "body_paragraphs",
                "cta_text",
                "cta_url_suffix",
                "ps_line",
            ],
            "additionalProperties": False,
        },
    },
}

# ── Tone instructions by age segment ─────────────────────────────────────

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


def _build_prompt(campaign_data: dict, moment: str) -> str:
    """Build the prompt for the AI model."""
    seg = campaign_data["segment"]
    age_segment = seg.get("age_segment", "ADULTO")
    travel_profile = seg.get("travel_profile", "EXPLORADOR_CULTURAL")
    client_value = seg.get("client_value", "MID_VALUE")
    country = seg.get("country", "ES")
    gender = seg.get("gender", "")

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
- Segmento de edad: {age_segment}
- Perfil de viaje: {travel_profile}
- Valor del cliente: {client_value}
- País de origen: {country}
- Género: {gender}
- Puntuación media que da: {seg.get('avg_score', 7)}

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
- Segmento de edad: {age_segment}
- Perfil de viaje: {travel_profile}
- Valor del cliente: {client_value}
- País: {country}

ÚLTIMA ESTANCIA:
- Hotel: {last['hotel_name']}
- Ciudad: {last['city']}
- Check-in: {last['checkin']}
- Check-out: {last['checkout']}

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
    """Generate mock copy without API call (for --dry-run mode)."""
    seg = campaign_data["segment"]
    age = seg.get("age_segment", "ADULTO")

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
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign=joven_{season}_2025",
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
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign=adulto_{season}_2025",
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
                "cta_url_suffix": f"utm_source=email&utm_medium=pre_arrival&utm_campaign=senior_{season}_2025",
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
                "cta_url_suffix": "utm_source=email&utm_medium=post_stay&utm_campaign=joven_2025",
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
                "cta_url_suffix": "utm_source=email&utm_medium=post_stay&utm_campaign=adulto_2025",
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
                "cta_url_suffix": "utm_source=email&utm_medium=post_stay&utm_campaign=senior_2025",
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
    """Keep generation diagnostics off stdout while preserving traceability."""
    logger.debug(
        "Generated email copy via %s for guest=%s moment=%s",
        source,
        guest_id,
        moment,
    )


def _call_openai(prompt: str) -> dict:
    """Call the OpenAI API and return parsed JSON copy."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = OpenAI(api_key=api_key)
    request = {
        "model": OPENAI_EMAIL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un copywriter de alto rendimiento para emails de Eurostars. "
                    "Responde solo con JSON válido y conciso."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": EMAIL_COPY_SCHEMA,
        "max_completion_tokens": OPENAI_EMAIL_MAX_OUTPUT_TOKENS,
    }

    try:
        response = client.chat.completions.create(**request)
    except TypeError:
        request.pop("max_completion_tokens", None)
        response = client.chat.completions.create(**request)

    message = response.choices[0].message
    refusal = getattr(message, "refusal", None)
    if refusal:
        raise ValueError(f"OpenAI refusal: {refusal}")

    raw = message.content or "{}"
    return json.loads(raw)


def generate_copy(
    campaign_data: dict,
    moment: str,
    dry_run: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Generate email copy for a campaign.

    Parameters
    ----------
    campaign_data : dict
        Campaign payload as produced by campaign_engine.
    moment : str
        'pre_arrival' or 'post_stay'.
    dry_run : bool
        If True, skips the API call and returns deterministic mock copy.
    verbose : bool
        Deprecated flag kept for backward compatibility.

    Returns
    -------
    dict
        Structured email copy.
    """
    guest_id = str(campaign_data.get("guest_id", "?"))

    if dry_run:
        copy = _mock_copy(campaign_data, moment)
        if verbose:
            _log_generation_source("mock", guest_id, moment)
        return copy

    # ── Validate API key ──────────────────────────────────────────────────
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-xxxxx"):
        logger.warning(
            "OPENAI_API_KEY no configurada o es un placeholder; usando mock copy."
        )
        copy = _mock_copy(campaign_data, moment)
        if verbose:
            _log_generation_source("mock", guest_id, moment)
        return copy

    prompt = _build_prompt(campaign_data, moment)

    try:
        copy = _call_openai(prompt)
        if verbose:
            _log_generation_source(f"openai:{OPENAI_EMAIL_MODEL}", guest_id, moment)
        return copy

    except Exception as exc:
        logger.warning("OpenAI email generation failed: %s. Using mock copy.", exc)
        copy = _mock_copy(campaign_data, moment)
        if verbose:
            _log_generation_source("mock", guest_id, moment)
        return copy


def generate_sms(campaign_data: dict, dry_run: bool = True) -> str:
    """Generate ultra-short SMS copy (max 160 chars)."""
    seg = campaign_data.get("segment", {})

    if campaign_data.get("campaign_type") == "pre_arrival":
        hotel = campaign_data.get("recommended_hotel", {})
        name = hotel.get("name", "Eurostars")
        city = hotel.get("city", "")
        msg = f"Eurostars: Tu hotel ideal en {city} te espera. {name}. Reserva ahora con -10%: eurostars.com/r"
    else:
        last = campaign_data.get("last_stay", {})
        msg = f"Eurostars: Gracias por tu estancia en {last.get('city', '')}. -15% en tu próximo viaje: eurostars.com/r"

    # Truncate to 160 chars
    if len(msg) > 160:
        msg = msg[:157] + "..."
    return msg


def main():
    """
    Quick sanity-check: generates one pre-arrival copy using the real API
    (set DRY_RUN=1 to force mock mode).
    """
    dry_run = os.environ.get("DRY_RUN", "0") == "1"

    from pipeline.campaigns import campaign_engine

    results = campaign_engine.generate_all("pre_arrival", "1014907189")
    if not results:
        logger.warning("No campaign results returned.")
        return

    copy = generate_copy(results[0], "pre_arrival", dry_run=dry_run, verbose=True)
    sms = generate_sms(results[0])
    logger.info(
        "Generated sample assets for guest %s using model %s",
        results[0].get("guest_id", "?"),
        OPENAI_EMAIL_MODEL if not dry_run else "mock",
    )
    logger.debug("Sample copy: %s", json.dumps(copy, ensure_ascii=False))
    logger.debug("Sample sms: %s", sms)
    # print(json.dumps(copy, indent=2, ensure_ascii=False))
    # print(f"\nSMS: {sms}")


if __name__ == "__main__":
    main()
