"""Tests de la couche bronze.

`test_immatriculations_uniques` protège contre un bug subtil : les numéros de
moteur C-MAPSS repartent de 1 dans chaque sous-jeu. Sans identifiant global,
deux moteurs distincts recevraient la même immatriculation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.cmapss import COLUMNS
from src.ingestion.bronze import run

SUBSETS_TEST = ["FD001", "FD003"]


@pytest.fixture
def faux_cmapss(tmp_path):
    """Crée un mini C-MAPSS complet (train, test, RUL) pour 2 sous-jeux."""
    rng = np.random.default_rng(0)

    def ecrire(nom, units, longueurs):
        rows = []
        for u, n in zip(units, longueurs, strict=True):
            for c in range(1, n + 1):
                rows.append([u, c, *rng.normal(size=3), *rng.normal(size=21)])
        pd.DataFrame(rows, columns=COLUMNS).to_csv(
            tmp_path / nom, sep=" ", header=False, index=False
        )

    for fd in SUBSETS_TEST:
        ecrire(f"train_{fd}.txt", (1, 2, 3), (20, 30, 25))
        ecrire(f"test_{fd}.txt", (1, 2, 3), (10, 12, 8))
        (tmp_path / f"RUL_{fd}.txt").write_text("40\n30\n55\n")

    return tmp_path


def test_ingestion_ecrit_des_partitions(faux_cmapss, tmp_path):
    out = tmp_path / "lake"
    df = run(faux_cmapss, out, subsets=SUBSETS_TEST)

    assert len(df) == 2 * (75 + 30)
    assert list(out.glob("flight_year=*")), "aucune partition écrite"


def test_immatriculations_uniques(faux_cmapss, tmp_path):
    """Un moteur = un avion. Pas de doublon entre sous-jeux ni entre splits."""
    df = run(faux_cmapss, tmp_path / "lake", subsets=SUBSETS_TEST)
    correspondance = df.groupby("engine_id").tail_number.nunique()

    assert (correspondance == 1).all(), "un moteur porte plusieurs immatriculations"
    assert df.tail_number.nunique() == df.engine_id.nunique(), (
        "deux moteurs différents partagent une immatriculation"
    )


def test_colonnes_de_tracabilite_presentes(faux_cmapss, tmp_path):
    df = run(faux_cmapss, tmp_path / "lake", subsets=SUBSETS_TEST)
    for col in ("fd_subset", "split", "source_file", "ingested_at", "pipeline_version"):
        assert col in df.columns
        assert df[col].notna().all()


def test_bronze_ne_plafonne_pas_le_rul(faux_cmapss, tmp_path):
    """Le plafond à 125 est un choix de modélisation : il appartient au silver."""
    df = run(faux_cmapss, tmp_path / "lake", subsets=SUBSETS_TEST)
    assert df.rul.max() > 55


def test_erreur_si_fichier_manquant(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(tmp_path, tmp_path / "lake", subsets=["FD001"])
