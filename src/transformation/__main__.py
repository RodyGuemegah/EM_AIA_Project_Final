"""Point d'entrée : python -m src.transformation"""

from __future__ import annotations

import argparse
import sys

from src.cmapss import SENSORS
from src.storage import lake_path
from src.transformation.silver import read_bronze, transform, write_silver


def main() -> int:
    p = argparse.ArgumentParser(description="Transformation silver C-MAPSS → Parquet")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="transforme et affiche le bilan sans rien écrire dans le lake",
    )
    args = p.parse_args()

    source = lake_path("bronze", "engine_sensors")
    print(f"Lecture du bronze depuis {source}...")
    try:
        bronze = read_bronze()
    except KeyError as e:
        # Variables MinIO absentes : message utile plutôt qu'une trace brute.
        print(f"[ERREUR] Variable d'environnement manquante : {e}")
        return 1
    except OSError as e:
        print(f"[ERREUR] Bronze illisible ({source}) : {e}")
        print("         Le bronze a-t-il été ingéré ? → python -m src.ingestion")
        return 1

    print(f"  {len(bronze):,} lignes lues")

    df = transform(bronze)

    # Les capteurs plats ont été retirés par `delete_flat_sensors_`.
    retires = [s for s in SENSORS if s not in df.columns]

    if args.dry_run:
        destination = "(dry-run : rien n'a été écrit)"
    else:
        destination = write_silver(df)

    print(f"\n✓ {len(df):,} lignes → {destination}")
    print(f"  Moteurs        : {df.engine_id.nunique():,}")
    print(f"  Capteurs plats : {len(retires)} retirés"
          + (f" ({', '.join(retires)})" if retires else ""))
    print(f"  Régimes de vol : {df.regime.nunique()}")
    print(f"  Colonnes       : {bronze.shape[1]} → {df.shape[1]}")
    print(f"  RUL plafonné à : {df.rul.max()}")
    print(f"  Période        : {df.flight_date.min().date()} → {df.flight_date.max().date()}")
    print(f"  Partitions     : {df.groupby(['flight_year', 'flight_month']).ngroups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
