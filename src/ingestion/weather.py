"""Ingestion de la météo vers la couche bronze.

CE QUE CETTE SOURCE APPORTE, ET CE QU'ELLE N'APPORTE PAS
---------------------------------------------------------
Elle comble la case « données externes : conditions météorologiques » du
document de présentation, et démontre l'ingestion par API — un mode d'acquisition
différent des fichiers posés sur disque.

Elle ne sera PAS utilisée comme variable du modèle. Le rattachement
moteur ↔ aéroport est généré par `src.fleet` : aucune corrélation physique ne
peut exister entre la température de Roissy et la dégradation d'un moteur
C-MAPSS affecté à Roissy par tirage aléatoire. Sur données SAFRAN réelles, ces
variables seraient exploitables (démarrages à froid, ingestion de sable,
corrosion saline).

LA MÉTÉO N'EST PAS CELLE DE L'AÉROPORT
--------------------------------------
Open-Meteo renvoie le point de grille de son modèle le plus proche, à quelques
kilomètres. On conserve les deux jeux de coordonnées pour que l'écart reste
mesurable sans refaire l'appel.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.storage import get_lake_filesystem, lake_path

PIPELINE_VERSION = "0.1.0"
SOURCE_DIR = Path("data/raw/weather")
DATASET = "weather"


def read_json(chemin: Path) -> pd.DataFrame:
    """Aplatit un fichier Open-Meteo en lignes (un aéroport, un jour).

    `daily` est un dictionnaire de listes parallèles : time[], temperature[],
    etc., toutes de même longueur. pandas les reconnaît et en fait des colonnes.
    """
    data = json.loads(chemin.read_text())

    df = pd.DataFrame(data["daily"])
    df = df.rename(columns={"time": "observation_date"})
    df["observation_date"] = pd.to_datetime(df.observation_date)

    df["icao"] = data["_icao"]
    df["latitude_demandee"] = data["_latitude_demandee"]
    df["longitude_demandee"] = data["_longitude_demandee"]
    df["latitude_maille"] = data["latitude"]
    df["longitude_maille"] = data["longitude"]
    df["elevation_m"] = data["elevation"]

    # Unités renvoyées par l'API, conservées : « 12,5 » ne veut rien dire
    # sans « °C », et le jury peut le demander.
    for variable, unite in data["daily_units"].items():
        if variable != "time":
            df[f"unite_{variable}"] = unite

    df["source_file"] = chemin.name
    df["ingested_at"] = datetime.now(timezone.utc)
    df["pipeline_version"] = PIPELINE_VERSION

    df["observation_year"] = df.observation_date.dt.year
    df["observation_month"] = df.observation_date.dt.month
    return df


def write_parquet(df: pd.DataFrame, out_dir: str, filesystem=None) -> str:
    pq.write_to_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        root_path=out_dir,
        filesystem=filesystem,
        partition_cols=["observation_year", "observation_month"],
        existing_data_behavior="delete_matching",
        compression="snappy",
    )
    return out_dir


def run(source_dir=SOURCE_DIR, out_dir=None, filesystem=None) -> pd.DataFrame:
    fichiers = sorted(Path(source_dir).glob("*.json"))
    if not fichiers:
        raise FileNotFoundError(
            f"Aucun JSON dans {source_dir}. Lancer d'abord : "
            "python -m src.ingestion.weather_fetch"
        )

    df = pd.concat([read_json(f) for f in fichiers], ignore_index=True)

    if filesystem is None:
        filesystem = get_lake_filesystem()
    if out_dir is None:
        out_dir = lake_path("bronze", DATASET)

    write_parquet(df, out_dir, filesystem)
    return df


def main() -> int:
    try:
        df = run()
    except FileNotFoundError as e:
        print(f"[ERREUR] {e}")
        return 1

    manquantes = df.temperature_2m_max.isna().sum()
    print(f"✓ {len(df):,} lignes → bronze/{DATASET}")
    print(f"  Aéroports    : {df.icao.nunique()}")
    print(f"  Période      : {df.observation_date.min().date()} → "
          f"{df.observation_date.max().date()}")
    print(f"  Partitions   : {df.groupby(['observation_year', 'observation_month']).ngroups}")
    print(f"  Températures manquantes : {manquantes}")
    print(f"  Écart maille/aéroport   : "
          f"max {(df.latitude_maille - df.latitude_demandee).abs().max():.3f}°")
    return 0


if __name__ == "__main__":
    sys.exit(main())