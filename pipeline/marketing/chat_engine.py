#!/usr/bin/env python3
"""
chat_engine.py — Marketing AI Assistant.

Conversational agent with full access to dashboard data.
Uses Anthropic if available, falls back to a contextual heuristic engine.
"""

from __future__ import annotations

import json
import logging
import os
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

from pipeline.marketing.dashboard_engine import build_dashboard_data

load_dotenv()

logger = logging.getLogger("marketing_chat")

# Cache dashboard data to avoid rebuilding on every message
_dashboard_cache: dict | None = None


def _get_dashboard() -> dict:
    global _dashboard_cache
    if _dashboard_cache is None:
        _dashboard_cache = build_dashboard_data()
    return _dashboard_cache


def refresh_dashboard_cache() -> None:
    global _dashboard_cache
    _dashboard_cache = None


def _build_system_prompt(dashboard: dict) -> str:
    """Build the system prompt with full dashboard context."""
    context = dashboard.get("context", {})
    kpis = dashboard.get("kpis", {})
    segment_cards = dashboard.get("segment_cards", [])
    perf_age = dashboard.get("performance_by_age", [])
    perf_profile = dashboard.get("performance_by_profile", [])
    perf_value = dashboard.get("performance_by_value", [])
    perf_moment = dashboard.get("performance_by_moment", [])
    recommendations = dashboard.get("recommendations", {})
    focus_cities = dashboard.get("focus_cities", [])
    recent_campaigns = dashboard.get("recent_campaigns", [])

    return f"""Eres el director de estrategia de marketing de Eurostars Hotel Company.
Tienes acceso completo a los datos operativos de campañas, segmentación de clientes y señales del mercado.
Responde siempre en español. Sé directo, concreto y profesional. No uses emojis.
Cuando propongas acciones, deben ser específicas y ejecutables.
Cuando analices datos, cita números concretos del dashboard.

CONTEXTO ESTRATÉGICO:
- Prioridad actual: {context.get('strategic_priority', 'Sin definir')}
- Notas del jefe de marketing: {json.dumps(context.get('manager_notes', []), ensure_ascii=False)}
- Señales de recepción: {json.dumps(context.get('reception_notes', []), ensure_ascii=False)}
- Señales externas: {json.dumps(context.get('external_signals', []), ensure_ascii=False)}

KPIs ACTUALES:
- Total campañas analizadas: {kpis.get('total_campaigns', 0)}
- Tamaño audiencia: {kpis.get('audience_size', 0)} usuarios
- Segmentos activos: {kpis.get('active_segments', 0)}
- Índice medio de engagement: {kpis.get('avg_engagement_index', 0)}
- Presión estratégica: {kpis.get('priority_pressure', 0)}/100

CIUDADES EN FOCO: {', '.join(focus_cities)}

RENDIMIENTO POR EDAD:
{json.dumps([{{'label': s['label'], 'index': s['avg_engagement_index'], 'count': s['count']}} for s in perf_age], ensure_ascii=False)}

RENDIMIENTO POR PERFIL DE VIAJE:
{json.dumps([{{'label': s['label'], 'index': s['avg_engagement_index'], 'count': s['count']}} for s in perf_profile], ensure_ascii=False)}

RENDIMIENTO POR VALOR DE CLIENTE:
{json.dumps([{{'label': s['label'], 'index': s['avg_engagement_index'], 'count': s['count']}} for s in perf_value], ensure_ascii=False)}

RENDIMIENTO POR MOMENTO:
{json.dumps([{{'label': s['label'], 'index': s['avg_engagement_index'], 'count': s['count']}} for s in perf_moment], ensure_ascii=False)}

TOP SEGMENTOS:
{json.dumps([{{'segment': s['segment_label'], 'users': s['users'], 'campaigns': s['campaigns'], 'engagement': s['avg_engagement_index'], 'adr': s['avg_adr'], 'channel': s['dominant_channel']}} for s in segment_cards[:6]], ensure_ascii=False)}

RECOMENDACIONES ACTIVAS:
- RRSS: {recommendations.get('rrss', {{}}).get('summary', 'N/A')}
- Hotel: {recommendations.get('hotel', {{}}).get('summary', 'N/A')}
- Ads: {recommendations.get('ads', {{}}).get('summary', 'N/A')}

CAMPAÑAS RECIENTES (últimas 6):
{json.dumps([{{'type': c['campaign_type'], 'segment': c['age_segment'] + ' / ' + c['travel_profile'], 'channel': c['channel'], 'hotel': c['hotel'], 'engagement': c['engagement_index']}} for c in recent_campaigns[:6]], ensure_ascii=False)}
"""


# ── Heuristic fallback engine ────────────────────────────────

def _detect_intent(message: str) -> str:
    """Detect the user's intent from their message."""
    msg = message.lower().strip()

    if any(w in msg for w in ["analizar", "análisis", "analiza", "situación", "estado", "cómo va", "resumen", "overview"]):
        return "analysis"
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
    """Generate contextual reply using dashboard data without AI API."""
    intent = _detect_intent(message)
    kpis = dashboard.get("kpis", {})
    context = dashboard.get("context", {})
    segments = dashboard.get("segment_cards", [])
    perf_age = dashboard.get("performance_by_age", [])
    perf_profile = dashboard.get("performance_by_profile", [])
    perf_value = dashboard.get("performance_by_value", [])
    focus_cities = dashboard.get("focus_cities", [])
    recommendations = dashboard.get("recommendations", {})
    recent = dashboard.get("recent_campaigns", [])

    if intent == "analysis":
        top_seg = segments[0] if segments else {}
        worst_age = min(perf_age, key=lambda x: x["avg_engagement_index"]) if perf_age else {}
        return (
            f"Situación actual del pipeline de marketing:\n\n"
            f"Tenemos {kpis.get('total_campaigns', 0)} campañas activas sobre una base de "
            f"{kpis.get('audience_size', 0)} usuarios segmentados en {kpis.get('active_segments', 0)} cruces de edad y perfil.\n\n"
            f"El índice de engagement medio es del {round(kpis.get('avg_engagement_index', 0) * 100)}%, "
            f"con una presión estratégica de {kpis.get('priority_pressure', 0)}/100.\n\n"
            f"El segmento con mejor tracción es {top_seg.get('segment_label', 'N/A')} "
            f"({top_seg.get('users', 0)} usuarios, engagement {round(top_seg.get('avg_engagement_index', 0) * 100)}%, "
            f"ADR medio {round(top_seg.get('avg_adr', 0))}€).\n\n"
            f"El segmento de edad con menor rendimiento es {worst_age.get('label', 'N/A')} "
            f"({round(worst_age.get('avg_engagement_index', 0) * 100)}% engagement).\n\n"
            f"Ciudades en foco: {', '.join(focus_cities)}.\n\n"
            f"Prioridad estratégica: {context.get('strategic_priority', 'Sin definir')}."
        )

    if intent == "segment":
        lines = ["Desglose de segmentos prioritarios:\n"]
        for seg in segments[:5]:
            lines.append(
                f"- {seg['segment_label']}: {seg['users']} usuarios, "
                f"{seg['campaigns']} campañas, engagement {round(seg['avg_engagement_index'] * 100)}%, "
                f"ADR medio {round(seg['avg_adr'])}€, canal dominante: {seg['dominant_channel']}"
            )
        lines.append(f"\nLos segmentos de mayor valor (HIGH_VALUE) son los que más margen ofrecen para upselling.")
        hv = [s for s in perf_value if s["label"] == "HIGH_VALUE"]
        if hv:
            lines.append(f"HIGH_VALUE tiene un engagement del {round(hv[0]['avg_engagement_index'] * 100)}% sobre {hv[0]['count']} campañas.")
        return "\n".join(lines)

    if intent == "social_media":
        rrss = recommendations.get("rrss", {})
        return (
            f"Plan de acción para redes sociales:\n\n"
            f"{rrss.get('summary', 'Sin resumen disponible.')}\n\n"
            f"Acciones concretas:\n" +
            "\n".join(f"- {a}" for a in rrss.get("actions", [])) +
            f"\n\nEl contenido debería priorizar los segmentos con mejor engagement: "
            f"{', '.join(s['segment_label'] for s in segments[:3])}.\n\n"
            f"Recomendación adicional: crear una serie de contenido visual centrado en las ciudades en foco "
            f"({', '.join(focus_cities)}) con narrativa de experiencia local, no de hotel."
        )

    if intent == "hotel_actions":
        hotel = recommendations.get("hotel", {})
        reception = context.get("reception_notes", [])
        return (
            f"Plan de acciones dentro del hotel:\n\n"
            f"{hotel.get('summary', 'Sin resumen disponible.')}\n\n"
            f"Acciones concretas:\n" +
            "\n".join(f"- {a}" for a in hotel.get("actions", [])) +
            f"\n\nSeñales detectadas por recepción:\n" +
            "\n".join(f"- {r}" for r in reception) +
            f"\n\nEstas señales indican oportunidades claras de upselling en el momento del check-in, "
            f"especialmente para los perfiles culturales y gastronómicos."
        )

    if intent == "advertising":
        ads = recommendations.get("ads", {})
        return (
            f"Estrategia de publicidad externa:\n\n"
            f"{ads.get('summary', 'Sin resumen disponible.')}\n\n"
            f"Acciones propuestas:\n" +
            "\n".join(f"- {a}" for a in ads.get("actions", [])) +
            f"\n\nSugerencia de campaña nueva:\n"
            f"- Campaña de retargeting dinámico en Meta para usuarios que han visitado las páginas de "
            f"{', '.join(focus_cities[:2])} en los últimos 30 días.\n"
            f"- Audience lookalike basada en el segmento {segments[0]['segment_label'] if segments else 'top'} "
            f"con exclusión de clientes existentes.\n"
            f"- Budget split recomendado: 60% performance (reserva directa), 40% awareness (contenido de destino)."
        )

    if intent == "channel_mix":
        lines = ["Análisis del mix de canales:\n"]
        channel_data = {}
        for c in recent:
            ch = c.get("channel", "email")
            if ch not in channel_data:
                channel_data[ch] = {"count": 0, "total_engagement": 0}
            channel_data[ch]["count"] += 1
            channel_data[ch]["total_engagement"] += c.get("engagement_index", 0)
        for ch, data in sorted(channel_data.items(), key=lambda x: -x[1]["count"]):
            avg = round(data["total_engagement"] / max(data["count"], 1) * 100)
            lines.append(f"- {ch}: {data['count']} campañas recientes, engagement medio {avg}%")
        lines.append(
            f"\nEl canal dominante varía por segmento. Los jóvenes responden mejor a push, "
            f"los adultos y senior a email. El SMS tiene mejor tracción con leadtimes cortos (<7 días)."
        )
        return "\n".join(lines)

    if intent == "destinations":
        lines = [f"Ciudades en foco actual: {', '.join(focus_cities)}.\n"]
        external = context.get("external_signals", [])
        if external:
            lines.append("Señales externas activas:")
            for s in external:
                lines.append(f"- {s}")
        city_campaigns = {}
        for c in recent:
            h = c.get("hotel", "")
            if h:
                city_campaigns[h] = city_campaigns.get(h, 0) + 1
        if city_campaigns:
            lines.append("\nActividad reciente por hotel/destino:")
            for hotel, count in sorted(city_campaigns.items(), key=lambda x: -x[1]):
                lines.append(f"- {hotel}: {count} campañas recientes")
        return "\n".join(lines)

    if intent == "new_ideas":
        top = segments[:2] if len(segments) >= 2 else segments
        top_names = [s["segment_label"] for s in top]
        return (
            f"Ideas de campaña basadas en los datos actuales:\n\n"
            f"1. Campaña \"48 horas en...\" para {top_names[0] if top_names else 'segmento top'}:\n"
            f"   - Serie de emails + stories con itinerario curado de fin de semana\n"
            f"   - Dirigida a perfiles culturales con engagement alto\n"
            f"   - CTA: reserva directa con early check-in incluido\n\n"
            f"2. Campaña de fidelización cruzada:\n"
            f"   - Detectar huéspedes que han visitado 2+ destinos Eurostars\n"
            f"   - Ofrecerles acceso a programa de experiencias exclusivas\n"
            f"   - Canal: email personalizado + notificación push\n\n"
            f"3. Activación gastronómica en {focus_cities[0] if focus_cities else 'destinos clave'}:\n"
            f"   - Colaboración con restaurantes locales para paquetes de escapada\n"
            f"   - Contenido en redes: behind-the-scenes con chef local\n"
            f"   - Target: segmentos GASTRONOMIA_CIUDAD y EXPLORADOR_CULTURAL\n\n"
            f"4. Campaña de re-engagement post-stay:\n"
            f"   - Los post-stay actuales tienen un engagement del "
            f"{round(next((p['avg_engagement_index'] for p in dashboard.get('performance_by_moment', []) if p['label'] == 'post_stay'), 0.5) * 100)}%\n"
            f"   - Propuesta: añadir incentivo de reserva directa con descuento para próximo viaje\n"
            f"   - A/B test: con incentivo vs sin incentivo"
        )

    if intent == "weak_spots":
        worst_segs = sorted(segments, key=lambda s: s["avg_engagement_index"])[:3]
        lines = ["Puntos débiles detectados:\n"]
        for seg in worst_segs:
            lines.append(
                f"- {seg['segment_label']}: engagement {round(seg['avg_engagement_index'] * 100)}%, "
                f"{seg['users']} usuarios, ADR {round(seg['avg_adr'])}€"
            )
        worst_age = min(perf_age, key=lambda x: x["avg_engagement_index"]) if perf_age else {}
        if worst_age:
            lines.append(
                f"\nEl segmento de edad con peor rendimiento es {worst_age['label']} "
                f"({round(worst_age['avg_engagement_index'] * 100)}% engagement)."
            )
        lines.append(
            "\nRecomendaciones para mejorar:\n"
            "- Revisar creatividades y asuntos de email para los segmentos con bajo engagement\n"
            "- Testear canales alternativos (push para jóvenes, SMS para leadtimes cortos)\n"
            "- Considerar ajustar la frecuencia de contacto para evitar fatiga"
        )
        return "\n".join(lines)

    if intent == "top_performers":
        best_segs = sorted(segments, key=lambda s: -s["avg_engagement_index"])[:3]
        lines = ["Segmentos con mejor rendimiento:\n"]
        for seg in best_segs:
            lines.append(
                f"- {seg['segment_label']}: engagement {round(seg['avg_engagement_index'] * 100)}%, "
                f"{seg['users']} usuarios, ADR medio {round(seg['avg_adr'])}€, canal: {seg['dominant_channel']}"
            )
        lines.append(
            f"\nOportunidad: concentrar presupuesto en los 2-3 segmentos top para maximizar ROI, "
            f"y usar aprendizajes de sus campañas como plantilla para mejorar los segmentos más débiles."
        )
        return "\n".join(lines)

    # General fallback
    return (
        f"Estoy aquí para ayudarte con la estrategia de marketing. Puedo:\n\n"
        f"- Analizar la situación actual de campañas y segmentos\n"
        f"- Proponer nuevas ideas de campañas de publicidad\n"
        f"- Desglosar el rendimiento por segmento, canal o destino\n"
        f"- Recomendar acciones para redes sociales o dentro del hotel\n"
        f"- Identificar puntos débiles y oportunidades\n"
        f"- Analizar el mix de canales\n\n"
        f"Datos actuales: {kpis.get('total_campaigns', 0)} campañas, "
        f"{kpis.get('audience_size', 0)} usuarios, engagement medio {round(kpis.get('avg_engagement_index', 0) * 100)}%."
    )


# ── Anthropic engine ─────────────────────────────────────────

def _anthropic_reply(message: str, history: list[dict], dashboard: dict) -> str | None:
    """Try to get a reply from Anthropic. Returns None if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxxxx"):
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = _build_system_prompt(dashboard)

        messages = []
        for entry in history[-10:]:
            role = "user" if entry.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": entry.get("content", "")})
        messages.append({"role": "user", "content": message})

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("Anthropic chat failed: %s", exc)
        return None


# ── Campaign Proposal Generator ──────────────────────────────

def _generate_heuristic_proposals(dashboard: dict) -> list[dict]:
    """Generate structured campaign proposals from dashboard data."""
    segments = dashboard.get("segment_cards", [])
    context = dashboard.get("context", {})
    kpis = dashboard.get("kpis", {})
    focus_cities = dashboard.get("focus_cities", [])
    perf_moment = dashboard.get("performance_by_moment", [])
    perf_profile = dashboard.get("performance_by_profile", [])
    external = context.get("external_signals", [])
    reception = context.get("reception_notes", [])

    proposals = []

    # 1. High-engagement segment campaign
    if segments:
        top = segments[0]
        proposals.append({
            "id": "camp-001",
            "name": f"Escapada premium para {top['segment_label']}",
            "objective": "Conversión a reserva directa",
            "segment": top["segment_label"],
            "segment_users": top["users"],
            "segment_engagement": top["avg_engagement_index"],
            "channel": top["dominant_channel"],
            "campaign_type": "pre_arrival",
            "timing": "Lanzamiento en próximos 7 días",
            "estimated_engagement": round(min(top["avg_engagement_index"] + 0.05, 0.98), 2),
            "subject_line": f"Tu escapada a {focus_cities[0] if focus_cities else 'un destino especial'} te espera",
            "preview_text": f"Descubre una experiencia diseñada para viajeros como tú. Early check-in incluido.",
            "body_summary": (
                f"Email visual con itinerario personalizado de 48h en {focus_cities[0] if focus_cities else 'destino principal'}. "
                f"Incluye recomendaciones de restaurantes, actividades culturales y oferta de upgrade. "
                f"CTA principal: reserva directa con beneficio exclusivo."
            ),
            "priority": "alta",
            "rationale": f"Segmento con mejor engagement ({round(top['avg_engagement_index']*100)}%) y ADR medio de {round(top['avg_adr'])}€. Máximo potencial de conversión.",
        })

    # 2. Low-performing segment recovery campaign
    if len(segments) >= 3:
        worst = min(segments, key=lambda s: s["avg_engagement_index"])
        proposals.append({
            "id": "camp-002",
            "name": f"Reactivación del segmento {worst['segment_label']}",
            "objective": "Recuperar engagement y reducir churn",
            "segment": worst["segment_label"],
            "segment_users": worst["users"],
            "segment_engagement": worst["avg_engagement_index"],
            "channel": "email",
            "campaign_type": "post_stay",
            "timing": "Lanzamiento en próximos 14 días",
            "estimated_engagement": round(min(worst["avg_engagement_index"] + 0.12, 0.85), 2),
            "subject_line": f"Te echamos de menos, {worst['age_segment'].lower()}",
            "preview_text": "Hemos preparado algo especial para tu próxima escapada. Solo para clientes como tú.",
            "body_summary": (
                f"Email de reactivación con incentivo de reserva directa (descuento o upgrade garantizado). "
                f"Tono cercano, no agresivo. Incluir selección curada de destinos basada en historial. "
                f"A/B test del asunto: emocional vs racional."
            ),
            "priority": "media",
            "rationale": f"Engagement actual en {round(worst['avg_engagement_index']*100)}%. Margen de mejora alto con campaña específica.",
        })

    # 3. Event-driven campaign from external signals
    if external:
        signal = external[0]
        target_seg = segments[1] if len(segments) >= 2 else (segments[0] if segments else None)
        proposals.append({
            "id": "camp-003",
            "name": f"Activación por evento: {signal[:60]}",
            "objective": "Captar demanda del evento externo",
            "segment": target_seg["segment_label"] if target_seg else "ADULTO · EXPLORADOR_CULTURAL",
            "segment_users": target_seg["users"] if target_seg else 0,
            "segment_engagement": target_seg["avg_engagement_index"] if target_seg else 0.75,
            "channel": "email",
            "campaign_type": "pre_arrival",
            "timing": "Lanzamiento 2 semanas antes del evento",
            "estimated_engagement": 0.82,
            "subject_line": f"El momento perfecto para {focus_cities[0] if focus_cities else 'tu próxima escapada'}",
            "preview_text": f"Un evento especial. Un hotel a la altura. Reserva con ventaja exclusiva.",
            "body_summary": (
                f"Email temático vinculado al evento ({signal}). "
                f"Itinerario que combina el evento con la experiencia del hotel. "
                f"Oferta limitada en tiempo. CTA a reserva directa."
            ),
            "priority": "alta",
            "rationale": f"Señal externa activa con alta afinidad para el segmento objetivo. Oportunidad de capitalizar demanda.",
        })

    # 4. Cross-sell / upsell from reception signals
    if reception:
        proposals.append({
            "id": "camp-004",
            "name": "Campaña de upsell pre-arrival",
            "objective": "Incrementar revenue por reserva con upgrades",
            "segment": "Todos los segmentos con reserva confirmada",
            "segment_users": kpis.get("audience_size", 0),
            "segment_engagement": kpis.get("avg_engagement_index", 0.75),
            "channel": "email",
            "campaign_type": "pre_arrival",
            "timing": "48h antes del check-in",
            "estimated_engagement": 0.78,
            "subject_line": "Mejora tu estancia antes de llegar",
            "preview_text": "Late checkout, upgrade de habitación y experiencias exclusivas a precio especial.",
            "body_summary": (
                f"Email automatizado que se envía 48h antes del check-in con opciones de upgrade. "
                f"Basado en la señal de recepción: '{reception[0]}'. "
                f"Incluir 3 opciones: upgrade habitación, late checkout, pack experiencia gastronómica."
            ),
            "priority": "alta",
            "rationale": f"Recepción detecta demanda real de upgrades. Automatizar la venta antes de la llegada maximiza la conversión.",
        })

    # 5. Social media content campaign
    if len(segments) >= 2:
        cultural_seg = next((s for s in segments if "CULTURAL" in s["travel_profile"]), segments[0])
        proposals.append({
            "id": "camp-005",
            "name": f"RRSS: Serie 'Vive como un local' en {focus_cities[0] if focus_cities else 'destino'}",
            "objective": "Awareness y tráfico a web",
            "segment": cultural_seg["segment_label"],
            "segment_users": cultural_seg["users"],
            "segment_engagement": cultural_seg["avg_engagement_index"],
            "channel": "push",
            "campaign_type": "pre_arrival",
            "timing": "3 publicaciones/semana durante 4 semanas",
            "estimated_engagement": 0.72,
            "subject_line": "Descubre el barrio como un vecino",
            "preview_text": "Rutas, restaurantes y secretos locales seleccionados por nuestro equipo.",
            "body_summary": (
                f"Serie de contenido para Instagram y TikTok mostrando la experiencia local en "
                f"{focus_cities[0] if focus_cities else 'destinos clave'}. Formato: Reels de 30-60s con "
                f"itinerarios de barrio, recomendaciones gastronómicas y detrás de cámaras del hotel. "
                f"CTA en bio y stories: link a landing de reserva directa."
            ),
            "priority": "media",
            "rationale": f"El contenido experiencial genera mejores ratios de engagement orgánico. Target alineado con el segmento {cultural_seg['segment_label']}.",
        })

    return proposals


def _generate_ai_proposals(dashboard: dict) -> list[dict] | None:
    """Try to generate proposals with Anthropic."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxxxx"):
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = _build_system_prompt(dashboard)
        prompt = """Genera exactamente 5 propuestas de campaña de marketing. Para cada una devuelve JSON con estos campos:
id, name, objective, segment, segment_users (int), segment_engagement (float 0-1), channel, campaign_type (pre_arrival/post_stay/checkin_report), timing, estimated_engagement (float 0-1), subject_line, preview_text, body_summary, priority (alta/media/baja), rationale.

Devuelve solo un JSON array. Sin markdown, sin explicación."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as exc:
        logger.warning("Anthropic proposals failed: %s", exc)
        return None


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
        modified["channel"] = "push"
        modified["body_summary"] += " Adaptar para formato visual de redes sociales: copy corto, CTA en bio."

    modified["_modification_applied"] = instructions
    return modified


# ── Public API ────────────────────────────────────────────────

def generate_campaign_proposals() -> dict:
    """
    Generate structured campaign proposals from dashboard data.

    Returns: {"proposals": [...], "source": "anthropic"|"heuristic"}
    """
    dashboard = _get_dashboard()

    ai_proposals = _generate_ai_proposals(dashboard)
    if ai_proposals:
        return {"proposals": ai_proposals, "source": "anthropic"}

    proposals = _generate_heuristic_proposals(dashboard)
    return {"proposals": proposals, "source": "heuristic"}


def handle_modify_messaging(campaign_id: str, instructions: str) -> dict:
    """
    Modify the messaging of a generated campaign based on instructions.

    Returns: {"campaign": {...}, "source": "anthropic"|"heuristic"}
    """
    dashboard = _get_dashboard()
    proposals = _generate_heuristic_proposals(dashboard)
    
    campaign = next((p for p in proposals if p["id"] == campaign_id), None)
    if not campaign:
        return {"error": f"Campaña {campaign_id} no encontrada", "campaign": None, "source": "heuristic"}

    # Try Anthropic for better messaging
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("sk-ant-xxxxx"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = f"""Modifica esta campaña de marketing siguiendo estas instrucciones: "{instructions}"

Campaña actual:
{json.dumps(campaign, ensure_ascii=False, indent=2)}

Devuelve SOLO el JSON de la campaña modificada, con los mismos campos. Ajusta subject_line, preview_text y body_summary según las instrucciones."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            modified = json.loads(text)
            modified["_modification_applied"] = instructions
            return {"campaign": modified, "source": "anthropic"}
        except Exception as exc:
            logger.warning("Anthropic modify failed: %s", exc)

    modified = _modify_messaging_heuristic(campaign, instructions)
    return {"campaign": modified, "source": "heuristic"}


def handle_chat_message(message: str, history: list[dict] | None = None) -> dict:
    """
    Handle a chat message from the marketing director.

    Returns: {"reply": "...", "source": "anthropic"|"heuristic"}
    """
    if history is None:
        history = []

    dashboard = _get_dashboard()

    # Try Anthropic first
    anthropic_reply = _anthropic_reply(message, history, dashboard)
    if anthropic_reply:
        return {"reply": anthropic_reply, "source": "anthropic"}

    # Fallback to heuristic
    reply = _heuristic_reply(message, dashboard)
    return {"reply": reply, "source": "heuristic"}
