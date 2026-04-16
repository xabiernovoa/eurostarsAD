#!/usr/bin/env python3
"""
send_campaign.py — Fase 8: envío y trazabilidad de campañas

Envía emails vía SendGrid o los guarda en disco en modo --dry-run.
Registra todas las campañas en campaign_log.json con parámetros UTM.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import OUTPUT_DIR
from backend.personalization.segment_views import get_age_key, get_segment_label, get_segment_slug
from backend.storage.campaign_log import load_campaign_log, save_campaign_log

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("send_campaign")
_LOG_LOCK = Lock()

def _load_log() -> list[dict]:
    """Carga el registro actual de campañas."""
    return load_campaign_log()


def _save_log(log: list[dict]) -> None:
    """Guarda el registro de campañas."""
    save_campaign_log(log)


def _inject_utm(html: str, segment: dict, moment: str) -> str:
    """Garantiza que todos los enlaces incluyan parámetros UTM."""
    # Los parámetros UTM ya salen de copy.cta_url_suffix en las plantillas.
    # Aquí añadimos utm_content con información de segmento al resto de enlaces.
    utm_content = f"seg_{get_segment_slug(segment)}"
    html = html.replace("utm_content=joven", f"utm_content={utm_content}")
    html = html.replace("utm_content=adulto", f"utm_content={utm_content}")
    html = html.replace("utm_content=senior", f"utm_content={utm_content}")
    return html


def send_email_sendgrid(
    to_email: str,
    subject: str,
    html_content: str,
) -> bool:
    """Envía un email usando la API de SendGrid."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key or api_key.startswith("SG.xxxxx"):
        logger.warning("No hay una API key válida de SendGrid")
        return False

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        sender = os.environ.get("SENDER_EMAIL", "noreply@eurostarshotels.com")
        message = Mail(
            from_email=sender,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logger.info("Respuesta de SendGrid: %d", response.status_code)
        return response.status_code in (200, 201, 202)

    except Exception as e:
        logger.error("Ha fallado el envío con SendGrid: %s", e)
        return False


def send_campaign(
    campaign_data: dict,
    html: str,
    copy: dict,
    channel: dict,
    sms_text: str = "",
    dry_run: bool = True,
) -> dict:
    """Envía o guarda una campaña y registra el resultado."""
    guest_id = campaign_data.get("guest_id", "")
    moment = campaign_data.get("campaign_type", "unknown")
    segment = campaign_data.get("segment", {})

    # Inyectar parámetros UTM
    html = _inject_utm(html, segment, moment)

    primary_channel = channel.get("primary_channel", "email")

    log_entry = {
        "guest_id": guest_id,
        "channel": primary_channel,
        "template": f"template_{get_age_key(segment).lower()}.html",
        "campaign_type": moment,
        "hotel_recommended": "",
        "segment_label": get_segment_label(segment),
        "subject": copy.get("subject", ""),
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
        "dry_run": dry_run,
    }
    contact_phone = str(campaign_data.get("contact_phone", "")).strip()
    if contact_phone:
        log_entry["phone_target"] = contact_phone

    # Extraer información del hotel
    hotel = campaign_data.get("recommended_hotel", campaign_data.get("last_stay", {}))
    log_entry["hotel_recommended"] = hotel.get("name", hotel.get("hotel_name", ""))

    if dry_run:
        # Guardar HTML en disco
        OUTPUT_DIR.mkdir(exist_ok=True)
        filename = f"{moment}_{guest_id}.html"
        path = OUTPUT_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        log_entry["status"] = "saved_to_disk"
        log_entry["output_file"] = filename
        logger.info("Dry-run: %s guardado en %s", filename, OUTPUT_DIR)

        # La demo no usa ficheros SMS sueltos; solo guardamos una vista previa en el log.
        if sms_text and primary_channel == "sms":
            log_entry["sms_preview"] = sms_text[:160]

    else:
        # Envío real
        if primary_channel == "email":
            success = send_email_sendgrid(
                to_email=f"guest_{guest_id}@example.com",  # Marcador de posición
                subject=copy.get("subject", "Eurostars Hotels"),
                html_content=html,
            )
            log_entry["status"] = "sent" if success else "failed"
        elif primary_channel == "sms":
            # El SMS se enviaría por Twilio o similar; aquí queda simulado
            log_entry["status"] = "sms_mock_sent"
            log_entry["sms_text"] = sms_text[:160]
        else:
            # Notificación push simulada
            log_entry["status"] = "push_mock_sent"

    # Añadir al registro de campañas
    with _LOG_LOCK:
        log = _load_log()
        log.append(log_entry)
        _save_log(log)

    return log_entry


def send_batch(
    campaigns: list[dict],
    htmls: list[str],
    copies: list[dict],
    channels: list[dict],
    sms_texts: list[str],
    dry_run: bool = True,
) -> list[dict]:
    """Envía un lote de campañas."""
    results = []
    for i, (campaign, html, copy, channel) in enumerate(
        zip(campaigns, htmls, copies, channels)
    ):
        sms = sms_texts[i] if i < len(sms_texts) else ""
        result = send_campaign(campaign, html, copy, channel, sms, dry_run)
        results.append(result)

    # Resumen
    statuses = {}
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
    logger.info("Lote completado — %d campañas: %s", len(results), statuses)

    return results


def main():
    log = _load_log()
    logger.info("El registro de campañas tiene %d entradas", len(log))
    if log:
        for entry in log[-5:]:
            logger.info("  %s — %s — %s — %s",
                        entry["guest_id"], entry["campaign_type"],
                        entry["channel"], entry["status"])


if __name__ == "__main__":
    main()
