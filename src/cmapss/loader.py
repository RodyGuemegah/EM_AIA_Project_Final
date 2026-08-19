"""Chargement du jeu NASA C-MAPSS et calcul du RUL.

Format des fichiers C-MAPSS (train_FDxxx.txt / test_FDxxx.txt) :
26 colonnes séparées par des espaces, sans en-tête.
    1  : unit_number     identifiant du moteur
    2  : time_in_cycles  numéro du cycle de vol
    3-5: op_setting_1..3 réglages opératoires (définissent le régime de vol)
    6-26: sensor_01..21  mesures capteurs

Les fichiers RUL_FDxxx.txt donnent, pour le jeu de test uniquement,
le RUL réel de chaque moteur au dernier cycle observé.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# --- Schéma ---------------------------------------------------------------

OP_SETTINGS = [f"op_setting_{i}" for i in range(1, 4)]
SENSORS = [f"sensor_{i:02d}" for i in range(1, 22)]
COLUMNS = ["unit_number", "time_in_cycles", *OP_SETTINGS, *SENSORS]

# Plafond du RUL en escalier (piecewise linear).
# Justification : en début de vie, la dégradation n'est pas encore observable
# par les capteurs. Prédire un RUL de 300 revient à apprendre du bruit.
# 125 est la valeur de référence dans la littérature C-MAPSS.
RUL_CAP = 125


# --- Chargement -----------------------------------------------------------


def _read_raw(path: Path) -> pd.DataFrame:
    """Lit un fichier C-MAPSS brut (séparateur espace, largeur variable)."""
    df = pd.read_csv(path, sep=r"\s+", header=None, engine="python")

    # Certains fichiers comportent 2 colonnes vides en fin de ligne.
    df = df.dropna(axis=1, how="all")
    if df.shape[1] != len(COLUMNS):
        raise ValueError(
            f"{path.name}: {df.shape[1]} colonnes lues, {len(COLUMNS)} attendues."
        )

    df.columns = COLUMNS
    return df.astype({"unit_number": "int32", "time_in_cycles": "int32"})


def load_train(path: str | Path, rul_cap: int | None = RUL_CAP) -> pd.DataFrame:
    """Charge un fichier d'entraînement et ajoute la colonne `rul`.

    Sur le jeu d'entraînement, chaque moteur est suivi jusqu'à la panne :
    le RUL se déduit donc directement de la durée totale observée.
    """
    df = _read_raw(Path(path))
    last_cycle = df.groupby("unit_number")["time_in_cycles"].transform("max")
    df["rul"] = last_cycle - df["time_in_cycles"]

    if rul_cap is not None:
        df["rul"] = df["rul"].clip(upper=rul_cap)

    return df


def load_test(
    path: str | Path, rul_path: str | Path, rul_cap: int | None = RUL_CAP
) -> pd.DataFrame:
    """Charge un fichier de test et ajoute la colonne `rul`.

    Sur le jeu de test, le suivi s'arrête AVANT la panne. Le RUL restant au
    dernier cycle est fourni séparément dans RUL_FDxxx.txt ; on le propage
    en remontant les cycles.
    """
    df = _read_raw(Path(path))

    rul_final = pd.read_csv(rul_path, sep=r"\s+", header=None, engine="python")
    rul_final = rul_final.dropna(axis=1, how="all").iloc[:, 0]
    rul_final.index = range(1, len(rul_final) + 1)  # unit_number commence à 1

    last_cycle = df.groupby("unit_number")["time_in_cycles"].transform("max")
    df["rul"] = df["unit_number"].map(rul_final) + (last_cycle - df["time_in_cycles"])

    if rul_cap is not None:
        df["rul"] = df["rul"].clip(upper=rul_cap)

    return df


# --- Nettoyage ------------------------------------------------------------


def constant_sensors(df: pd.DataFrame, tol: float = 1e-9) -> list[str]:
    """Retourne les capteurs de variance nulle.

    Plusieurs capteurs C-MAPSS sont plats sur FD001/FD003 : ils n'apportent
    aucune information et gonflent inutilement l'espace de features.
    Les retirer est un choix à documenter dans un ADR.
    """
    present = [c for c in SENSORS if c in df.columns]
    return [c for c in present if df[c].std(ddof=0) <= tol]


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par moteur : durée de vie observée. Utile pour l'EDA."""
    return (
        df.groupby("unit_number")
        .agg(
            cycles_observes=("time_in_cycles", "max"),
            rul_min=("rul", "min"),
            rul_max=("rul", "max"),
        )
        .reset_index()
    )
