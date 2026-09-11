"""Tests de l'ingestion SDR (FAA) vers la couche bronze.

Deux familles de tests. Les premiers vérifient la MÉCANIQUE — le fichier est lu,
les partitions sont écrites, un schéma inattendu fait échouer. Les seconds
vérifient la DOCTRINE : le bronze ne filtre pas, ne retype pas, ne perd pas
l'original. Ce sont ceux-là qui protègent les décisions d'architecture — un
refactor qui « nettoierait un peu » les casserait, et c'est le but.

Aucune donnée réelle n'est lue : les fixtures fabriquent un SDR minuscule à
partir de `COLUMNS_FAA`. La CI reste autonome et rapide.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pyarrow.fs import LocalFileSystem

from src.ingestion.sdr import COLUMNS_FAA, run

# Deux lignes, choisies pour ce qu'elles piègent :
#  - un chapitre ATA 53 (cellule) et un 72 (moteur turbine), pour vérifier que
#    le bronze n'écrème pas les 96 % de SDR non-moteur ;
#  - une date de constat « 01/03/2022 », ambiguë entre les conventions US et FR ;
#  - un numéro de série à zéro initial, que l'inférence de type détruirait ;
#  - un `Discrepancy` contenant un VRAI retour à la ligne, qui décalerait
#    n'importe quelle lecture ligne à ligne.
LIGNES = [
    {
        "OperatorControlNumber": "TEST2022010300001",
        "DifficultyDate": "01/03/2022",
        "SubmissionDate": "2022-01-05T04:59:23.250-05:00",
        "JASCCode": "5310",
        "AircraftSerialNumber": "0123",
        "PartName": "PANNEAU",
        "Discrepancy": "FISSURE CONSTATEE\nSUR DEUX LIGNES",
    },
    {
        "OperatorControlNumber": "TEST2022021500002",
        "DifficultyDate": "02/15/2022",
        "SubmissionDate": "2022-02-16T08:00:00.000-05:00",
        "JASCCode": "7250",
        "AircraftSerialNumber": "4567",
        "PartName": "AUBE TURBINE",
        "Discrepancy": "VIBRATION MOTEUR 2",
    },
]


@pytest.fixture
def faux_sdr(tmp_path):
    """Écrit un SDR-2022.csv minimal au format FAA exact (76 colonnes)."""
    df = pd.DataFrame(LIGNES).reindex(columns=COLUMNS_FAA)
    df.to_csv(tmp_path / "SDR-2022.csv", index=False)
    return tmp_path


def _run_local(data_dir, out_dir, years=(2022,)):
    """Ingestion sur disque local, sans MinIO — garde la CI autonome."""
    return run(data_dir, str(out_dir), years=list(years), filesystem=LocalFileSystem())


# --- Mécanique ------------------------------------------------------------


def test_ingestion_ecrit_des_partitions(faux_sdr, tmp_path):
    out = tmp_path / "lake"
    df = _run_local(faux_sdr, out)

    assert len(df) == len(LIGNES)
    assert list(out.glob("difficulty_year=2022")), "aucune partition écrite"
    assert len(list(out.glob("difficulty_year=*/difficulty_month=*"))) == 2


def test_colonnes_de_tracabilite_presentes(faux_sdr, tmp_path):
    df = _run_local(faux_sdr, tmp_path / "lake")
    for col in ("source_file", "ingested_at", "pipeline_version"):
        assert col in df.columns
        assert df[col].notna().all()
    assert df.source_file.unique().tolist() == ["SDR-2022.csv"]


def test_erreur_si_schema_inattendu(tmp_path):
    """Colonne manquante, renommée ou réordonnée : les trois doivent échouer."""
    pd.DataFrame(LIGNES).reindex(columns=COLUMNS_FAA[:-1]).to_csv(
        tmp_path / "SDR-2022.csv", index=False
    )
    with pytest.raises(ValueError, match="schéma FAA inattendu"):
        _run_local(tmp_path, tmp_path / "lake")


def test_erreur_si_ordre_des_colonnes_change(tmp_path):
    """Le cas sournois : 76 colonnes, les bons noms, le mauvais ordre."""
    permute = [COLUMNS_FAA[1], COLUMNS_FAA[0], *COLUMNS_FAA[2:]]
    pd.DataFrame(LIGNES).reindex(columns=permute).to_csv(
        tmp_path / "SDR-2022.csv", index=False
    )
    with pytest.raises(ValueError, match="ordre différent"):
        _run_local(tmp_path, tmp_path / "lake")


def test_erreur_si_millesime_manquant(tmp_path):
    with pytest.raises(FileNotFoundError):
        _run_local(tmp_path, tmp_path / "lake", years=(2099,))


# --- Doctrine -------------------------------------------------------------


def test_date_lue_en_format_americain(faux_sdr, tmp_path):
    """« 01/03/2022 » est le 3 JANVIER. Lu en JJ/MM, ce serait le 1er mars.

    Une erreur de deux mois sur 100 % des lignes, qu'aucun contrôle de volume ne
    révélerait — le fichier aurait le bon nombre de lignes, juste les mauvaises dates.
    """
    df = _run_local(faux_sdr, tmp_path / "lake")
    ligne = df[df.difficulty_date_raw == "01/03/2022"].iloc[0]

    assert ligne.difficulty_date == pd.Timestamp("2022-01-03")
    assert ligne.difficulty_month == 1, "mois de mars : la date a été lue en JJ/MM"


def test_chaines_brutes_conservees(faux_sdr, tmp_path):
    """Le typage d'une date est une INTERPRÉTATION : l'original doit rester."""
    df = _run_local(faux_sdr, tmp_path / "lake")

    assert df.difficulty_date_raw.tolist() == [lig["DifficultyDate"] for lig in LIGNES]
    assert df.submission_date_raw.tolist() == [lig["SubmissionDate"] for lig in LIGNES]


def test_le_bronze_ne_filtre_pas_les_chapitres_non_moteur(faux_sdr, tmp_path):
    """96 % des SDR concernent la cellule. Le bronze les garde TOUS.

    Filtrer sur ATA 72 dès l'ingestion rendrait impossible de rejouer le
    traitement et de retrouver le fichier FAA d'origine. C'est un choix
    d'analyse : il appartient au silver.
    """
    df = _run_local(faux_sdr, tmp_path / "lake")
    chapitres = set(df.jasc_code.str.zfill(4).str[:2])

    assert "53" in chapitres, "le SDR cellule a été filtré à l'ingestion"
    assert "72" in chapitres


def test_retour_a_la_ligne_dans_discrepancy_ne_decale_pas(faux_sdr, tmp_path):
    """`Discrepancy` est du texte libre et contient de vrais sauts de ligne.

    Le fichier FAA 2022 compte 64 993 lignes physiques pour 62 612
    enregistrements. Une lecture ligne à ligne décalerait tout le fichier.
    """
    df = _run_local(faux_sdr, tmp_path / "lake")

    assert len(df) == len(LIGNES), "le saut de ligne a produit un enregistrement fantôme"
    assert "\n" in df.discrepancy.iloc[0]


def test_zeros_initiaux_preserves(faux_sdr, tmp_path):
    """« 0123 » est un numéro de série, pas le nombre 123."""
    df = _run_local(faux_sdr, tmp_path / "lake")

    assert df.aircraft_serial_number.iloc[0] == "0123"


def test_colonnes_non_typees(faux_sdr, tmp_path):
    """Le bronze ne type que les dates. Le reste reste en texte, brut."""
    df = _run_local(faux_sdr, tmp_path / "lake")

    assert str(df.jasc_code.dtype) in {"str", "object"}
    assert str(df.aircraft_serial_number.dtype) in {"str", "object"}
