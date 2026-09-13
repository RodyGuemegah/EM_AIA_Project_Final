"""Volumétrie du data lake : ce que rapportent Parquet et le partitionnement.

CE QUE CE SCRIPT MESURE
-----------------------
À deux échelles (×1 et ×10), sur disque local :
  1. la taille sur disque
  2. le temps de scan complet
  3. le temps de lecture d'un seul mois        → gain du partitionnement
  4. le temps de lecture de 4 colonnes sur 41  → gain du format colonnaire
Plus, une fois : Parquet contre CSV à colonnes identiques.

CE QUE CE SCRIPT NE FAIT PAS
----------------------------
Il n'interprète pas. Il affiche un tableau ; les conclusions sont rédigées
à la main dans docs/benchmarks/volumetrie.md, après lecture des chiffres.

DEUX LIMITES ASSUMÉES
---------------------
1. Les lectures sont « chaudes » : le système d'exploitation garde les fichiers
   en cache. Ces chiffres comparent donc des formats entre eux, ils ne prédisent
   pas une latence de production. Un run d'échauffement est jeté, puis on garde
   la MÉDIANE de 5 répétitions — une moyenne se laisserait décaler par une seule
   pause du ramasse-miettes.

2. L'échelle ×10 est construite par réplication : chaque copie reçoit de
   NOUVEAUX identifiants de moteurs. Sans cela, Parquet stockerait chaque valeur
   distincte une seule fois et le taux de compression serait six fois trop
   optimiste (mesuré : 23 contre 135 octets par ligne). Chaque copie produit ses
   propres fichiers, la structure diffère donc légèrement de ×1.
"""

from __future__ import annotations

import shutil
import statistics
import time
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq
from pyarrow.fs import LocalFileSystem

from src.storage import get_lake_filesystem, lake_path

SOURCE = lake_path("bronze", "engine_sensors")
RACINE = Path("/tmp/benchmark_volumetrie")
COLONNES = ["engine_id", "time_in_cycles", "sensor_04", "rul"]
FACTEURS = [1, 10]
REPETITIONS = 5


def chrono(fn, repetitions=REPETITIONS) -> float:
    """Médiane de N exécutions, après un run d'échauffement jeté."""
    fn()
    temps = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        fn()
        temps.append((time.perf_counter() - t0) * 1000)
    return statistics.median(temps)


def construire(df, facteur: int, destination: Path) -> None:
    """Réplique le bronze `facteur` fois, copie par copie pour tenir en mémoire."""
    for i in range(facteur):
        copie = df.copy()
        if facteur > 1:
            copie["engine_id"] = copie.engine_id + f"_r{i}"
            copie["tail_number"] = copie.tail_number + f"_r{i}"
        copie.to_parquet(
            destination,
            partition_cols=["flight_year", "flight_month"],
            compression="snappy",
            existing_data_behavior="overwrite_or_ignore",
        )


def taille(chemin: Path) -> int:
    return sum(f.stat().st_size for f in chemin.rglob("*.parquet"))


def mesurer(chemin: Path) -> dict:
    """Les quatre mesures sur un dataset donné."""
    jeu = ds.dataset(chemin, partitioning="hive")
    partitions = sorted({(p[0], p[1]) for p in
                         jeu.to_table(columns=["flight_year", "flight_month"])
                            .to_pandas().itertuples(index=False)})
    annee, mois = partitions[len(partitions) // 2]   # un mois du milieu

    scan = lambda: pq.read_table(chemin)
    un_mois = lambda: pq.read_table(
        chemin, filters=[("flight_year", "==", annee), ("flight_month", "==", mois)])
    colonnes = lambda: pq.read_table(chemin, columns=COLONNES)

    # Vérifier que le filtre a réellement élagué, au lieu de le supposer :
    # un `filters=` mal formé lirait tout puis filtrerait en mémoire, et le
    # benchmark afficherait un temps honorable avec une conclusion fausse.
    lues, total = un_mois().num_rows, scan().num_rows
    assert lues < total, "le filtre n'a rien élagué"

    return {
        "lignes": total,
        "octets": taille(chemin),
        "partitions": len(partitions),
        "mois": f"{annee}-{mois:02d}",
        "t_scan": chrono(scan),
        "t_mois": chrono(un_mois),
        "t_colonnes": chrono(colonnes),
        "lignes_mois": lues,
    }


def main() -> int:
    df = pq.read_table(SOURCE, filesystem=get_lake_filesystem()).to_pandas()
    print(f"Source : {len(df):,} lignes, {df.shape[1]} colonnes\n")

    if RACINE.exists():
        shutil.rmtree(RACINE)

    resultats = []
    for facteur in FACTEURS:
        chemin = RACINE / f"x{facteur}"
        print(f"Construction ×{facteur}...", flush=True)
        construire(df, facteur, chemin)
        resultats.append({"facteur": facteur, **mesurer(chemin)})

    print(f"\n{'échelle':>8}{'lignes':>12}{'taille':>10}{'o/ligne':>9}"
          f"{'scan':>9}{'1 mois':>9}{'4 col.':>9}")
    print("-" * 66)
    for r in resultats:
        print(f"{'×' + str(r['facteur']):>8}{r['lignes']:>12,}"
              f"{r['octets'] / 1e6:>9.1f}M{r['octets'] / r['lignes']:>9.0f}"
              f"{r['t_scan']:>7.0f}ms{r['t_mois']:>7.0f}ms{r['t_colonnes']:>7.0f}ms")

    print(f"\nRatios (scan ÷ requête ciblée) :")
    for r in resultats:
        print(f"  ×{r['facteur']:<3} un mois : {r['t_scan'] / r['t_mois']:.1f}x"
              f"   |   4 colonnes : {r['t_scan'] / r['t_colonnes']:.1f}x")

    # Parquet contre CSV, à colonnes identiques.
    csv, parquet = RACINE / "cmp.csv", RACINE / "cmp.parquet"
    df.to_csv(csv, index=False)
    df.to_parquet(parquet, compression="snappy")
    c, p = csv.stat().st_size / 1e6, parquet.stat().st_size / 1e6
    print(f"\nMême contenu, {df.shape[1]} colonnes :")
    print(f"  CSV     {c:6.1f} Mo")
    print(f"  Parquet {p:6.1f} Mo   → ÷{c / p:.1f}")

    shutil.rmtree(RACINE)
    print(f"\n(données temporaires supprimées de {RACINE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())