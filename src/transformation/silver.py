"""Couche SILVER — nettoyage et features d'historique.

Le bronze contient DES VALEURS. Le silver contient UNE TRAJECTOIRE.

Trois opérations :
  1. retirer les capteurs plats (aucune information)
  2. étiqueter le régime de vol (altitude / Mach / manette)
  3. construire l'historique : moyenne, pente, dérive depuis le neuf

CE QUE LE SILVER NE FAIT PAS : normaliser.
Soustraire une moyenne ou diviser par un écart-type suppose de CALCULER
ces nombres sur les données — y compris sur les moteurs d'examen. C'est une
fuite. La normalisation appartient au Pipeline du modèle, ajusté sur le
tas d'apprentissage seul.

LECTURE NON PARTITIONNÉE — l'historique d'un moteur traverse 2 à 6 dossiers
mensuels. Calculer une moyenne glissante dossier par dossier serait faux.
"""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.cmapss import SENSORS
from src.storage import get_lake_filesystem, lake_path

RUL_CAP = 125
FENETRE = 20  


def read_bronze(filesystem=None) -> pd.DataFrame:
    """Charge tout le  lake bronze, trié par moteur puis par vol."""
    if filesystem is None:
        filesystem = get_lake_filesystem()

    df = pq.read_table(
        lake_path("bronze", "engine_sensors"), filesystem=filesystem
    ).to_pandas()

    return df.sort_values(["engine_id", "time_in_cycles"]).reset_index(drop=True)

def delete_flat_sensors_(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Supprime les capteurs plats et renvoie la liste des capteurs CONSERVÉS.

    Le second élément du tuple alimente `add_history` : ce sont les colonnes
    encore présentes dans le DataFrame retourné.
    """
    # On ne peut pas se contenter de regarder la variance : un capteur constant
    # sur l'ensemble du bronze peut varier sur un sous-jeu. On regarde donc
    # chaque sous-jeu séparément.
    flat_sensors = []
    for s in SENSORS:
        if df.groupby("fd_subset")[s].nunique().max() == 1:
            flat_sensors.append(s)
    # On renvoie les capteurs CONSERVÉS : c'est sur eux que porte l'historique.
    kept = [s for s in SENSORS if s not in flat_sensors]
    return df.drop(columns=flat_sensors), kept


def define_flight_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Étiquette le régime de vol (altitude / Mach / manette)."""
    # TODO : implémenter la logique pour définir le régime de vol

    df = df.copy()
    df["regime"] = (
        (df.op_setting_1.round(0) + 0.0).astype(int).astype(str) + "_"
        + (df.op_setting_2.round(2) + 0.0).astype(str) + "_"
        + (df.op_setting_3.round(0) + 0.0).astype(int).astype(str)
    )
    return df  # Placeholder, à remplacer par la logique réelle

def add_history(df: pd.DataFrame, capteurs: list[str]) -> pd.DataFrame:
    """Ajoute 3 colonnes par capteur : moyenne glissante, pente, dérive.

    LE groupby("engine_id") EST VITAL. Sans lui, la moyenne du premier vol
    du moteur 42 inclurait les derniers vols du moteur 41 — deux machines
    différentes mélangées. C'est le même piège que l'avion qui téléportait.

    Aucune fuite ici : la moyenne du moteur 1 n'utilise QUE le passé du
    moteur 1. Aucune autre machine n'intervient.
    """
    df = df.copy()
    g = df.groupby("engine_id")

    for c in capteurs:
        # Niveau moyen récent — lisse le bruit vol à vol.
        # min_periods=1 : dès le 1er vol on a une valeur, pas de NaN.
        df[f"{c}_moy{FENETRE}"] = g[c].transform(
            lambda s: s.rolling(FENETRE, min_periods=1).mean()
        )
        # Pente : de combien ça bouge en moyenne d'un vol à l'autre.
        df[f"{c}_pente"] = g[c].transform(
            lambda s: s.diff().rolling(FENETRE, min_periods=1).mean().fillna(0)
        )
        # Dérive : écart par rapport au moteur neuf. Souvent la plus forte.
        df[f"{c}_derive"] = df[c] - g[c].transform("first")

    return df

def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Enchaîne les trois opérations, dans l'ordre."""
    df, capteurs = delete_flat_sensors_(df)
    df = define_flight_regime(df)
    df = add_history(df, capteurs)

    # Plafond du RUL : choix de modélisation, assumé ici.
    df["rul"] = df.rul.clip(upper=RUL_CAP)
    return df

def write_silver(df: pd.DataFrame, filesystem=None) -> str:
    """Écrit le silver, partitionné comme le bronze."""
    if filesystem is None:
        filesystem = get_lake_filesystem()

    chemin = lake_path("silver", "engine_features")
    pq.write_to_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        root_path=chemin,
        filesystem=filesystem,
        partition_cols=["flight_year", "flight_month"],
        existing_data_behavior="delete_matching",
        compression="snappy",
    )
    return chemin

def run(filesystem=None) -> pd.DataFrame:
    df = transform(read_bronze(filesystem))
    write_silver(df, filesystem)
    return df