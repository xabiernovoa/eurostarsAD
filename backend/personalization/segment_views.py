from __future__ import annotations

from typing import Any

AGE_RANGE_TO_KEY = {
    "19-25": "JOVEN",
    "26-35": "JOVEN",
    "36-45": "ADULTO",
    "46-65": "ADULTO",
    ">65": "SENIOR",
}

AGE_LABELS = {
    "JOVEN": "Joven",
    "ADULTO": "Adulto",
    "SENIOR": "Senior",
}

AGE_ORDER = {"JOVEN": 0, "ADULTO": 1, "SENIOR": 2}

AFFINITY_LABELS = {
    "playero": "Playero",
    "montana": "Montaña",
    "cultural": "Cultural",
    "gastronomico": "Gastronómico",
    "clima_calido": "Clima cálido",
    "mediterraneo": "Mediterráneo",
    "continental": "Continental",
}

VALUE_LABELS = {
    "esencial": "Esencial",
    "confort": "Confort",
    "premium": "Premium",
    "lujo": "Lujo",
}

VALUE_WEIGHTS = {
    "esencial": 0.48,
    "confort": 0.63,
    "premium": 0.79,
    "lujo": 0.9,
}

VALUE_BADGES = {
    "esencial": "PERFIL ESENCIAL",
    "confort": "PERFIL CONFORT",
    "premium": "PERFIL PREMIUM",
    "lujo": "PERFIL VIP ELITE",
}

THEME_LABELS = {
    "premium": "Colección Exclusiva",
    "playero": "Escapada Relax",
    "montana": "Experiencia Activa",
    "cultural": "Inmersión Cultural",
    "gastronomico": "Ruta Gastronómica",
    "clima_calido": "Destino Luminoso",
    "mediterraneo": "Escapada Mediterránea",
    "continental": "City Break Continental",
}


def _segment_tags(segment: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(segment, dict):
        return {}
    tags = segment.get("tags", {})
    return tags if isinstance(tags, dict) else {}


def _segment_metrics(segment: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(segment, dict):
        return {}
    metrics = segment.get("metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def get_age_key(segment: dict[str, Any] | None) -> str:
    tags = _segment_tags(segment)
    demographics = tags.get("demografia", {})
    if isinstance(demographics, dict):
        age = str(demographics.get("edad", "")).strip().upper()
        if age in AGE_LABELS:
            return age

    age_range = str((segment or {}).get("age_range", "")).strip()
    return AGE_RANGE_TO_KEY.get(age_range, "ADULTO")


def get_age_label(segment: dict[str, Any] | None) -> str:
    return AGE_LABELS.get(get_age_key(segment), "Adulto")


def get_age_order(segment: dict[str, Any] | None) -> int:
    return AGE_ORDER.get(get_age_key(segment), 9)


def get_affinities(segment: dict[str, Any] | None) -> list[str]:
    tags = _segment_tags(segment)
    affinities = tags.get("afinidades_destino", [])
    if isinstance(affinities, list):
        return [str(tag).strip() for tag in affinities if str(tag).strip()]
    return []


def get_primary_affinity(segment: dict[str, Any] | None) -> str:
    affinities = get_affinities(segment)
    return affinities[0] if affinities else "cultural"


def get_affinity_label(tag: str) -> str:
    return AFFINITY_LABELS.get(tag, tag.replace("_", " ").title())


def get_primary_affinity_label(segment: dict[str, Any] | None) -> str:
    return get_affinity_label(get_primary_affinity(segment))


def get_value_level(segment: dict[str, Any] | None) -> str:
    tags = _segment_tags(segment)
    level = str(tags.get("nivel_valor", "")).strip().lower()
    return level if level in VALUE_LABELS else "confort"


def get_value_label(segment: dict[str, Any] | None) -> str:
    return VALUE_LABELS.get(get_value_level(segment), "Confort")


def get_value_weight(segment: dict[str, Any] | None) -> float:
    return VALUE_WEIGHTS.get(get_value_level(segment), 0.63)


def get_value_badge(segment: dict[str, Any] | None) -> str:
    return VALUE_BADGES.get(get_value_level(segment), "PERFIL CONFORT")


def is_high_value(segment: dict[str, Any] | None) -> bool:
    return get_value_level(segment) in {"premium", "lujo"}


def get_booking_behavior(segment: dict[str, Any] | None) -> dict[str, str]:
    tags = _segment_tags(segment)
    behavior = tags.get("comportamiento_reserva", {})
    return behavior if isinstance(behavior, dict) else {}


def get_loyalty_principal(segment: dict[str, Any] | None) -> str:
    tags = _segment_tags(segment)
    loyalty = tags.get("fidelidad", {})
    if isinstance(loyalty, dict):
        return str(loyalty.get("principal", "")).strip() or "explorador"
    return "explorador"


def get_loyalty_label(segment: dict[str, Any] | None) -> str:
    principal = get_loyalty_principal(segment)
    return principal.replace("_", " ").title()


def get_theme_key(segment: dict[str, Any] | None) -> str:
    value_level = get_value_level(segment)
    affinities = get_affinities(segment)
    primary_affinity = get_primary_affinity(segment)

    if value_level in {"premium", "lujo"}:
        return "premium"
    if "playero" in affinities:
        return "playero"
    if primary_affinity in THEME_LABELS:
        return primary_affinity
    return "cultural"


def get_theme_label(segment: dict[str, Any] | None) -> str:
    return THEME_LABELS.get(get_theme_key(segment), "Selección Eurostars")


def get_segment_label(segment: dict[str, Any] | None) -> str:
    return f"{get_age_label(segment)} · {get_primary_affinity_label(segment)} · {get_value_label(segment)}"


def get_segment_slug(segment: dict[str, Any] | None) -> str:
    return "_".join(
        [
            get_age_key(segment).lower(),
            get_primary_affinity(segment),
            get_value_level(segment),
        ]
    )


def get_metrics(segment: dict[str, Any] | None) -> dict[str, Any]:
    return _segment_metrics(segment)


def get_propensity_text(segment: dict[str, Any] | None) -> str:
    affinities = set(get_affinities(segment))
    value_level = get_value_level(segment)

    if value_level in {"premium", "lujo"}:
        return "Cliente muy propenso a upgrades de categoría, spa y servicios de alto valor añadido."
    if "gastronomico" in affinities:
        return "Cliente muy propenso a reservas en restaurantes destacados y experiencias gastronómicas locales."
    if "cultural" in affinities:
        return "Cliente muy propenso a rutas culturales, visitas guiadas y propuestas vinculadas al patrimonio."
    if "playero" in affinities or "clima_calido" in affinities or "mediterraneo" in affinities:
        return "Cliente muy propenso a bienestar, terraza, piscina y experiencias de descanso al aire libre."
    if "montana" in affinities:
        return "Cliente muy propenso a turismo activo, rutas naturales y actividades deportivas."
    return "Cliente propenso a propuestas de valor claras, bien contextualizadas y fáciles de reservar."


def summarize_segment(segment: dict[str, Any] | None) -> dict[str, str]:
    return {
        "age_key": get_age_key(segment),
        "age_label": get_age_label(segment),
        "primary_affinity": get_primary_affinity(segment),
        "primary_affinity_label": get_primary_affinity_label(segment),
        "value_level": get_value_level(segment),
        "value_label": get_value_label(segment),
        "loyalty": get_loyalty_principal(segment),
        "loyalty_label": get_loyalty_label(segment),
        "theme_key": get_theme_key(segment),
        "theme_label": get_theme_label(segment),
        "label": get_segment_label(segment),
        "slug": get_segment_slug(segment),
    }
