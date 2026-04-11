#!/usr/bin/env python3
"""
Build profiles.json from Eurostars data for the Gmail demo interface.
Reads customer data, segments, and campaign log to create user profiles.
"""

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

EUROSTARS_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent

# Spanish first names by gender
MALE_NAMES = [
    "Carlos", "Miguel", "Alejandro", "David", "Javier", "Daniel", "Pablo",
    "Andrés", "Fernando", "Antonio", "Roberto", "Sergio", "Jorge", "Manuel",
    "Raúl", "Álvaro", "Diego", "Marcos", "Iván", "Adrián", "Hugo", "Gonzalo",
    "Rafael", "Óscar", "Tomás", "Enrique", "Pedro", "Alberto", "Luis", "Ramón"
]
FEMALE_NAMES = [
    "María", "Laura", "Carmen", "Elena", "Isabel", "Ana", "Lucía", "Marta",
    "Patricia", "Cristina", "Sofía", "Beatriz", "Paula", "Raquel", "Inés",
    "Clara", "Rosa", "Teresa", "Valentina", "Nuria", "Pilar", "Rocío",
    "Silvia", "Victoria", "Sara", "Eva", "Irene", "Julia", "Claudia", "Diana"
]
ITALIAN_MALE = [
    "Marco", "Luca", "Alessandro", "Andrea", "Matteo", "Lorenzo", "Giuseppe",
    "Francesco", "Giovanni", "Stefano", "Davide", "Simone", "Pietro", "Fabio",
    "Roberto", "Massimo", "Paolo", "Enrico", "Riccardo", "Emanuele"
]
ITALIAN_FEMALE = [
    "Giulia", "Francesca", "Chiara", "Valentina", "Alessia", "Sara", "Elena",
    "Martina", "Silvia", "Federica", "Paola", "Elisa", "Roberta", "Monica",
    "Anna", "Patrizia", "Lucia", "Ilaria", "Daniela", "Veronica"
]
PT_MALE = [
    "João", "Pedro", "Ricardo", "Tiago", "André", "Bruno", "Nuno", "Diogo",
    "Rui", "Filipe", "Miguel", "Carlos", "Paulo", "António", "Gonçalo"
]
PT_FEMALE = [
    "Ana", "Maria", "Catarina", "Sofia", "Marta", "Joana", "Inês", "Beatriz",
    "Raquel", "Teresa", "Rita", "Filipa", "Cláudia", "Mariana", "Helena"
]
SURNAMES_ES = [
    "García", "Martínez", "López", "González", "Rodríguez", "Fernández",
    "Sánchez", "Pérez", "Gómez", "Díaz", "Moreno", "Ruiz", "Jiménez",
    "Álvarez", "Romero", "Navarro", "Torres", "Domínguez", "Ramos", "Gil"
]
SURNAMES_IT = [
    "Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo",
    "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "De Luca",
    "Costa", "Giordano", "Mancini", "Rizzo", "Lombardi", "Moretti"
]
SURNAMES_PT = [
    "Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues",
    "Martins", "Sousa", "Fernandes", "Gonçalves", "Gomes", "Lopes", "Marques",
    "Alves", "Almeida", "Ribeiro", "Pinto", "Carvalho", "Teixeira"
]

AVATAR_COLORS = [
    "#1a73e8", "#ea4335", "#34a853", "#fbbc04", "#673ab7",
    "#e91e63", "#ff5722", "#009688", "#3f51b5", "#795548",
    "#607d8b", "#f44336", "#4caf50", "#2196f3", "#ff9800",
    "#9c27b0", "#00bcd4", "#8bc34a", "#ff6f00", "#5c6bc0"
]

TRAVEL_PROFILE_LABELS = {
    "LUJO": "🏨 Lujo",
    "EXPLORADOR_CULTURAL": "🏛️ Explorador Cultural",
    "AVENTURERO": "🌍 Aventurero",
    "GASTRONOMIA_CIUDAD": "🍽️ Gastronomía & Ciudad"
}

AGE_SEGMENT_LABELS = {
    "JOVEN": "Joven",
    "ADULTO": "Adulto",
    "SENIOR": "Senior"
}

CLIENT_VALUE_LABELS = {
    "STANDARD": "Standard",
    "MID_VALUE": "Mid Value",
    "HIGH_VALUE": "High Value"
}

COUNTRY_FLAGS = {"ES": "🇪🇸", "IT": "🇮🇹", "PT": "🇵🇹"}
COUNTRY_DOMAINS = {"ES": "gmail.com", "IT": "gmail.com", "PT": "gmail.com"}


def generate_name(gender: str, country: str, rng: random.Random) -> tuple[str, str]:
    if country == "IT":
        first = rng.choice(ITALIAN_MALE if gender == "Masculino" else ITALIAN_FEMALE)
        last = rng.choice(SURNAMES_IT)
    elif country == "PT":
        first = rng.choice(PT_MALE if gender == "Masculino" else PT_FEMALE)
        last = rng.choice(SURNAMES_PT)
    else:
        first = rng.choice(MALE_NAMES if gender == "Masculino" else FEMALE_NAMES)
        last = rng.choice(SURNAMES_ES)
    return first, last


def main():
    # Load data
    with open(EUROSTARS_DIR / "data" / "segments.json") as f:
        segments = json.load(f)

    with open(EUROSTARS_DIR / "data" / "customer_data_200.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        customers = {row["GUEST_ID"]: row for row in reader}

    with open(EUROSTARS_DIR / "data" / "campaign_log.json") as f:
        campaign_log = json.load(f)

    # Deduplicate campaign log
    seen = set()
    unique_log = []
    for entry in campaign_log:
        if entry["output_file"] not in seen:
            seen.add(entry["output_file"])
            unique_log.append(entry)

    # Group campaigns by guest
    user_campaigns = defaultdict(list)
    for entry in unique_log:
        user_campaigns[entry["guest_id"]].append(entry)

    # Build profiles
    profiles = []
    rng = random.Random(42)  # Deterministic

    for guest_id, seg in segments.items():
        cust = customers.get(guest_id, {})
        camps = user_campaigns.get(guest_id, [])

        first_name, last_name = generate_name(seg["gender"], seg["country"], rng)
        email = f"{first_name.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n').replace('ã','a').replace('ç','c')}.{last_name.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n').replace('ã','a').replace('ç','c')}@{COUNTRY_DOMAINS.get(seg['country'], 'gmail.com')}"

        avatar_color = rng.choice(AVATAR_COLORS)

        # Build email list for this user
        email_files = []
        for c in camps:
            if c["campaign_type"] in ("pre_arrival", "post_stay"):
                email_files.append({
                    "filename": c["output_file"],
                    "type": c["campaign_type"],
                    "subject": c["subject"],
                    "hotel": c["hotel_recommended"],
                })

        profile = {
            "guest_id": guest_id,
            "name": f"{first_name} {last_name}",
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "avatar_color": avatar_color,
            "avatar_letter": first_name[0].upper(),
            "country": seg["country"],
            "country_flag": COUNTRY_FLAGS.get(seg["country"], "🌍"),
            "gender": seg["gender"],
            "age_range": seg["age_range"],
            "age_segment": seg["age_segment"],
            "age_segment_label": AGE_SEGMENT_LABELS.get(seg["age_segment"], seg["age_segment"]),
            "travel_profile": seg["travel_profile"],
            "travel_profile_label": TRAVEL_PROFILE_LABELS.get(seg["travel_profile"], seg["travel_profile"]),
            "client_value": seg["client_value"],
            "client_value_label": CLIENT_VALUE_LABELS.get(seg["client_value"], seg["client_value"]),
            "avg_score": seg.get("avg_score", 0),
            "emails": email_files,
        }
        profiles.append(profile)

    # Sort by name
    profiles.sort(key=lambda p: p["name"])

    output = {
        "profiles": profiles,
        "email_dir": str(EUROSTARS_DIR / "output"),
        "images_dir": str(EUROSTARS_DIR / "images"),
    }

    out_path = OUTPUT_DIR / "profiles.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Generated {len(profiles)} profiles → {out_path}")
    # Stats
    by_segment = defaultdict(int)
    for p in profiles:
        by_segment[f"{p['age_segment']} / {p['travel_profile']}"] += 1
    print("\nSegment distribution:")
    for seg, count in sorted(by_segment.items()):
        print(f"  {seg}: {count}")


if __name__ == "__main__":
    main()
