from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from backend.paths import CAMPAIGN_LOG_PATH, CUSTOMERS_PATH, OUTPUT_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_DATA_PATH = CUSTOMERS_PATH

AGE_SEGMENT_MAP = {
    "19-25": "JOVEN",
    "26-35": "JOVEN",
    "36-45": "ADULTO",
    "46-65": "ADULTO",
    ">65": "SENIOR",
}

AGE_SEGMENT_LABELS = {
    "JOVEN": "Joven",
    "ADULTO": "Adulto",
    "SENIOR": "Senior",
}

COUNTRY_LABELS = {
    "ES": "Espana",
    "IT": "Italia",
    "PT": "Portugal",
}

AVATAR_COLORS = [
    "#1a73e8",
    "#ea4335",
    "#34a853",
    "#fbbc04",
    "#673ab7",
    "#e91e63",
    "#ff5722",
    "#009688",
    "#3f51b5",
    "#795548",
    "#607d8b",
    "#4caf50",
]

EMAIL_FILENAME_RE = re.compile(r"^(pre_arrival|post_stay)_(.+)\.html$")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
PREHEADER_RE = re.compile(
    r'<div[^>]*style="[^"]*display\s*:\s*none[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", value or "")).strip()


def _split_name(name: str) -> tuple[str, str]:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _avatar_color(guest_id: str) -> str:
    digest = hashlib.sha1(str(guest_id).encode("utf-8")).digest()
    index = int.from_bytes(digest[:2], "big") % len(AVATAR_COLORS)
    return AVATAR_COLORS[index]


def _load_campaign_log_index() -> dict[str, dict]:
    if not CAMPAIGN_LOG_PATH.exists():
        return {}

    try:
        with open(CAMPAIGN_LOG_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    latest_by_filename: dict[str, dict] = {}
    for entry in entries:
        filename = str(entry.get("output_file", "")).strip()
        if not filename:
            continue
        current = latest_by_filename.get(filename)
        if current and current.get("timestamp", "") > entry.get("timestamp", ""):
            continue
        latest_by_filename[filename] = {
            "subject": str(entry.get("subject", "")).strip(),
            "hotel": str(entry.get("hotel_recommended", "")).strip(),
            "timestamp": str(entry.get("timestamp", "")).strip(),
        }
    return latest_by_filename


def load_guest_directory() -> dict[str, dict]:
    with open(CUSTOMER_DATA_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        directory: dict[str, dict] = {}

        for row in reader:
            guest_id = str(row.get("GUEST_ID", "")).strip().strip('"')
            if not guest_id or guest_id in directory:
                continue

            name = str(row.get("GUEST_NAME", "")).strip() or f"Huesped {guest_id}"
            first_name, last_name = _split_name(name)
            country = str(row.get("COUNTRY_GUEST", "")).strip()
            age_range = str(row.get("AGE_RANGE", "")).strip()
            age_segment = AGE_SEGMENT_MAP.get(age_range, "ADULTO")

            directory[guest_id] = {
                "guest_id": guest_id,
                "name": name,
                "first_name": first_name,
                "last_name": last_name,
                "email": str(row.get("EMAIL", "")).strip(),
                "country": country,
                "country_label": COUNTRY_LABELS.get(country, country),
                "nationality": str(row.get("NATIONALITY", "")).strip(),
                "gender": str(row.get("GENDER_ID", "")).strip(),
                "age_range": age_range,
                "age_segment": age_segment,
                "age_segment_label": AGE_SEGMENT_LABELS.get(age_segment, age_segment.title()),
                "avatar_color": _avatar_color(guest_id),
                "avatar_letter": (first_name[:1] or name[:1] or "H").upper(),
            }

    return directory


def _extract_email_metadata(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    title_match = TITLE_RE.search(content)
    preheader_match = PREHEADER_RE.search(content)
    return {
        "subject": _clean_text(title_match.group(1)) if title_match else "",
        "snippet": _clean_text(preheader_match.group(1)) if preheader_match else "",
    }


def load_guest_emails() -> dict[str, list[dict]]:
    if not OUTPUT_DIR.exists():
        return {}

    log_index = _load_campaign_log_index()
    emails_by_guest: dict[str, list[dict]] = defaultdict(list)

    for path in OUTPUT_DIR.glob("*.html"):
        match = EMAIL_FILENAME_RE.match(path.name)
        if not match:
            continue

        campaign_type, guest_id = match.groups()
        extracted = _extract_email_metadata(path)
        campaign_log_entry = log_index.get(path.name, {})
        emails_by_guest[guest_id].append(
            {
                "filename": path.name,
                "type": campaign_type,
                "subject": campaign_log_entry.get("subject") or extracted["subject"] or path.stem,
                "snippet": extracted["snippet"],
                "hotel": campaign_log_entry.get("hotel", ""),
                "updated_at": path.stat().st_mtime,
            }
        )

    for emails in emails_by_guest.values():
        emails.sort(key=lambda item: (-item["updated_at"], item["filename"]))
        for email in emails:
            email.pop("updated_at", None)

    return dict(emails_by_guest)


def build_mail_profiles() -> dict[str, list[dict]]:
    guests = load_guest_directory()
    emails_by_guest = load_guest_emails()

    profiles = []
    for guest_id, guest in sorted(guests.items(), key=lambda item: item[1]["name"].lower()):
        profiles.append(
            {
                **guest,
                "emails": emails_by_guest.get(guest_id, []),
            }
        )

    return {"profiles": profiles}
