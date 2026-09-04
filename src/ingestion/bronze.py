"""Couche BRONZE — ingestion des données brutes vers le data lake.

QU'EST-CE QUE LA COUCHE BRONZE ?
--------------------------------
L'architecture en médaillon découpe le traitement en trois couches :

    BRONZE   la donnée telle qu'elle est arrivée, + traçabilité
    SILVER   la donnée nettoyée, normalisée, prête à l'usage
    GOLD     la donnée modélisée pour l'analyse (schéma en étoile)

Règle d'or : le bronze NE NETTOIE PAS. On n'y retire aucune colonne, on ne
corrige aucune valeur aberrante, on ne plafonne pas le RUL. Pourquoi ?
Parce que la traçabilité EASA impose de pouvoir rejouer un traitement deux ans
plus tard et de justifier une décision de maintenance. Si on nettoie dès
l'ingestion, la donnée d'origine est perdue et cette justification devient
impossible.

CE QUE LE BRONZE AJOUTE MALGRÉ TOUT
-----------------------------------
1. Des colonnes de traçabilité (qui, quand, depuis quel fichier).
2. Le rattachement calendaire produit par `src.fleet`.

Le point 2 mérite justification : dater un vol ressemble à de la
transformation. Mais dans la réalité SAFRAN, les données post-vol arrivent
DÉJÀ horodatées et rattachées à un appareil — c'est une métadonnée native du
flux. C-MAPSS ne la fournit pas ; le planificateur la reconstitue. Elle relève
donc de l'ingestion, pas de la transformation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.cmapss import load_test, load_train
from src.fleet import add_flight_calendar
from src.storage import get_lake_filesystem, lake_path

PIPELINE_VERSION = "0.1.0"
SUBSETS = ["FD001", "FD002", "FD003", "FD004"]


def _add_lineage(df: pd.DataFrame, source_file: Path, subset: str, split: str) -> pd.DataFrame:
    """Ajoute les colonnes de traçabilité.

    Sans elles, impossible de répondre à « d'où vient cette ligne ? » —
    question que le jury peut poser, et qu'un auditeur EASA posera.
    """
    df = df.copy()
    df["fd_subset"] = subset
    df["split"] = split
    df["source_file"] = source_file.name
    df["ingested_at"] = datetime.now(timezone.utc)
    df["pipeline_version"] = PIPELINE_VERSION
    return df


def ingest_subset(subset: str, data_dir: Path) -> pd.DataFrame:
    """Charge train + test d'un sous-jeu et ajoute la traçabilité.

    Ne date PAS les vols : la flotte doit être construite une seule fois,
    sur l'ensemble des sous-jeux, sinon les immatriculations se répètent
    d'un sous-jeu à l'autre. C'est le rôle de `run()`.
    """
    data_dir = Path(data_dir)
    train_file = data_dir / f"train_{subset}.txt"
    test_file = data_dir / f"test_{subset}.txt"
    rul_file = data_dir / f"RUL_{subset}.txt"

    for f in (train_file, test_file, rul_file):
        if not f.exists():
            raise FileNotFoundError(f"Fichier manquant : {f}")

    # rul_cap=None : le plafond à 125 est un CHOIX DE MODÉLISATION.
    # Il appartient à la couche silver, pas au bronze.
    train = _add_lineage(load_train(train_file, rul_cap=None), train_file, subset, "train")
    test = _add_lineage(load_test(test_file, rul_file, rul_cap=None), test_file, subset, "test")

    df = pd.concat([train, test], ignore_index=True)

    # Les moteurs train et test portent les mêmes numéros : on les distingue
    # avant de construire la flotte, sinon deux moteurs différents
    # partageraient la même immatriculation.
    df["engine_id"] = df["fd_subset"] + "_" + df["split"] + "_" + df["unit_number"].astype(str)

    return df


def write_bronze(df: pd.DataFrame, out_dir: str, filesystem=None) -> str:
    """Écrit en Parquet partitionné par année/mois de vol.

    POURQUOI PARTITIONNER ?
    Sans partition, lire un mois de données oblige à scanner l'ensemble du
    fichier. Avec, le moteur de requête ne lit que le dossier concerné.
    C'est ce qui rend l'architecture tenable à l'échelle pluri-annuelle.

    POURQUOI PARQUET ET PAS CSV ?
    Format colonnaire compressé : une requête sur 3 capteurs ne lit que ces
    3 colonnes, et le fichier pèse plusieurs fois moins lourd.

    POURQUOI UN PARAMÈTRE `filesystem` ?
    Il découple la logique d'écriture du lieu de stockage. Par défaut
    (`None`), PyArrow écrit sur le disque local — c'est ce qui permet aux
    tests de tourner sans MinIO. En production, on lui passe le client S3
    construit par `src.storage`.
    """
    pq.write_to_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        root_path=out_dir,
        filesystem=filesystem,
        partition_cols=["flight_year", "flight_month"],
        existing_data_behavior="delete_matching",
        compression="snappy",
    )
    return out_dir


def run(data_dir, out_dir=None, subsets=None, seed=42, filesystem=None):
    subsets = subsets or SUBSETS
    frames = [ingest_subset(s, Path(data_dir)) for s in subsets]
    df = pd.concat(frames, ignore_index=True)
    df = add_flight_calendar(df, seed=seed, id_col="engine_id")

    if filesystem is None:
        filesystem = get_lake_filesystem()
    if out_dir is None:
        out_dir = lake_path("bronze", "engine_sensors")

    write_bronze(df, out_dir, filesystem=filesystem)
    return df
