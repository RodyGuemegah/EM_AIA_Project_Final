"""Point d'entrée : python -m src.ingestion"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.ingestion.bronze import SUBSETS, run


def main() -> int:
    p = argparse.ArgumentParser(description="Ingestion bronze C-MAPSS → Parquet")
    p.add_argument("--data-dir", default="data/raw/CMAPSSData")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--subsets", nargs="+", default=SUBSETS, choices=SUBSETS)
    args = p.parse_args()

    if not Path(args.data_dir).exists():
        print(f"[ERREUR] Dossier introuvable : {args.data_dir}")
        return 1

    print(f"Ingestion de {', '.join(args.subsets)}...")
    df = run(args.data_dir, args.out_dir, subsets=args.subsets)

    print(f"\n✓ {len(df):,} lignes écrites dans {args.out_dir}")
    print(f"  Moteurs      : {df.engine_id.nunique():,}")
    print(f"  Période      : {df.flight_date.min().date()} → {df.flight_date.max().date()}")
    print(f"  Partitions   : {df.groupby(['flight_year', 'flight_month']).ngroups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
