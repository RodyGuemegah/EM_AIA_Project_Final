"""Tests de l'ingestion météo — sans réseau, sans MinIO.

FIXTURE_LFPG est une VRAIE réponse de l'archive Open-Meteo, enregistrée en dur.
Les tests portent donc sur de la donnée authentique tout en restant hors ligne :
même principe que `faux_cmapss` dans test_bronze.py.
"""

from __future__ import annotations

import copy
import json

import pytest
from pyarrow.fs import LocalFileSystem

from src.ingestion.weather import read_json, run

FIXTURE_LFPG = {
    "latitude": 49.03339,
    "longitude": 2.6064737,
    "elevation": 107.0,
    "daily_units": {
        "time": "iso8601",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_sum": "mm",
        "wind_speed_10m_max": "km/h",
    },
    "daily": {
        "time": ["2022-01-01", "2022-01-02", "2022-01-03"],
        "temperature_2m_max": [12.5, 13.3, 11.6],
        "temperature_2m_min": [7.2, 8.0, 9.6],
        "precipitation_sum": [0.0, 3.2, 7.9],
        "wind_speed_10m_max": [14.2, 28.7, 31.1],
    },
    "_icao": "LFPG",
    "_latitude_demandee": 49.0097,
    "_longitude_demandee": 2.5479,
}


def _write_fixture(dossier, icao="LFPG", modifs=None):
    """Dépose un JSON au format Open-Meteo dans `dossier`."""
    data = copy.deepcopy(FIXTURE_LFPG)
    data["_icao"] = icao
    if modifs:
        data.update(modifs)
    chemin = dossier / f"{icao}.json"
    chemin.write_text(json.dumps(data))
    return chemin


@pytest.fixture
def dossier_json(tmp_path):
    """Deux aéroports, trois jours chacun."""
    d = tmp_path / "raw"
    d.mkdir()
    _write_fixture(d, "LFPG")
    _write_fixture(d, "EGLL", {"latitude": 51.5, "longitude": -0.46, "elevation": 25.0})
    return d


def _run_local(source_dir, tmp_path):
    """Ingestion sur disque local — garde la CI indépendante de MinIO."""
    return run(source_dir=source_dir, out_dir=str(tmp_path / "lake"),
               filesystem=LocalFileSystem())


def test_aplatit_une_ligne_par_jour(tmp_path):
    """Les tableaux parallèles de l'API deviennent des lignes."""
    df = read_json(_write_fixture(tmp_path))
    assert len(df) == 3
    assert df.temperature_2m_max.tolist() == [12.5, 13.3, 11.6]


def test_coordonnees_demandees_et_maille_conservees(tmp_path):
    """L'API répond pour sa maille, pas pour l'aéroport : on garde les deux.

    Sans cela, impossible de mesurer l'écart sans refaire l'appel.
    """
    df = read_json(_write_fixture(tmp_path))
    assert df.latitude_demandee.iloc[0] == 49.0097
    assert df.latitude_maille.iloc[0] == 49.03339
    assert abs(df.latitude_maille.iloc[0] - df.latitude_demandee.iloc[0]) > 0.01


def test_colonnes_de_tracabilite_presentes(tmp_path):
    df = read_json(_write_fixture(tmp_path))
    for col in ("icao", "source_file", "ingested_at", "pipeline_version", "elevation_m"):
        assert col in df.columns
        assert df[col].notna().all()


def test_cle_aeroport_date_unique(dossier_json, tmp_path):
    """Une ligne = un aéroport, un jour. Le couple doit être unique."""
    df = _run_local(dossier_json, tmp_path)
    assert not df.duplicated(subset=["icao", "observation_date"]).any()
    assert len(df) == 6          # 2 aéroports x 3 jours


def test_partitions_ecrites(dossier_json, tmp_path):
    _run_local(dossier_json, tmp_path)
    assert list((tmp_path / "lake").glob("observation_year=*")), "aucune partition"


def test_valeur_nulle_api_preservee(tmp_path):
    """Un capteur manquant côté API doit rester manquant, pas devenir 0."""
    modifs = {"daily": {**FIXTURE_LFPG["daily"],
                        "temperature_2m_max": [12.5, None, 11.6]}}
    df = read_json(_write_fixture(tmp_path, modifs=modifs))
    assert df.temperature_2m_max.isna().sum() == 1


def test_erreur_si_aucun_json(tmp_path):
    """Message explicite plutôt qu'un DataFrame vide silencieux."""
    vide = tmp_path / "vide"
    vide.mkdir()
    with pytest.raises(FileNotFoundError, match="weather_fetch"):
        _run_local(vide, tmp_path)