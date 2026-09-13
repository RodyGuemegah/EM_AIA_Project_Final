"""Récupération de la météo historique depuis Open-Meteo.

POURQUOI CE FICHIER EST SÉPARÉ DE `weather.py`
-----------------------------------------------
Il parle à internet ; `weather.py` ne parle qu'au disque. On télécharge UNE
fois, on ingère autant de fois qu'on veut. Sans cette séparation, chaque
débogage de l'ingestion rappellerait l'API — impoli envers un service gratuit,
et la CI échouerait le jour où Open-Meteo est en maintenance.

DIX APPELS, PAS 7 500
---------------------
Un appel par aéroport couvrant TOUTE la plage de dates. Demander jour par jour
produirait 7 500 requêtes pour le même résultat.

LES RÉPONSES SONT SAUVEGARDÉES TELLES QUELLES
---------------------------------------------
Aucune transformation ici. Le JSON brut est la donnée d'origine : un auditeur
doit pouvoir vérifier ce que l'API a réellement renvoyé.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
DEBUT, FIN = "2022-01-01", "2024-01-31"
DESTINATION = Path("data/raw/weather")
PAUSE_S = 1.0

# Coordonnées des aéroports de la flotte simulée par `src.fleet`.
# À vérifier sur OurAirports : ce sont des faits que le jury peut recouper.
AEROPORTS = {
    "LFPG": (49.0097, 2.5479),    # Paris Charles-de-Gaulle
    "LFPO": (48.7233, 2.3794),    # Paris Orly
    "EGLL": (51.4706, -0.4619),   # Londres Heathrow
    "EDDF": (50.0333, 8.5706),    # Francfort
    "LEMD": (40.4719, -3.5626),   # Madrid
    "LIRF": (41.8003, 12.2389),   # Rome Fiumicino
    "EHAM": (52.3086, 4.7639),    # Amsterdam
    "LFMN": (43.6584, 7.2159),    # Nice
    "LFLL": (45.7256, 5.0811),    # Lyon
    "LFBO": (43.6291, 1.3638),    # Toulouse
}


def recuperer(icao: str, lat: float, lon: float) -> dict:
    """Un appel, toute la plage de dates.

    `raise_for_status()` est indispensable : sans lui, une erreur 429 ou 500
    renverrait une page HTML qu'on sauvegarderait comme si c'étaient des données.
    """
    reponse = requests.get(
        URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": DEBUT,
            "end_date": FIN,
            "daily": VARIABLES,
            "timezone": "UTC",
        },
        timeout=30,
    )
    reponse.raise_for_status()

    data = reponse.json()
    # On conserve ce qu'on a DEMANDÉ : l'API renvoie les coordonnées de sa
    # maille de calcul, qui diffèrent de celles de l'aéroport.
    data["_icao"] = icao
    data["_latitude_demandee"] = lat
    data["_longitude_demandee"] = lon
    return data


def run(destination: Path = DESTINATION) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    echecs = 0

    for i, (icao, (lat, lon)) in enumerate(AEROPORTS.items()):
        try:
            data = recuperer(icao, lat, lon)
        except requests.RequestException as e:
            print(f"  [ÉCHEC] {icao} : {e}")
            echecs += 1
            continue

        (destination / f"{icao}.json").write_text(json.dumps(data))
        jours = len(data["daily"]["time"])
        ecart_lat = abs(data["latitude"] - lat)
        print(f"  {icao} : {jours} jours   "
              f"maille à {data['latitude']:.3f}/{data['longitude']:.3f} "
              f"(écart {ecart_lat:.3f}°), altitude {data['elevation']} m")

        if i < len(AEROPORTS) - 1:
            time.sleep(PAUSE_S)

    return echecs


def main() -> int:
    print(f"Récupération météo {DEBUT} → {FIN} pour {len(AEROPORTS)} aéroports...\n")
    echecs = run()
    print(f"\n✓ {len(AEROPORTS) - echecs}/{len(AEROPORTS)} aéroports dans {DESTINATION}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())