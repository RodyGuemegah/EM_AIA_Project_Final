"""Contrôle de bon fonctionnement — la preuve que le jour 1 est bouclé.

Usage :
    python -m src.sanity data/raw/CMAPSSData
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.cmapss import constant_sensors, load_train, summarize


def main(data_dir: str) -> int:
    d = Path(data_dir)
    train_file = d / "train_FD001.txt"

    if not train_file.exists():
        print(f"[ERREUR] Fichier introuvable : {train_file}")
        print("→ Télécharge C-MAPSS et dézippe-le dans data/raw/ (voir README).")
        return 1

    df = load_train(train_file)
    stats = summarize(df)

    print("=" * 60)
    print("C-MAPSS FD001 — chargement réussi")
    print("=" * 60)
    print(f"Lignes                 : {len(df):,}")
    print(f"Moteurs                : {df.unit_number.nunique()}")
    print(f"Cycles par moteur      : {stats.cycles_observes.min()} à "
          f"{stats.cycles_observes.max()} (médiane {stats.cycles_observes.median():.0f})")
    print(f"RUL (plafonné à 125)   : {df.rul.min()} à {df.rul.max()}")

    plats = constant_sensors(df)
    print(f"Capteurs constants     : {len(plats)} → {plats}")
    print()
    print("Aperçu :")
    print(df.head(3).to_string())
    print()
    print("✓ Jour 1 validé. Prochaine étape : le planificateur de vols.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/raw/CMAPSSData"))
