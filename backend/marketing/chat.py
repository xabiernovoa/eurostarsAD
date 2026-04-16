#!/usr/bin/env python3
"""
chat_engine.py — Asistente de IA para marketing.

Agente conversacional con acceso completo a los datos del dashboard.
Usa Gemini vía Vertex AI cuando está disponible y, si no, recurre
a un motor heurístico contextual.
"""

from __future__ import annotations

import json
import logging
import re
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

from backend.marketing.dashboard import build_dashboard_data

load_dotenv()

logger = logging.getLogger("marketing_chat")

# Caché del dashboard para evitar reconstruirlo en cada mensaje
_dashboard_cache: dict | None = None

CAMPAIGN_CREATE_PATTERNS = (
    "genera una campaña",
    "genera campaña",
    "crear una campaña",
    "crea una campaña",
    "haz una campaña",
    "diseña una campaña",
    "proponme una campaña",
    "propón una campaña",
    "quiero una campaña",
    "necesito una campaña",
    "ayúdame con una campaña",
    "monta una campaña",
    "prepara una campaña",
)

OBJECTIVE_HINTS = {
    "upsell": ("upsell", "late checkout", "upgrade", "mejora de habitación", "spa", "desayuno", "parking"),
    "reserva directa": ("reserva directa", "captación", "captar", "booking", "bookings", "conversion", "conversión"),
    "fidelización": ("fidelización", "fidelizacion", "retención", "retencion", "repetición", "repeat", "loyalty"),
    "branding": ("branding", "awareness", "notoriedad", "visibilidad", "marca"),
    "reactivación": ("reactivación", "reactivacion", "reactivar", "winback", "recuperar"),
    "evento": ("evento", "festival", "concierto", "feria", "paquete evento"),
}

CHANNEL_HINTS = {
    "email": ("email", "correo", "newsletter", "mail"),
    "sms": ("sms",),
    "push": ("push", "notificación", "notificacion"),
    "whatsapp": ("whatsapp",),
    "rrss": ("instagram", "tiktok", "rrss", "redes", "social", "reels", "stories"),
    "paid": ("google ads", "meta ads", "ads", "paid", "display"),
    "in-hotel": ("recepción", "recepcion", "check-in", "checkin", "lobby", "hotel", "mostrador"),
}

MOMENT_HINTS = {
    "pre-arrival": ("pre-arrival", "pre arrival", "antes de la llegada", "antes de llegar", "pre estancia"),
    "post-stay": ("post-stay", "post stay", "después de la estancia", "despues de la estancia", "post estancia"),
    "check-in": ("check-in", "checkin", "llegada", "durante la estancia", "in-house", "in house"),
}

SEGMENT_HINTS = (
    ("familias", ("familia", "familias", "niños", "ninos")),
    ("jóvenes", ("joven", "jóvenes", "jovenes", "millennial", "gen z")),
    ("adultos", ("adulto", "adultos")),
    ("senior", ("senior", "mayores", "+65", "65+")),
    ("perfil lujo", ("lujo", "premium", "vip", "high value")),
    ("perfil cultural", ("cultural", "explorador cultural", "museos", "patrimonio")),
    ("perfil aventurero", ("aventurero", "aventura", "naturaleza")),
    ("perfil gastronómico", ("gastronom", "foodie", "restaurante", "gastro")),
)


def _get_dashboard() -> dict:
    global _dashboard_cache
    if _dashboard_cache is None:
        _dashboard_cache = build_dashboard_data()
    return _dashboard_cache


def refresh_dashboard_cache() -> None:
    global _dashboard_cache
    _dashboard_cache = None


def _conversation_text(message: str, history: list[dict] | None = None) -> str:
    history = history or []
    parts = [entry.get("content", "") for entry in history[-10:] if entry.get("role") == "user"]
    parts.append(message)
    return " ".join(parts).lower()


def _contains_any(text: str, needles: tuple[str, ...] | list[str]) -> bool:
    return any(needle in text for needle in needles)


def _is_campaign_creation_request(message: str, history: list[dict] | None = None) -> bool:
    text = _conversation_text(message, history)
    if _contains_any(text, CAMPAIGN_CREATE_PATTERNS):
        return True
    return "campaña" in text and _contains_any(
        text,
        ("genera", "crear", "crea", "haz", "diseña", "propon", "propón", "quiero", "necesito", "prepara"),
    )


def _extract_campaign_brief(message: str, history: list[dict] | None, dashboard: dict) -> dict:
    text = _conversation_text(message, history)
    segment_cards = ((dashboard.get("segment_rankings") or {}).get("by_size") or [])
    focus_cities = [item.get("city", "") for item in ((dashboard.get("signal_facts") or {}).get("cities") or [])]

    objective = None
    for label, hints in OBJECTIVE_HINTS.items():
        if _contains_any(text, hints):
            objective = label
            break

    channel = None
    for label, hints in CHANNEL_HINTS.items():
        if _contains_any(text, hints):
            channel = label
            break

    moment = None
    for label, hints in MOMENT_HINTS.items():
        if _contains_any(text, hints):
            moment = label
            break

    segment = None
    for card in segment_cards:
        label = str(card.get("segment_label", "")).strip()
        if label and label.lower() in text:
            segment = label
            break
    if not segment:
        matched_segments = [label for label, hints in SEGMENT_HINTS if _contains_any(text, hints)]
        if matched_segments:
            segment = " + ".join(matched_segments[:2])

    destination = None
    known_cities = list(dict.fromkeys(focus_cities + ["Madrid", "Sevilla", "Roma", "Lisboa", "Oporto", "Granada", "El Grove"]))
    for city in known_cities:
        if city and city.lower() in text:
            destination = city
            break

    timing = None
    timing_match = re.search(
        r"(este fin de semana|la semana que viene|este mes|el mes que viene|navidad|verano|invierno|primavera|otoño|otono|black friday|puente)",
        text,
    )
    if timing_match:
        timing = timing_match.group(1)

    return {
        "objective": objective,
        "segment": segment,
        "channel": channel,
        "moment": moment,
        "destination": destination,
        "timing": timing,
    }


def _missing_campaign_brief_fields(brief: dict) -> list[str]:
    missing = []
    if not brief.get("objective"):
        missing.append("objetivo")
    if not brief.get("segment"):
        missing.append("público")
    if not (brief.get("channel") or brief.get("moment")):
        missing.append("canal/momento")
    if not (brief.get("destination") or brief.get("timing")):
        missing.append("destino/timing")
    return missing


def _campaign_clarification_reply(brief: dict) -> str | None:
    missing = _missing_campaign_brief_fields(brief)
    known_lines = []
    if brief.get("objective"):
        known_lines.append(f"- Objetivo: {brief['objective']}")
    if brief.get("segment"):
        known_lines.append(f"- Público: {brief['segment']}")
    if brief.get("channel"):
        known_lines.append(f"- Canal: {brief['channel']}")
    if brief.get("moment"):
        known_lines.append(f"- Momento: {brief['moment']}")
    if brief.get("destination"):
        known_lines.append(f"- Destino: {brief['destination']}")
    if brief.get("timing"):
        known_lines.append(f"- Timing: {brief['timing']}")

    enough_context = len([v for v in brief.values() if v]) >= 3 and len(missing) <= 1
    if enough_context:
        return None

    reply = "Perfecto, la aterrizo contigo. Para no devolverte una campaña genérica, necesito cerrar un poco más el brief."
    if known_lines:
        reply += "\n\nAhora mismo te he entendido esto:\n" + "\n".join(known_lines)

    questions = []
    if "objetivo" in missing:
        questions.append("- Qué quieres mover exactamente: reserva directa, upsell, fidelización, branding o reactivación.")
    if "público" in missing:
        questions.append("- A quién va dirigida: segmento, perfil o tipo de cliente.")
    if "canal/momento" in missing:
        questions.append("- En qué canal y momento la quieres activar: email, SMS, push, RRSS, pre-arrival, post-stay o in-hotel.")
    if "destino/timing" in missing:
        questions.append("- Sobre qué destino o ventana temporal la planteamos: ciudad, hotel, fin de semana, campaña estacional, etc.")

    reply += "\n\nRespóndeme a esto y te la monto:\n" + "\n".join(questions[:4])
    reply += (
        "\n\nSi te resulta más cómodo, puedes contestarme en una sola línea. "
        "Ejemplo: \"Quiero una campaña de upsell para senior cultural por email pre-arrival en Sevilla para mayo\"."
    )
    return reply


def _heuristic_campaign_reply(brief: dict, dashboard: dict) -> str:
    top_segment = ((dashboard.get("segment_rankings") or {}).get("by_size") or [{}])[0]
    top_hotel = (dashboard.get("top_hotels") or [{}])[0]

    objective = brief.get("objective") or "activación comercial"
    segment = brief.get("segment") or top_segment.get("segment_label", "segmento prioritario")
    channel = brief.get("channel") or "email"
    moment = brief.get("moment") or "pre-arrival"
    destination = brief.get("destination") or top_hotel.get("hotel", "destino prioritario")
    timing = brief.get("timing") or "las próximas 2 semanas"

    return (
        "Perfecto. Con lo que me has dado, te propongo esta campaña. Esto es una sugerencia asistida, no un dato observado.\n\n"
        f"- Objetivo: {objective}\n"
        f"- Público: {segment}\n"
        f"- Canal: {channel}\n"
        f"- Momento: {moment}\n"
        f"- Destino/timing: {destination} · {timing}\n\n"
        "Concepto:\n"
        f"Lanzar una campaña centrada en {destination} para empujar {objective}, con una propuesta muy clara de valor "
        f"y una creatividad adaptada a {segment}.\n\n"
        "Bajada táctica:\n"
        f"- Mensaje principal: beneficio concreto y accionable para ese público.\n"
        f"- Activación: salida en {channel} con ventana {moment} durante {timing}.\n"
        f"- CTA: una sola acción prioritaria, sin fricción.\n"
        f"- KPI a vigilar: clics hacia la landing, reservas directas atribuidas y uso de la oferta propuesta.\n\n"
        "Si quieres, en el siguiente mensaje te la convierto ya en una versión completa con asunto, preview, cuerpo y rationale."
    )


def _build_system_prompt(dashboard: dict) -> str:
    """Construye el prompt de sistema con todo el contexto del dashboard."""
    context = dashboard.get("context", {})
    overview = dashboard.get("overview_facts", {})
    audience = dashboard.get("audience_facts", {})
    channels = dashboard.get("channel_distribution", [])
    moments = dashboard.get("moment_distribution", [])
    top_hotels = dashboard.get("top_hotels", [])
    signal_facts = dashboard.get("signal_facts", {})
    segment_rankings = dashboard.get("segment_rankings", {})
    recent_messages = dashboard.get("recent_messages", [])
    focus_cities = [item.get("city", "") for item in (signal_facts.get("cities") or []) if item.get("city")]

    recent_json = json.dumps(
        [
            {
                "type": c.get("campaign_type"),
                "segment": c.get("segment_label"),
                "channel": c.get("channel"),
                "hotel": c.get("hotel"),
                "subject": c.get("subject"),
            }
            for c in recent_messages[:6]
        ],
        ensure_ascii=False,
    )

    return f"""Eres el director de estrategia de marketing de Eurostars Hotel Company.
Tienes acceso completo a los datos operativos de campañas, segmentación de clientes y señales del mercado.
Responde siempre en español. Sé directo, concreto y profesional. No uses emojis.
Cuando propongas acciones, deben ser específicas y ejecutables.
Cuando analices datos, cita números concretos del dashboard.
No presentes métricas sintéticas como si fueran datos observados. Si hablas de propuestas, deja claro que son sugerencias asistidas.

CONTEXTO ESTRATÉGICO:
- Prioridad actual: {context.get('strategic_priority', 'Sin definir')}
- Notas del jefe de marketing: {json.dumps(context.get('manager_notes', []), ensure_ascii=False)}
- Señales de recepción: {json.dumps(context.get('reception_notes', []), ensure_ascii=False)}
- Señales externas: {json.dumps(context.get('external_signals', []), ensure_ascii=False)}

HECHOS DEL DASHBOARD:
- Usuarios segmentados: {overview.get('guest_count', 0)}
- Piezas registradas en log: {overview.get('message_count', 0)}
- Países en la base: {overview.get('country_count', 0)}
- Hoteles distintos recomendados: {overview.get('hotel_count', 0)}
- Eventos e insights externos activos: {overview.get('signal_count', 0)}

CIUDADES EN FOCO: {', '.join(focus_cities)}

MIX DE CANALES:
{json.dumps(channels, ensure_ascii=False)}

MOMENTOS DEL VIAJE:
{json.dumps(moments, ensure_ascii=False)}

HOTELES MÁS RECOMENDADOS:
{json.dumps(top_hotels[:6], ensure_ascii=False)}

EVENTOS E INSIGHTS ACTIVOS:
{json.dumps(signal_facts, ensure_ascii=False)}

AUDIENCIA:
{json.dumps(audience, ensure_ascii=False)}

SEGMENTOS POR TAMAÑO:
{json.dumps((segment_rankings.get('by_size') or [])[:6], ensure_ascii=False)}

SEGMENTOS POR ADR:
{json.dumps((segment_rankings.get('by_adr') or [])[:6], ensure_ascii=False)}

CAMPAÑAS RECIENTES (últimas 6):
{recent_json}
"""


# ── Heuristic fallback engine ────────────────────────────────

def _detect_intent(message: str) -> str:
    """Detect the user's intent from their message."""
    msg = message.lower().strip()

    if any(w in msg for w in ["analizar", "análisis", "analiza", "situación", "estado", "cómo va", "resumen", "overview"]):
        return "analysis"
    if any(w in msg for w in ["evento", "eventos", "insight", "insights", "contexto", "señal", "señales"]):
        return "destinations"
    if any(w in msg for w in ["segmento", "audiencia", "perfil", "joven", "adulto", "senior", "lujo", "cultural", "aventurero", "gastro"]):
        return "segment"
    if any(w in msg for w in ["instagram", "tiktok", "redes", "rrss", "social", "contenido", "reels", "stories"]):
        return "social_media"
    if any(w in msg for w in ["hotel", "recepción", "lobby", "check-in", "checkin", "upsell", "upgrade"]):
        return "hotel_actions"
    if any(w in msg for w in ["campaña", "publicidad", "ads", "anuncio", "paid", "inversión", "presupuesto", "google", "meta"]):
        return "advertising"
    if any(w in msg for w in ["canal", "email", "sms", "push", "mix"]):
        return "channel_mix"
    if any(w in msg for w in ["ciudad", "destino", "lisboa", "sevilla", "madrid", "roma", "oporto", "granada"]):
        return "destinations"
    if any(w in msg for w in ["idea", "proponer", "sugerir", "sugiere", "nueva", "nuevo", "creativa", "innovar"]):
        return "new_ideas"
    if any(w in msg for w in ["peor", "bajo", "problema", "mejorar", "débil", "riesgo"]):
        return "weak_spots"
    if any(w in msg for w in ["mejor", "top", "fuerte", "éxito", "oportunidad"]):
        return "top_performers"

    return "general"


def _heuristic_reply(message: str, dashboard: dict) -> str:
    """Genera una respuesta contextual con datos del dashboard sin usar API de IA."""
    intent = _detect_intent(message)
    overview = dashboard.get("overview_facts", {})
    context = dashboard.get("context", {})
    channels = dashboard.get("channel_distribution", [])
    moments = dashboard.get("moment_distribution", [])
    top_hotels = dashboard.get("top_hotels", [])
    signal_facts = dashboard.get("signal_facts", {})
    segment_rankings = dashboard.get("segment_rankings", {})
    audience_facts = dashboard.get("audience_facts", {})

    segments_by_size = segment_rankings.get("by_size", [])
    segments_by_adr = segment_rankings.get("by_adr", [])
    countries = audience_facts.get("by_country", [])
    values = audience_facts.get("by_value", [])
    biggest_segment = segments_by_size[0] if segments_by_size else {}
    top_adr_segment = segments_by_adr[0] if segments_by_adr else {}
    top_hotel = top_hotels[0] if top_hotels else {}
    top_country = countries[0] if countries else {}

    if intent == "analysis":
        return (
            "Situación actual del dashboard:\n\n"
            f"- Usuarios segmentados: {overview.get('guest_count', 0)}\n"
            f"- Piezas registradas en el log: {overview.get('message_count', 0)}\n"
            f"- Países en la base: {overview.get('country_count', 0)}\n"
            f"- Hoteles distintos recomendados: {overview.get('hotel_count', 0)}\n"
            f"- Eventos e insights externos activos: {overview.get('signal_count', 0)}\n\n"
            f"El segmento más grande ahora es {biggest_segment.get('segment_label', 'N/A')} "
            f"con {biggest_segment.get('users', 0)} usuarios y ADR medio de {round(biggest_segment.get('avg_adr', 0))}€.\n\n"
            f"El segmento con mayor ADR es {top_adr_segment.get('segment_label', 'N/A')} "
            f"con {top_adr_segment.get('users', 0)} usuarios y ADR medio de {round(top_adr_segment.get('avg_adr', 0))}€.\n\n"
            f"El hotel recomendado con más presencia en el log es {top_hotel.get('hotel', 'N/A')} "
            f"con {top_hotel.get('count', 0)} piezas.\n\n"
            f"Prioridad estratégica: {context.get('strategic_priority', 'Sin definir')}."
        )

    if intent == "segment":
        lines = ["Desglose de segmentos prioritarios:\n"]
        for seg in segments_by_size[:5]:
            lines.append(
                f"- {seg['segment_label']}: {seg['users']} usuarios, "
                f"ADR medio {round(seg['avg_adr'])}€, lead time medio {seg['avg_leadtime']} días, "
                f"canal dominante: {seg.get('top_channel', 'N/A')}"
            )
        premium = [s for s in values if s["label"] in {"Premium", "Lujo"}]
        if premium:
            lines.append(
                f"\nEn la base actual hay {sum(item['count'] for item in premium)} usuarios de valor Premium o Lujo."
            )
        return "\n".join(lines)

    if intent == "social_media":
        cities = signal_facts.get("cities", [])
        city_names = [item["city"] for item in cities[:3]]
        return (
            "Propuesta de trabajo para redes sociales:\n\n"
            "- Crear una línea de contenido sobre experiencia local y no solo sobre habitación.\n"
            f"- Priorizar los segmentos más grandes: {', '.join(seg['segment_label'] for seg in segments_by_size[:3]) or 'segmentos principales'}.\n"
            f"- Conectar el contenido con los eventos e insights activos en {', '.join(city_names) or 'las ciudades activas'}.\n"
            f"- Reutilizar como base visual los hoteles con más presencia en el log: {', '.join(item['hotel'] for item in top_hotels[:3]) or 'los hoteles principales'}.\n\n"
            "Esto es una sugerencia asistida para planificación, no un dato observado."
        )

    if intent == "hotel_actions":
        reception = context.get("reception_notes", [])
        return (
            "Propuesta de acciones dentro del hotel:\n\n"
            "- Preparar scripts de recepción para upgrade, late checkout y experiencias locales.\n"
            "- Alinear el mensaje pre-arrival con lo que recepción puede vender realmente.\n"
            f"- Concentrar el esfuerzo primero en los hoteles con más actividad del log: {', '.join(item['hotel'] for item in top_hotels[:3]) or 'los hoteles más activos'}.\n\n"
            "Observaciones actuales de recepción:\n" +
            "\n".join(f"- {r}" for r in reception) +
            "\n\nEsto es una recomendación operativa, no una métrica observada."
        )

    if intent == "advertising":
        city_names = [item["city"] for item in signal_facts.get("cities", [])[:3]]
        return (
            "Propuesta de publicidad externa:\n\n"
            f"- Priorizar ciudades con contexto activo: {', '.join(city_names) or 'las ciudades con eventos o insights activos'}.\n"
            f"- Construir audiencias a partir de los segmentos más grandes: {', '.join(seg['segment_label'] for seg in segments_by_size[:2]) or 'segmentos principales'}.\n"
            f"- Si buscas margen, vigilar especialmente segmentos de mayor ADR como {top_adr_segment.get('segment_label', 'los segmentos premium')}.\n"
            f"- Separar campañas de captación y campañas de remarketing para medirlas mejor.\n\n"
            "Esto es una sugerencia de planificación, no un resultado medido del canal."
        )

    if intent == "channel_mix":
        lines = ["Análisis del mix de canales:\n"]
        for channel in channels:
            lines.append(f"- {channel['label']}: {channel['count']} piezas ({round(channel['share'] * 100)}%)")
        lines.append(
            "\nEste bloque describe volumen del log. No implica rendimiento real de aperturas, clics o conversión."
        )
        return "\n".join(lines)

    if intent == "destinations":
        lines = ["Destinos y contexto activo:\n"]
        if top_hotels:
            lines.append("Hoteles más presentes en el log:")
            for hotel in top_hotels[:5]:
                lines.append(f"- {hotel['hotel']}: {hotel['count']} piezas")
        if signal_facts.get("signals"):
            lines.append("\nEventos e insights externos:")
            for signal in signal_facts["signals"]:
                lines.append(f"- {signal['text']}")
        return "\n".join(lines)

    if intent == "new_ideas":
        city_names = [item["city"] for item in signal_facts.get("cities", [])[:2]]
        return (
            "Ideas de campaña basadas en el dashboard actual:\n\n"
            f"1. Campaña de reserva directa para {segments_by_size[0]['segment_label'] if segments_by_size else 'el segmento principal'}:\n"
            "   - Mensaje centrado en beneficio concreto y experiencia local.\n"
            "   - Canal sugerido: email o paid social según objetivo.\n\n"
            f"2. Activación vinculada a contexto activo en {', '.join(city_names) or 'las ciudades con eventos'}:\n"
            "   - Combinar contenido de destino, oferta hotelera y CTA único.\n\n"
            f"3. Propuesta premium para {top_adr_segment.get('segment_label', 'segmentos de mayor ADR')}:\n"
            "   - Upsell de experiencia, upgrade o pack exclusivo.\n\n"
            "4. Trabajo coordinado marketing + recepción:\n"
            "   - Mismo mensaje antes de la llegada y en el momento del check-in.\n\n"
            "Todo lo anterior son sugerencias asistidas para ideación."
        )

    if intent == "weak_spots":
        lines = ["Puntos débiles detectados:\n"]
        if overview.get("rows_without_hotel", 0):
            lines.append(
                f"- Hay {overview.get('rows_without_hotel', 0)} piezas sin hotel recomendado en el log."
            )
        checkin = next((item for item in moments if item.get("key") == "checkin_report"), None)
        poststay = next((item for item in moments if item.get("key") == "post_stay"), None)
        if checkin and checkin.get("without_hotel", 0):
            lines.append("- El bloque de recepción no arrastra hotel recomendado en el dataset actual.")
        if poststay and poststay.get("without_hotel", 0):
            lines.append("- El bloque de postestancia tampoco arrastra hotel recomendado.")
        if not signal_facts.get("signals"):
            lines.append("- No hay eventos o insights externos cargados en contexto.")
        lines.append(
            "\nRecomendaciones para mejorar:\n"
            "- Completar mejor el dato de hotel en todas las piezas si quieres comparar destinos con más rigor.\n"
            "- Mantener actualizado el contexto externo para que el generador y el chat sean más útiles.\n"
            "- Separar siempre métricas observadas de sugerencias asistidas."
        )
        return "\n".join(lines)

    if intent == "top_performers":
        lines = ["Segmentos con mejor rendimiento:\n"]
        for seg in segments_by_size[:3]:
            lines.append(
                f"- {seg['segment_label']}: {seg['users']} usuarios, ADR medio {round(seg['avg_adr'])}€, canal dominante {seg.get('top_channel', 'N/A')}"
            )
        if top_hotels:
            lines.append("\nHoteles más presentes en el log:")
            for hotel in top_hotels[:3]:
                lines.append(f"- {hotel['hotel']}: {hotel['count']} piezas")
        lines.append(
            "\nOportunidad: concentrar primero el trabajo de activación en los segmentos más grandes y en los hoteles con más volumen registrado."
        )
        return "\n".join(lines)

    # General fallback
    return (
        f"Estoy aquí para ayudarte con la estrategia de marketing. Puedo:\n\n"
        f"- Resumir el estado actual del dashboard con datos reales\n"
        f"- Desglosar segmentos, canales, hoteles y contexto activo\n"
        f"- Señalar huecos de dato o inconsistencias operativas\n"
        f"- Proponer campañas o acciones como sugerencias asistidas\n\n"
        f"Datos actuales: {overview.get('message_count', 0)} piezas en el log, "
        f"{overview.get('guest_count', 0)} usuarios segmentados y "
        f"{overview.get('signal_count', 0)} eventos o insights externos activos."
    )


# ── Gemini engine (vía backend.ai.gemini) ─────────────

def _gemini_reply(message: str, history: list[dict], dashboard: dict) -> str | None:
    """Responde al chat de marketing usando Gemini vía Vertex AI."""
    try:
        from backend.ai.gemini import call_gemini, is_available
    except ModuleNotFoundError:
        return None

    if not is_available():
        return None

    system_prompt = _build_system_prompt(dashboard)
    is_campaign_request = _is_campaign_creation_request(message, history)
    campaign_brief = _extract_campaign_brief(message, history, dashboard) if is_campaign_request else {}

    # Gemini no tiene rol "system" separado → lo inyectamos en el prompt.
    conversation = f"INSTRUCCIONES DEL SISTEMA:\n{system_prompt}\n\n"
    if is_campaign_request:
        conversation += (
            "INSTRUCCIÓN ADICIONAL:\n"
            "Si el usuario está construyendo una campaña concreta y ya hay suficiente contexto, "
            "devuelve una propuesta cerrada y accionable. Si aún faltan datos críticos, no improvises: "
            "haz entre 1 y 3 preguntas muy concretas para cerrar el brief.\n"
            f"BRIEF DETECTADO: {json.dumps(campaign_brief, ensure_ascii=False)}\n\n"
        )
    conversation += "HISTORIAL DE CONVERSACIÓN:\n"
    for entry in history[-10:]:
        role = "USUARIO" if entry.get("role") == "user" else "ASISTENTE"
        conversation += f"{role}: {entry.get('content', '')}\n"
    conversation += f"\nUSUARIO: {message}\nASISTENTE:"

    reply = call_gemini(conversation, json_output=False)
    if not reply:
        return None
    return str(reply).strip() or None


# ── Generador de propuestas de campaña ───────────────────────

def _generate_heuristic_proposals(dashboard: dict) -> list[dict]:
    """Genera propuestas de campaña diversas para todos los canales de marketing."""
    segments = ((dashboard.get("segment_rankings") or {}).get("by_size") or [])
    high_adr_segments = ((dashboard.get("segment_rankings") or {}).get("by_adr") or [])
    context = dashboard.get("context", {})
    overview = dashboard.get("overview_facts", {})
    top_hotels = dashboard.get("top_hotels", [])
    audience = dashboard.get("audience_facts", {})
    signal_facts = dashboard.get("signal_facts", {})
    external = context.get("external_signals", [])
    reception = context.get("reception_notes", [])

    proposals = []
    signal_cities = [item.get("city", "") for item in (signal_facts.get("cities") or []) if item.get("city")]
    city1 = signal_cities[0] if signal_cities else "destino principal"
    city2 = signal_cities[1] if len(signal_cities) >= 2 else "destino secundario"
    hotel1 = (top_hotels[0] or {}).get("hotel") if top_hotels else "hotel prioritario"
    hotel2 = (top_hotels[1] or {}).get("hotel") if len(top_hotels) >= 2 else hotel1
    top_seg = segments[0] if segments else {}
    cultural_seg = next((s for s in segments if "Cultural" in str(s.get("segment_label", ""))), segments[0] if segments else {})
    premium_seg = next((s for s in high_adr_segments if s.get("users", 0) >= 3), high_adr_segments[0] if high_adr_segments else top_seg)
    country_top = ((audience.get("by_country") or [{}])[0]).get("label", "la base principal")
    message_count = overview.get("message_count", 0)
    guest_count = overview.get("guest_count", 0)

    # ── 1. RRSS: Serie de contenido ──────────────────────────
    proposals.append({
        "id": "camp-001",
        "category": "rrss",
        "category_label": "Redes sociales",
        "name": f"Serie «Vive como un local» — {city1}",
        "objective": "Awareness orgánico y tráfico a web de reserva directa",
        "segment": cultural_seg.get("segment_label", "Cultural"),
        "segment_users": cultural_seg.get("users", 0),
        "channel": "Instagram + TikTok",
        "campaign_type": "contenido_rrss",
        "timing": "4 semanas · 3 piezas/semana",
        "subject_line": "Descubre el barrio como un vecino",
        "preview_text": "Formato: Reels 30-60s y carruseles con rutas de barrio, restaurantes locales y detrás de cámaras del hotel.",
        "body_summary": (
            f"Serie de contenido visual para Instagram Reels y TikTok centrada en la vida local de {city1}. "
            f"3 pilares de contenido: 1) Ruta a pie por el barrio del hotel (60s), 2) Restaurante local con plato estrella (30s), "
            f"3) Behind-the-scenes del hotel y del destino: rooftop, cocina, preparación de habitación premium y ambientación local. "
            f"Cada pieza incluye CTA en bio hacia landing de reserva directa. Colaborar con micro-influencer local (5K-20K seguidores) para la serie."
        ),
        "deliverables": "12 Reels, 4 carruseles, 1 highlight permanente, 4 stories interactivas",
        "priority": "alta",
        "rationale": (
            f"Encaja con el peso del segmento {cultural_seg.get('segment_label', 'cultural')} "
            f"({cultural_seg.get('users', 0)} usuarios en la base) y con el contexto activo en {city1}."
        ),
    })

    # ── 2. Hotel: Decoración y señalización ──────────────────
    proposals.append({
        "id": "camp-002",
        "category": "hotel",
        "category_label": "Acción en hotel",
        "name": f"Rediseño de señalización y experiencia en {hotel1}",
        "objective": "Mejorar percepción de marca y facilitar upselling en el hotel",
        "segment": "Todos los huéspedes in-house",
        "segment_users": guest_count,
        "channel": "Físico / in-hotel",
        "campaign_type": "hotel_insite",
        "timing": "Implementación en 3-4 semanas",
        "subject_line": "Programa de experiencia en hotel",
        "preview_text": "QR interactivos, decoración temática estacional y materiales de upsell en puntos clave del hotel.",
        "body_summary": (
            f"Rediseño de la experiencia física dentro de {hotel1}: "
            f"1) QR en caballete de recepción: lleva a landing con experiencias locales reservables (rutas, restaurantes, late checkout). "
            f"2) Decoración estacional en lobby: fotografía gran formato de la ciudad con narrativa 'Eurostars te conecta con la ciudad'. "
            f"3) Tarjetas en habitación con recomendaciones de barrio personalizadas por perfil (aventurero, cultural, gastronómico). "
            f"4) Pantalla digital en ascensor con ofertas de upgrade y actividades del día. "
            f"5) Display en recepción con objetos de artesanía local, reforzando la conexión con el destino."
        ),
        "deliverables": "Diseño de QR + landing, 3 formatos de cartelería, tarjetas habitación (3 versiones), contenido pantalla",
        "priority": "alta",
        "rationale": (
            f"Recepción ya está aportando observaciones útiles ({len(reception)} activas) y "
            f"{hotel1} es uno de los hoteles con más presencia en el log."
        ),
    })

    # ── 3. Localización: Partnerships locales ────────────────
    proposals.append({
        "id": "camp-003",
        "category": "local",
        "category_label": "Localización",
        "name": f"Programa de partnerships locales — {city1}",
        "objective": "Crear experiencias diferenciales y contenido auténtico",
        "segment": premium_seg.get("segment_label", "Segmentos de alto valor"),
        "segment_users": premium_seg.get("users", 0),
        "channel": "Presencial + digital",
        "campaign_type": "local_partnership",
        "timing": "Activo de mayo a septiembre",
        "subject_line": f"Alianzas locales en {city1}",
        "preview_text": "Acuerdos con restaurantes, bodegas y galerías locales para crear paquetes exclusivos Eurostars.",
        "body_summary": (
            f"Crear una red de partnerships locales en {city1}: "
            f"1) 3 restaurantes con menú «Selección Eurostars» con descuento para huéspedes (exposición cruzada en ambas marcas). "
            f"2) Bodega/cata de vinos con visita privada para huéspedes premium y de alto valor. "
            f"3) Galería de arte o taller de artesanía local: experiencia reservable desde el QR de habitación. "
            f"4) Ruta guiada a pie con guía local, exclusiva para huéspedes (sábados por la mañana). "
            f"Todos los partners deben generar contenido co-branded para RRSS (mínimo 2 posts/mes cada uno). "
            f"Medir: reservas de experiencias, menciones en RRSS, NPS incremento."
        ),
        "deliverables": "3-5 acuerdos firmados, kit co-branding, landing experiencias, material para partners",
        "priority": "alta",
        "rationale": (
            f"Se apoya en segmentos con ADR alto como {premium_seg.get('segment_label', 'los perfiles premium')} "
            f"y en destinos con contexto activo como {city1}."
        ),
    })

    # ── 4. Branding: Imagen corporativa ──────────────────────
    proposals.append({
        "id": "camp-004",
        "category": "branding",
        "category_label": "Imagen corporativa",
        "name": "Refresh visual de temporada Eurostars",
        "objective": "Actualizar presencia visual e identidad de marca en todos los canales",
        "segment": "Todos los segmentos",
        "segment_users": guest_count,
        "channel": "Todos (digital + físico)",
        "campaign_type": "branding",
        "timing": "Desarrollo 2 semanas, roll-out progresivo",
        "subject_line": "Línea visual primavera-verano 2026",
        "preview_text": "Nueva paleta cromática, fotografía de destino y plantillas de comunicación para la temporada.",
        "body_summary": (
            "Crear una línea visual de temporada que unifique todos los puntos de contacto: "
            f"1) Fotografía: nueva sesión en {hotel1} y {hotel2} con modelo + lifestyle local (no solo habitación vacía). "
            "2) Paleta estacional: tonos cálidos dorados + verdes mediterráneos para headers, banners y señalización. "
            "3) Kit de plantillas: email (banner + footer), stories (3 templates), feed (carrusel + single), firma de email corporativa. "
            "4) Adaptación de portadas de RRSS, headers de Booking/Expedia y web propia. "
            "5) Guía de tono de voz para la temporada: inspiracional, cercano, basado en experiencia local."
        ),
        "deliverables": "Sesión fotográfica (50+ imágenes), kit plantillas (15 formatos), guía de tono, portadas RRSS",
        "priority": "media",
        "rationale": (
            f"Con {message_count} piezas registradas en el log, tener un sistema visual coherente ayuda a unificar email, RRSS y soportes in-hotel."
        ),
    })

    # ── 5. Geolocalización: Push y SMS ───────────────────────
    if segments:
        proposals.append({
            "id": "camp-005",
            "category": "geolocalizacion",
            "category_label": "Geolocalización",
            "name": f"Campaña de proximidad en {city1}",
            "objective": "Captar reservas de último minuto y walk-ins premium",
            "segment": top_seg.get("segment_label", "Segmento principal"),
            "segment_users": top_seg.get("users", 0),
            "channel": "Push + SMS + Google Ads local",
            "campaign_type": "geolocalizacion",
            "timing": "Activo en continuo (jueves a domingo)",
            "subject_line": f"Estás cerca de {city1} — tu habitación te espera",
            "preview_text": f"Notificación push y SMS geolocalizado para usuarios en un radio de 50km del hotel.",
            "body_summary": (
                f"Campaña de proximidad geolocalizada en {city1}: "
                f"1) Push notification a usuarios de la app con reserva pasada cuando están en radio <50km: oferta de último minuto con upgrade. "
                f"2) Google Ads con extensión de ubicación para búsquedas tipo «hotel {city1} esta noche». "
                f"3) SMS a base de datos de clientes que han visitado la ciudad antes, con oferta relámpago de fin de semana (envío jueves 17h). "
                f"4) Cartelería digital en estaciones de tren/aeropuerto cercanos con QR directo a reserva. "
                f"Personalización: el mensaje cambia según el perfil del usuario (aventurero → rooftop, cultural → itinerario, gastro → restaurante partner)."
            ),
            "deliverables": "Configuración geofencing, 3 creatividades push, 2 plantillas SMS, campaña Google Ads local, diseño cartelería",
            "priority": "media",
            "rationale": (
                f"Tiene sentido probarlo sobre el segmento más voluminoso ({top_seg.get('segment_label', 'segmento principal')}) "
                f"y sobre destinos con eventos o insights activos."
            ),
        })

    # ── 6. Hotel: Upsell pre-arrival automatizado ────────────
    if reception:
        proposals.append({
            "id": "camp-006",
            "category": "hotel",
            "category_label": "Acción en hotel",
            "name": "Automatización de upsell pre-check-in",
            "objective": "Incrementar revenue por reserva con upgrades y experiencias",
            "segment": "Todos los segmentos con reserva confirmada",
            "segment_users": guest_count,
            "channel": "Email + WhatsApp",
            "campaign_type": "pre_arrival",
            "timing": "48h antes del check-in (automatizado)",
            "subject_line": "Mejora tu estancia antes de llegar",
            "preview_text": "Late checkout, upgrade y experiencias locales a precio especial para ti.",
            "body_summary": (
                f"Flujo automatizado que se activa 48h antes del check-in: "
                f"1) Email con 3 opciones de upgrade personalizadas por segmento (habitación superior, late checkout, pack gastronómico). "
                f"2) Si no abre el email en 12h, enviar recordatorio por WhatsApp Business con carrusel visual. "
                f"3) Incluir mapa interactivo con los partnerships locales activos y botón de reserva directa. "
                f"4) Variante para premium y lujo: ofrecer acceso exclusivo a experiencia privada (cata, rooftop sunset). "
                f"Basado en esta observación de recepción: «{reception[0]}»."
            ),
            "deliverables": "Flujo automatizado (email + WhatsApp), 3 plantillas segmentadas, mapa interactivo, landing upsell",
            "priority": "alta",
            "rationale": (
                f"Hay {guest_count} usuarios segmentados y recepción ya está aportando observaciones que pueden convertirse en ofertas previas a la llegada."
            ),
        })

    # ── 7. Evento: Activación especial ───────────────────────
    if external:
        signal = external[0]
        proposals.append({
            "id": "camp-007",
            "category": "evento",
            "category_label": "Evento",
            "name": f"Activación 360° — {signal[:55]}",
            "objective": "Captar demanda del evento y generar contenido de marca",
            "segment": cultural_seg.get("segment_label", "Cultural"),
            "segment_users": cultural_seg.get("users", 0),
            "channel": "Multicanal (email + RRSS + hotel + partners)",
            "campaign_type": "evento",
            "timing": "Pre-evento (2 semanas), durante y post",
            "subject_line": f"Tu hotel para vivir {signal[:40]}",
            "preview_text": "Paquete exclusivo: alojamiento + itinerario del evento + experiencia Eurostars.",
            "body_summary": (
                f"Campaña 360° alrededor de «{signal}»: "
                f"PRE-EVENTO: Email a base de datos segmentada con paquete hotel+evento. Stories cuenta atrás 5 días. "
                f"DURANTE: Decoración temática en lobby (roll-up + flores/ambientación del evento). Stories en directo desde el evento. "
                f"Recepción con detalle de bienvenida temático (mapa del evento + posavasos ilustrado). "
                f"POST-EVENTO: Email UGC recopilando fotos de huéspedes durante el evento. Reels resumen 60s. "
                f"Cada fase tiene KPIs: reservas (pre), menciones social (durante), reservas futuras (post)."
            ),
            "deliverables": "Pack de emails (3), 15 stories, roll-up de lobby, detalle de bienvenida, reels postevento, email UGC",
            "priority": "alta",
            "rationale": f"Parte de un evento o insight que ya está cargado en el contexto activo: «{signal}».",
        })

    # ── 8. Decoración: Rediseño espacios comunes ─────────────
    proposals.append({
        "id": "camp-008",
        "category": "decoracion",
        "category_label": "Decoración",
        "name": f"Intervención artística en zonas comunes — {city1}",
        "objective": "Crear momentos 'Instagrameables' y reforzar identidad de destino",
        "segment": "JOVEN + ADULTO · Todos los perfiles",
        "segment_users": guest_count,
        "channel": "Físico / in-hotel",
        "campaign_type": "decoracion",
        "timing": "Instalación en 2 semanas, rotación trimestral",
        "subject_line": f"El arte de la ciudad, dentro del hotel",
        "preview_text": f"Intervención artística y fotográfica que conecta {city1} con la experiencia Eurostars.",
        "body_summary": (
            f"Programa de intervención artística en {city1}: "
            f"1) Mural o instalación fotográfica gran formato en el lobby con imágenes icónicas de la ciudad (artista local). "
            f"2) Rincón 'Instagrameable': esquina decorada con elementos locales (azulejos, cerámicas, plantas autóctonas) + neón con hashtag #EurostarsExperience. "
            f"3) Rotación trimestral de obras de artistas locales en pasillos y zonas comunes (con ficha y QR a perfil del artista). "
            f"4) Ambientación olfativa de marca: aroma diferenciado para el lobby que refuerce la memoria sensorial. "
            f"5) Mesa de revistas y libros curados sobre la ciudad (guías alternativas, fotografía, gastronomía local)."
        ),
        "deliverables": "Briefing artista, diseño rincón foto, plan de rotación anual, selección editorial, difusor de aroma",
        "priority": "media",
        "rationale": (
            f"Es una propuesta de marca pensada para hoteles con volumen como {hotel1} y para públicos amplios "
            f"como {country_top} o los segmentos jóvenes y adultos de la base."
        ),
    })

    return proposals


def _generate_ai_proposals(dashboard: dict) -> list[dict] | None:
    """Genera propuestas de campaña con Gemini vía Vertex AI."""
    try:
        from backend.ai.gemini import call_gemini, is_available
    except ModuleNotFoundError:
        return None

    if not is_available():
        return None

    system_prompt = _build_system_prompt(dashboard)
    prompt = (
        f"{system_prompt}\n\n"
        "Genera exactamente 5 propuestas de campaña de marketing. "
        "Para cada una devuelve un objeto JSON con estos campos: "
        "id, name, objective, segment, segment_users (int), "
        "channel, campaign_type, timing, subject_line, preview_text, "
        "body_summary, priority (alta/media/baja), rationale.\n"
        "No inventes estudios, porcentajes, benchmarks ni métricas observadas que no estén en el dashboard. "
        "Si justificas una propuesta, apóyate en conteos, segmentos, hoteles o eventos del panel.\n\n"
        "Devuelve únicamente un array JSON, sin markdown ni explicación."
    )

    result = call_gemini(prompt, json_output=True)
    if not isinstance(result, list) or not result:
        return None
    return result


def generate_single_campaign_proposal(
    index: int,
    previous_names: list[str],
    *,
    force_mock: bool = False,
) -> dict | None:
    """Genera UNA sola propuesta de campaña estilo Generador.

    Devuelve un dict con los campos que espera la tarjeta del dashboard
    (name, objective, segment, channel, timing, subject_line, preview_text,
    body_summary, priority, rationale, category, category_label). Si Gemini
    no está disponible o ``force_mock`` es True, cae a una variante del
    banco heurístico, añadiendo sufijo «(variante)» si el nombre colisiona.
    """
    dashboard = _get_dashboard()
    previous_names = previous_names or []

    def _from_heuristics() -> dict | None:
        proposals = _generate_heuristic_proposals(dashboard)
        if not proposals:
            return None
        base = dict(proposals[index % len(proposals)])
        base["id"] = f"live-{index + 1:03d}"
        if base.get("name") in previous_names:
            base["name"] = f"{base['name']} (variante)"
        return base

    if force_mock:
        return _from_heuristics()

    try:
        from backend.ai.gemini import call_gemini, is_available
    except ModuleNotFoundError:
        return _from_heuristics()

    if not is_available():
        return _from_heuristics()

    system_prompt = _build_system_prompt(dashboard)
    previous_fmt = (
        ", ".join(f'"{n}"' for n in previous_names[-10:])
        if previous_names
        else "ninguno todavía"
    )
    prompt = (
        f"{system_prompt}\n\n"
        "Genera UNA SOLA propuesta de campaña de marketing (no una lista) "
        "para Eurostars Hotel Company, pensada para el equipo de marketing. "
        f"Esta es la propuesta número {index + 1} en la sesión.\n"
        f"Evita repetir cualquiera de estos nombres ya usados: {previous_fmt}.\n\n"
        "Devuelve únicamente un objeto JSON con estos campos (en español):\n"
        "  id (string corto tipo 'live-001'),\n"
        "  name (título breve de la campaña),\n"
        "  category (uno de: rrss, hotel, local, branding, geolocalizacion, "
        "evento, decoracion),\n"
        "  category_label (etiqueta legible en español de la categoría),\n"
        "  objective (1 frase),\n"
        "  segment (etiqueta del segmento objetivo),\n"
        "  segment_users (int),\n"
        "  channel (canal o combinación),\n"
        "  timing (string temporal: '4 semanas', 'jueves a domingo', etc.),\n"
        "  subject_line (asunto breve si aplica),\n"
        "  preview_text (texto corto tipo preview email),\n"
        "  body_summary (descripción detallada en 3-6 frases, visible en la "
        "tarjeta del dashboard; no cortes ideas),\n"
        "  priority ('alta', 'media' o 'baja'),\n"
        "  rationale (1-3 frases explicando por qué esta propuesta encaja "
        "con los datos actuales del dashboard).\n"
        "No inventes benchmarks, estudios o métricas observadas ajenas al panel.\n\n"
        "No incluyas markdown ni explicaciones fuera del JSON."
    )

    result = call_gemini(prompt, json_output=True)
    if isinstance(result, dict) and result.get("name"):
        result.setdefault("id", f"live-{index + 1:03d}")
        if result["name"] in previous_names:
            result["name"] = f"{result['name']} (variante)"
        return result

    return _from_heuristics()


def _modify_messaging_heuristic(campaign: dict, instructions: str) -> dict:
    """Apply heuristic modifications to campaign messaging."""
    msg = instructions.lower()
    modified = dict(campaign)

    if any(w in msg for w in ["formal", "serio", "profesional", "corporativo"]):
        modified["subject_line"] = modified["subject_line"].replace("Tu ", "Su ").replace("te ", "le ")
        modified["body_summary"] = "Tono formal y corporativo. " + modified["body_summary"]
        modified["preview_text"] = modified["preview_text"].replace("tu", "su").replace("tú", "usted")
    elif any(w in msg for w in ["cercano", "informal", "amigable", "cálido", "personal"]):
        modified["body_summary"] = "Tono cercano y personal. " + modified["body_summary"]
    
    if any(w in msg for w in ["urgencia", "urgente", "última hora", "limitado", "escasez"]):
        modified["subject_line"] = "Últimas plazas: " + modified["subject_line"]
        modified["preview_text"] = "Disponibilidad limitada. " + modified["preview_text"]

    if any(w in msg for w in ["descuento", "oferta", "promoción", "precio", "ahorro"]):
        modified["subject_line"] = modified["subject_line"] + " — oferta exclusiva"
        modified["body_summary"] += " Incluir oferta visible con precio especial o descuento directo."

    if any(w in msg for w in ["lujo", "premium", "exclusivo", "vip"]):
        modified["subject_line"] = modified["subject_line"].replace("escapada", "experiencia exclusiva")
        modified["body_summary"] += " Tono premium, sin mencionar precios bajos. Destacar exclusividad y servicio."

    if any(w in msg for w in ["sms", "push", "notificación"]):
        modified["channel"] = "sms" if "sms" in msg else "push"
        modified["body_summary"] += " Adaptar contenido a formato corto para notificación/SMS (max 160 caracteres)."

    if any(w in msg for w in ["instagram", "tiktok", "redes", "rrss"]):
        modified["channel"] = "Instagram / TikTok"
        modified["body_summary"] += " Adaptar para formato visual de redes sociales: copy corto, CTA en bio."

    modified["_modification_applied"] = instructions
    return modified


def _modify_messaging_ai(campaign: dict, instructions: str) -> dict | None:
    """Reescribe el copy de una campaña con Gemini siguiendo las instrucciones."""
    try:
        from backend.ai.gemini import call_gemini, is_available
    except ModuleNotFoundError:
        return None

    if not is_available():
        return None

    prompt = (
        "Eres copywriter de Eurostars Hotel Company. "
        "Modifica esta campaña de email siguiendo las instrucciones.\n\n"
        f"CAMPAÑA ACTUAL:\n{json.dumps(campaign, ensure_ascii=False, indent=2)}\n\n"
        f"INSTRUCCIONES: {instructions}\n\n"
        "Devuelve únicamente el JSON de la campaña modificada con los mismos "
        "campos. Ajusta especialmente subject_line, preview_text y body_summary."
    )

    result = call_gemini(prompt, json_output=True)
    if not isinstance(result, dict):
        return None
    result["_modification_applied"] = instructions
    return result


# ── API pública ──────────────────────────────────────────────

def generate_campaign_proposals() -> dict:
    """
    Genera propuestas de campaña estructuradas a partir del dashboard.

    Devuelve: {"proposals": [...], "source": "gemini"|"heuristic"}
    """
    dashboard = _get_dashboard()

    ai_proposals = _generate_ai_proposals(dashboard)
    if ai_proposals:
        return {"proposals": ai_proposals, "source": "gemini"}

    proposals = _generate_heuristic_proposals(dashboard)
    return {"proposals": proposals, "source": "heuristic"}


def handle_modify_messaging(campaign_id: str, instructions: str, campaign: dict | None = None) -> dict:
    """
    Modifica el mensaje de una campaña generada a partir de instrucciones.

    Devuelve: {"campaign": {...}, "source": "gemini"|"heuristic"}
    """
    resolved_campaign = campaign if isinstance(campaign, dict) and campaign.get("name") else None
    if resolved_campaign is None:
        dashboard = _get_dashboard()
        proposals = _generate_heuristic_proposals(dashboard)
        resolved_campaign = next((p for p in proposals if p["id"] == campaign_id), None)

    if not resolved_campaign:
        return {"error": f"Campaña {campaign_id} no encontrada", "campaign": None, "source": "heuristic"}

    ai = _modify_messaging_ai(resolved_campaign, instructions)
    if ai:
        return {"campaign": ai, "source": "gemini"}

    modified = _modify_messaging_heuristic(resolved_campaign, instructions)
    return {"campaign": modified, "source": "heuristic"}


def handle_chat_message(message: str, history: list[dict] | None = None) -> dict:
    """
    Procesa un mensaje de chat del director de marketing.

    Devuelve: {"reply": "...", "source": "gemini"|"heuristic"}
    """
    if history is None:
        history = []

    dashboard = _get_dashboard()
    campaign_brief = None
    if _is_campaign_creation_request(message, history):
        campaign_brief = _extract_campaign_brief(message, history, dashboard)
        clarification = _campaign_clarification_reply(campaign_brief)
        if clarification:
            return {"reply": clarification, "source": "heuristic"}

    gemini = _gemini_reply(message, history, dashboard)
    if gemini:
        return {"reply": gemini, "source": "gemini"}

    if campaign_brief:
        return {"reply": _heuristic_campaign_reply(campaign_brief, dashboard), "source": "heuristic"}

    reply = _heuristic_reply(message, dashboard)
    return {"reply": reply, "source": "heuristic"}
