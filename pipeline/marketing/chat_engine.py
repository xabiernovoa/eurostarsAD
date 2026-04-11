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
    """Generate diverse campaign proposals across all marketing channels."""
    segments = dashboard.get("segment_cards", [])
    context = dashboard.get("context", {})
    kpis = dashboard.get("kpis", {})
    focus_cities = dashboard.get("focus_cities", [])
    external = context.get("external_signals", [])
    reception = context.get("reception_notes", [])
    perf_profile = dashboard.get("performance_by_profile", [])

    proposals = []
    city1 = focus_cities[0] if focus_cities else "destino principal"
    city2 = focus_cities[1] if len(focus_cities) >= 2 else "destino secundario"
    top_seg = segments[0] if segments else {}
    cultural_seg = next((s for s in segments if "CULTURAL" in s.get("travel_profile", "")), segments[0] if segments else {})
    gastro_seg = next((s for s in segments if "GASTRO" in s.get("travel_profile", "")), segments[0] if segments else {})

    # ── 1. RRSS: Serie de contenido ──────────────────────────
    proposals.append({
        "id": "camp-001",
        "category": "rrss",
        "category_label": "Redes sociales",
        "name": f"Serie «Vive como un local» — {city1}",
        "objective": "Awareness orgánico y tráfico a web de reserva directa",
        "segment": cultural_seg.get("segment_label", "CULTURAL"),
        "segment_users": cultural_seg.get("users", 0),
        "segment_engagement": cultural_seg.get("avg_engagement_index", 0.75),
        "channel": "Instagram + TikTok",
        "campaign_type": "contenido_rrss",
        "timing": "4 semanas · 3 piezas/semana",
        "estimated_engagement": 0.74,
        "subject_line": "Descubre el barrio como un vecino",
        "preview_text": "Formato: Reels 30-60s y carruseles con rutas de barrio, restaurantes locales y detrás de cámaras del hotel.",
        "body_summary": (
            f"Serie de contenido visual para Instagram Reels y TikTok centrada en la vida local de {city1}. "
            f"3 pilares de contenido: 1) Ruta a pie por el barrio del hotel (60s), 2) Restaurante local con plato estrella (30s), "
            f"3) Behind-the-scenes del hotel: rooftop, cocina, preparación de habitación premium. "
            f"Cada pieza incluye CTA en bio hacia landing de reserva directa. Colaborar con micro-influencer local (5K-20K seguidores) para la serie."
        ),
        "deliverables": "12 Reels, 4 carruseles, 1 highlight permanente, 4 stories interactivas",
        "priority": "alta",
        "rationale": f"El contenido experiencial orgánico tiene coste bajo y largo recorrido. Alineado con el segmento {cultural_seg.get('segment_label', '')} (engagement {round(cultural_seg.get('avg_engagement_index', 0)*100)}%).",
    })

    # ── 2. Hotel: Decoración y señalización ──────────────────
    proposals.append({
        "id": "camp-002",
        "category": "hotel",
        "category_label": "Acción en hotel",
        "name": f"Rediseño de señalización y experiencia en {city1}",
        "objective": "Mejorar percepción de marca y facilitar upselling en el hotel",
        "segment": "Todos los huéspedes in-house",
        "segment_users": kpis.get("audience_size", 0),
        "segment_engagement": 0.90,
        "channel": "Físico / in-hotel",
        "campaign_type": "hotel_insite",
        "timing": "Implementación en 3-4 semanas",
        "estimated_engagement": 0.85,
        "subject_line": "Programa de experiencia en hotel",
        "preview_text": "QR interactivos, decoración temática estacional y materiales de upsell en puntos clave del hotel.",
        "body_summary": (
            f"Rediseño de la experiencia física dentro de {city1}: "
            f"1) QR en caballete de recepción: lleva a landing con experiencias locales reservables (rutas, restaurantes, late checkout). "
            f"2) Decoración estacional en lobby: fotografía gran formato de la ciudad con narrativa 'Eurostars te conecta con la ciudad'. "
            f"3) Tarjetas en habitación con recomendaciones de barrio personalizadas por perfil (aventurero, cultural, gastronómico). "
            f"4) Pantalla digital en ascensor con ofertas de upgrade y actividades del día. "
            f"5) Display en recepción con objetos de artesanía local, reforzando la conexión con el destino."
        ),
        "deliverables": "Diseño de QR + landing, 3 formatos de cartelería, tarjetas habitación (3 versiones), contenido pantalla",
        "priority": "alta",
        "rationale": f"Recepción detecta: «{reception[0] if reception else 'interés en experiencias locales'}». La señalización convierte un momento pasivo (espera) en oportunidad de venta.",
    })

    # ── 3. Localización: Partnerships locales ────────────────
    proposals.append({
        "id": "camp-003",
        "category": "local",
        "category_label": "Localización",
        "name": f"Programa de partnerships locales — {city1}",
        "objective": "Crear experiencias diferenciales y contenido auténtico",
        "segment": gastro_seg.get("segment_label", "GASTRONOMÍA"),
        "segment_users": gastro_seg.get("users", 0),
        "segment_engagement": gastro_seg.get("avg_engagement_index", 0.80),
        "channel": "Presencial + digital",
        "campaign_type": "local_partnership",
        "timing": "Activo de mayo a septiembre",
        "estimated_engagement": 0.80,
        "subject_line": f"Alianzas locales en {city1}",
        "preview_text": "Acuerdos con restaurantes, bodegas y galerías locales para crear paquetes exclusivos Eurostars.",
        "body_summary": (
            f"Crear una red de partnerships locales en {city1}: "
            f"1) 3 restaurantes con menú «Selección Eurostars» con descuento para huéspedes (exposición cruzada en ambas marcas). "
            f"2) Bodega/cata de vinos con visita privada para huéspedes premium y HIGH_VALUE. "
            f"3) Galería de arte o taller de artesanía local: experiencia reservable desde el QR de habitación. "
            f"4) Ruta guiada a pie con guía local, exclusiva para huéspedes (sábados por la mañana). "
            f"Todos los partners deben generar contenido co-branded para RRSS (mínimo 2 posts/mes cada uno). "
            f"Medir: reservas de experiencias, menciones en RRSS, NPS incremento."
        ),
        "deliverables": "3-5 acuerdos firmados, kit co-branding, landing experiencias, material para partners",
        "priority": "alta",
        "rationale": f"El segmento gastronómico ({gastro_seg.get('segment_label', '')}) tiene alto ADR ({round(gastro_seg.get('avg_adr', 0))}€) y valor aspiracional. Los partnerships generan contenido auténtico sin coste de producción.",
    })

    # ── 4. Branding: Imagen corporativa ──────────────────────
    proposals.append({
        "id": "camp-004",
        "category": "branding",
        "category_label": "Imagen corporativa",
        "name": "Refresh visual de temporada Eurostars",
        "objective": "Actualizar presencia visual e identidad de marca en todos los canales",
        "segment": "Todos los segmentos",
        "segment_users": kpis.get("audience_size", 0),
        "segment_engagement": 0.70,
        "channel": "Todos (digital + físico)",
        "campaign_type": "branding",
        "timing": "Desarrollo 2 semanas, roll-out progresivo",
        "estimated_engagement": 0.68,
        "subject_line": "Línea visual primavera-verano 2026",
        "preview_text": "Nueva paleta cromática, fotografía de destino y plantillas de comunicación para la temporada.",
        "body_summary": (
            "Crear una línea visual de temporada que unifique todos los puntos de contacto: "
            "1) Fotografía: nueva sesión en los 3 hoteles en foco con modelo + lifestyle local (no solo habitación vacía). "
            "2) Paleta estacional: tonos cálidos dorados + verdes mediterráneos para headers, banners y señalización. "
            "3) Kit de plantillas: email (banner + footer), stories (3 templates), feed (carrusel + single), firma de email corporativa. "
            "4) Adaptación de portadas de RRSS, headers de Booking/Expedia y web propia. "
            "5) Guía de tono de voz para la temporada: inspiracional, cercano, basado en experiencia local."
        ),
        "deliverables": "Sesión fotográfica (50+ imágenes), kit plantillas (15 formatos), guía de tono, portadas RRSS",
        "priority": "media",
        "rationale": "Una imagen de marca cohesiva aumenta el reconocimiento y la confianza. Los activos generados alimentan 3-4 meses de comunicación.",
    })

    # ── 5. Geolocalización: Push y SMS ───────────────────────
    if segments:
        proposals.append({
            "id": "camp-005",
            "category": "geolocalizacion",
            "category_label": "Geolocalización",
            "name": f"Campaña de proximidad en {city1}",
            "objective": "Captar reservas de último minuto y walk-ins premium",
            "segment": "ADULTO · Todos los perfiles",
            "segment_users": top_seg.get("users", 0),
            "segment_engagement": top_seg.get("avg_engagement_index", 0.75),
            "channel": "Push + SMS + Google Ads local",
            "campaign_type": "geolocalizacion",
            "timing": "Activo en continuo (jueves a domingo)",
            "estimated_engagement": 0.65,
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
            "rationale": "Las reservas de último minuto tienen menor coste de adquisición. El targeting por proximidad alcanza usuarios con intención real de viaje.",
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
            "segment_users": kpis.get("audience_size", 0),
            "segment_engagement": kpis.get("avg_engagement_index", 0.75),
            "channel": "Email + WhatsApp",
            "campaign_type": "pre_arrival",
            "timing": "48h antes del check-in (automatizado)",
            "estimated_engagement": 0.78,
            "subject_line": "Mejora tu estancia antes de llegar",
            "preview_text": "Late checkout, upgrade y experiencias locales a precio especial para ti.",
            "body_summary": (
                f"Flujo automatizado que se activa 48h antes del check-in: "
                f"1) Email con 3 opciones de upgrade personalizadas por segmento (habitación superior, late checkout, pack gastronómico). "
                f"2) Si no abre el email en 12h, enviar recordatorio por WhatsApp Business con carrusel visual. "
                f"3) Incluir mapa interactivo con los partnerships locales activos y botón de reserva directa. "
                f"4) Variante para HIGH_VALUE: ofrecer acceso exclusivo a experiencia privada (cata, rooftop sunset). "
                f"Basado en señal de recepción: «{reception[0]}»."
            ),
            "deliverables": "Flujo automatizado (email + WhatsApp), 3 plantillas segmentadas, mapa interactivo, landing upsell",
            "priority": "alta",
            "rationale": f"Recepción detecta demanda real de upgrades. Automatizar maximiza la conversión sin carga operativa.",
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
            "segment": cultural_seg.get("segment_label", "EXPLORADOR_CULTURAL"),
            "segment_users": cultural_seg.get("users", 0),
            "segment_engagement": cultural_seg.get("avg_engagement_index", 0.75),
            "channel": "Multicanal (email + RRSS + hotel + partners)",
            "campaign_type": "evento",
            "timing": "Pre-evento (2 semanas), durante y post",
            "estimated_engagement": 0.82,
            "subject_line": f"Tu hotel para vivir {signal[:40]}",
            "preview_text": "Paquete exclusivo: alojamiento + itinerario del evento + experiencia Eurostars.",
            "body_summary": (
                f"Campaña 360° alrededor de «{signal}»: "
                f"PRE-EVENTO: Email a base de datos segmentada con paquete hotel+evento. Stories cuenta atrás 5 días. "
                f"DURANTE: Decoración temática en lobby (roll-up + flores/ambientación del evento). Stories en directo desde el evento. "
                f"Check-in con welcome gift temático (mapa del evento + posavasos ilustrado). "
                f"POST-EVENTO: Email UGC recopilando fotos de huéspedes durante el evento. Reels resumen 60s. "
                f"Cada fase tiene KPIs: reservas (pre), menciones social (durante), reservas futuras (post)."
            ),
            "deliverables": "Pack email (3), 15 stories, roll-up lobby, welcome gift, reels post-evento, UGC email",
            "priority": "alta",
            "rationale": f"Señal externa activa. Los eventos generan picos de demanda predecibles y contenido de alto valor para RRSS.",
        })

    # ── 8. Decoración: Rediseño espacios comunes ─────────────
    proposals.append({
        "id": "camp-008",
        "category": "decoracion",
        "category_label": "Decoración",
        "name": f"Intervención artística en zonas comunes — {city1}",
        "objective": "Crear momentos 'Instagrameables' y reforzar identidad de destino",
        "segment": "JOVEN + ADULTO · Todos los perfiles",
        "segment_users": kpis.get("audience_size", 0),
        "segment_engagement": 0.72,
        "channel": "Físico / in-hotel",
        "campaign_type": "decoracion",
        "timing": "Instalación en 2 semanas, rotación trimestral",
        "estimated_engagement": 0.70,
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
        "rationale": "Los espacios 'Instagrameables' generan UGC gratuito. El 73% de viajeros millennials elige hotel con espacios fotogénicos (Booking Insights 2025).",
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
