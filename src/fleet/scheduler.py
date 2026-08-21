"""Planificateur de vols — projette les cycles C-MAPSS sur un calendrier réel.

POURQUOI CE MODULE EXISTE
-------------------------
C-MAPSS numérote les vols (cycle 1, 2, 3...) mais ne les date pas. Sans date,
impossible de parler de « flux post-vol quotidien » ni de fraîcheur J+24h :
le pipeline batch n'aurait rien à traiter chaque jour.

Ce module attribue à chaque cycle une date, un vol et un avion, en simulant
l'exploitation d'une flotte.

LIMITE ASSUMÉE
--------------
1 cycle = 1 vol, quelle que soit la durée réelle du vol. C-MAPSS indexe la
dégradation sur le cycle, pas sur le temps de vol. Le rattachement calendaire
reconstitue le flux d'exploitation ; il ne modifie pas la physique du modèle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- Référentiels ---------------------------------------------------------

# Aéroports réels (code OACI). À remplacer par OurAirports en semaine 2.
AIRPORTS = [
    "LFPG",  # Paris Charles-de-Gaulle
    "LFPO",  # Paris Orly
    "EGLL",  # Londres Heathrow
    "EDDF",  # Francfort
    "LEMD",  # Madrid
    "LIRF",  # Rome Fiumicino
    "EHAM",  # Amsterdam
    "LFMN",  # Nice
    "LFLL",  # Lyon
    "LFBO",  # Toulouse
]

# Bases principales : les moteurs y sont rattachés en priorité.
HUBS = ["LFPG", "LFPO", "LFLL"]

# Fenêtre d'entrée en service de la flotte.
EIS_START = pd.Timestamp("2022-01-01")
EIS_END = pd.Timestamp("2023-06-30")

# Rythme d'exploitation : nombre de vols par jour et par appareil.
FLIGHTS_PER_DAY = (2, 4)


def _tail_number(i: int) -> str:
    """Immatriculation française : F-G suivi de 3 lettres. Ex. F-GKXA."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    a, b, c = (i // 676) % 26, (i // 26) % 26, i % 26
    return f"F-G{letters[a]}{letters[b]}{letters[c]}"


# --- Étape 1 : construire la flotte ---------------------------------------


def build_fleet(engine_ids, seed: int = 42, id_col: str = "unit_number") -> pd.DataFrame:
    """Une ligne par moteur : son avion, sa base, sa date de mise en service.

    `id_col` désigne la colonne qui identifie un moteur de façon UNIQUE.
    Attention : dans C-MAPSS, les numéros de moteur repartent de 1 dans chaque
    sous-jeu et dans chaque split. Le moteur 66 de FD001 et le moteur 66 de
    FD003 sont deux moteurs différents. Passer `unit_number` produirait donc
    deux appareils avec la même immatriculation — utiliser `engine_id`.

    Le `seed` garantit que deux exécutions produisent la même flotte.
    C'est une exigence de traçabilité : une prédiction doit rester
    reproductible, donc les données qui l'ont produite aussi.
    """
    units = sorted(set(engine_ids))
    rng = np.random.default_rng(seed)

    span = (EIS_END - EIS_START).days

    return pd.DataFrame(
        {
            id_col: units,
            "tail_number": [_tail_number(i) for i in range(len(units))],
            "base_airport": rng.choice(HUBS, size=len(units)),
            "eis_date": EIS_START + pd.to_timedelta(rng.integers(0, span, len(units)), unit="D"),
            "flights_per_day": rng.integers(FLIGHTS_PER_DAY[0], FLIGHTS_PER_DAY[1] + 1, len(units)),
        }
    )


# --- Étape 2 : dater les cycles -------------------------------------------


def schedule_flights(
    df: pd.DataFrame, fleet: pd.DataFrame, seed: int = 42, id_col: str = "unit_number"
) -> pd.DataFrame:
    """Ajoute date de vol, aéroports et numéro de vol à chaque cycle.

    Principe : le moteur enchaîne des allers-retours depuis sa base.
    Cycle impair  → base  →  destination
    Cycle pair    → destination → base
    """
    out = df.merge(fleet, on=id_col, how="left", validate="many_to_one")

    if out["tail_number"].isna().any():
        raise ValueError("Des moteurs n'ont pas de correspondance dans la flotte.")

    # Date : (cycle - 1) // vols_par_jour donne le nombre de jours écoulés.
    jours = (out["time_in_cycles"] - 1) // out["flights_per_day"]
    out["flight_date"] = out["eis_date"] + pd.to_timedelta(jours, unit="D")

    # L'avion enchaîne des ALLERS-RETOURS. Les cycles 1 et 2 forment la
    # rotation n°1, les cycles 3 et 4 la rotation n°2, etc. Les deux vols
    # d'une même rotation doivent partager la même escale, sinon l'avion
    # atterrit à Londres et redécolle d'Orly.
    cycle = out["time_in_cycles"].to_numpy(dtype="int64")
    rotation = (cycle + 1) // 2

    # Tirage déterministe : même moteur + même rotation → même escale.
    # `factorize` transforme un identifiant quelconque (texte ou entier)
    # en index numérique stable, pour pouvoir l'utiliser dans le calcul.
    cle, _ = pd.factorize(out[id_col])
    graine = cle.astype("int64") * 100_000 + rotation
    idx = (graine * 2_654_435_761 + seed) % len(AIRPORTS)
    escale = np.array(AIRPORTS)[idx]

    # Si l'escale tirée est la base du moteur, on décale d'un cran.
    meme = escale == out["base_airport"].to_numpy()
    escale = np.where(meme, np.array(AIRPORTS)[(idx + 1) % len(AIRPORTS)], escale)

    aller = cycle % 2 == 1
    out["origin"] = np.where(aller, out["base_airport"], escale)
    out["destination"] = np.where(aller, escale, out["base_airport"])

    out["flight_id"] = (
        out["tail_number"]
        + "_"
        + out["flight_date"].dt.strftime("%Y%m%d")
        + "_"
        + out["time_in_cycles"].astype(str)
    )

    # Colonnes de partitionnement pour l'écriture Parquet.
    out["flight_year"] = out["flight_date"].dt.year
    out["flight_month"] = out["flight_date"].dt.month

    return out.drop(columns=["eis_date", "flights_per_day"])


def add_flight_calendar(
    df: pd.DataFrame, seed: int = 42, id_col: str = "unit_number"
) -> pd.DataFrame:
    """Raccourci : construit la flotte et date les cycles en une fois."""
    fleet = build_fleet(df[id_col], seed=seed, id_col=id_col)
    return schedule_flights(df, fleet, seed=seed, id_col=id_col)
