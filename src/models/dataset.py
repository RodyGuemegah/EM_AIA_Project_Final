"""Préparation des données pour l'entraînement.

Va chercher les données dans le lake et les prépare pour le modèle :
filtrage, sélection de colonnes, séparation apprentissage / examen.
"""

from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq
from sklearn.model_selection import GroupShuffleSplit

from src.storage import get_lake_filesystem, lake_path


def load_bronze(subset="FD001", split="train", columns=None, filesystem=None) -> pd.DataFrame:
    """Lit le bronze depuis le lake.

    subset : "FD001" à "FD004", ou None pour tout prendre
    split  : "train" ou "test"
    """
    # 1. la clé de l'entrepôt (comme dans bronze.py : None => on la construit)
    if filesystem is None:
        filesystem = get_lake_filesystem()

    # 2. l'adresse du rayon
    chemin = lake_path("bronze", "engine_sensors")

    # 3. quels cartons on veut
    #    Syntaxe PyArrow : une LISTE de TUPLES (colonne, opérateur, valeur).
    #    Les conditions sont combinées avec ET.
    #    Exemple : [("fd_subset", "=", "FD001"), ("split", "=", "train")]
    filtres = []
    if subset is not None:
        filtres.append(("fd_subset", "=", subset))
    if split is not None:
        filtres.append(("split", "=", split))

    # 4. on va chercher
    table = pq.read_table(
        chemin,
        filesystem=filesystem,
        columns=columns,
        filters=filtres or None,   # None si la liste est vide
    )
    return table.to_pandas()

def split_par_moteur(df, test_size=0.2, seed=42):
    """Sépare les moteurs : 80 % pour apprendre, 20 % pour l'examen.

    JAMAIS ligne par ligne — un moteur entier va d'un côté ou de l'autre.
    """
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    idx_train, idx_test = next(gss.split(df, groups=df["engine_id"]))
    return df.iloc[idx_train], df.iloc[idx_test]