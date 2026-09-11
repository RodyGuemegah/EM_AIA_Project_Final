"""Ingestion des SDR (FAA Service Difficulty Reports) vers la couche BRONZE.

QU'EST-CE QU'UN SDR ?
---------------------
Un Service Difficulty Report est une déclaration réglementaire : un opérateur
américain signale à la FAA une anomalie constatée sur un aéronef (14 CFR 121.703).
C'est le pendant public et documenté de ce qu'un exploitant remonte à SAFRAN
après un vol. Chaque SDR décrit UN événement : ce qui a été constaté, sur quelle
pièce, à quel stade de l'exploitation, et comment il a été découvert.

POURQUOI CETTE SOURCE, ET POURQUOI SÉPARÉE
------------------------------------------
C-MAPSS donne une TRAJECTOIRE de dégradation, jamais un ÉVÉNEMENT. Les SDR
donnent l'inverse : des événements datés, sans capteurs. Les deux sources
décrivent le même métier par deux bouts opposés.

Elles ne se joignent PAS. La flotte C-MAPSS est simulée (immatriculations
fabriquées par `src.fleet`), les SDR portent de vrais N-numbers américains.
Aucune clé commune n'existe, et en inventer une au bronze reviendrait à poser
de la fabrication sur de la fabrication. Le bronze ingère donc les SDR comme une
source INDÉPENDANTE, dans son propre dataset. Si un rattachement doit exister,
il sera construit — et justifié — en silver.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne filtre pas sur les chapitres moteur (ATA 71-80), alors que 96 % des SDR
ne concernent pas le motopropulseur . Même règle que pour `bronze.py` : le bronze ne nettoie
pas. Un auditeur EASA doit pouvoir rejouer l'ingestion deux ans plus tard et
retrouver le fichier FAA d'origine, ligne pour ligne. Le filtrage moteur est un
choix d'analyse : il appartient au silver.

Il ne type pas non plus les colonnes — tout est lu en texte. Voir `_read_raw`.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.storage import get_lake_filesystem, lake_path

PIPELINE_VERSION = "0.1.0"
YEARS = [2022, 2023, 2024]

# Emplacement par défaut des fichiers FAA, et nom du dataset dans le lake.
DATA_DIR = "data/raw/sdr"
DATASET = "sdr_events"

# Année/mois de repli pour une date de constat illisible. Voir `_parse_dates` :
# laisser un NULL dans une colonne de partition produit un dataset que pyarrow
# ÉCRIT mais ne sait pas RELIRE. La sentinelle n'invente aucune donnée — la
# valeur d'origine reste intacte dans `difficulty_date_raw`.
PARTITION_DATE_INCONNUE = -1

# Clé primaire naturelle : vérifiée unique sur les 191 379 enregistrements
# des trois millésimes réunis.
CLE_PRIMAIRE = "operator_control_number"

# La FAA date l'événement en MM/DD/YYYY (format américain). Lu avec le défaut
# pandas, « 01/03/2022 » deviendrait le 1er mars au lieu du 3 janvier — une
# erreur silencieuse de deux mois sur 100 % des lignes.
FORMAT_DATE_FAA = "%m/%d/%Y"

# Le schéma FAA, figé. Comme `COLUMNS` pour C-MAPSS, cette constante sert deux
# usages : contrôler qu'un fichier reçu est bien celui qu'on croit, et permettre
# aux tests de fabriquer un faux SDR sans jamais lire `data/raw/`.
#
# On vérifie les NOMS et pas seulement leur nombre : un fichier gouvernemental
# qui réordonnerait deux colonnes ou en renommerait une garderait un compte de 76
# et passerait un contrôle par comptage sans le moindre avertissement.
COLUMNS_FAA = [
    "OperatorControlNumber", "DifficultyDate", "SubmissionDate",
    "OperatorDesignator", "SubmitterDesignator", "SubmitterTypeCode",
    "ReceivingRegionCode", "ReceivingDistrictOffice", "SDRType", "JASCCode",
    "NatureOfConditionA", "NatureOfConditionB", "NatureOfConditionC",
    "PrecautionaryProcedureA", "PrecautionaryProcedureB", "PrecautionaryProcedureC",
    "PrecautionaryProcedureD", "StageOfOperationCode", "HowDiscoveredCode",
    "RegistryNNumber", "AircraftMake", "AircraftModel", "AircraftSerialNumber",
    "AircraftTotalTime", "AircraftTotalCycles", "EngineMake", "EngineModel",
    "EngineSerialNumber", "EngineTotalTime", "EngineTotalCycles", "PropellerMake",
    "PropellerModel", "PropellerSerialNumber", "PropellerTotalTime",
    "PropellerTotalCycles", "PartMake", "PartName", "PartNumber",
    "PartSerialNumber", "PartCondition", "PartLocation", "PartTotalTime",
    "PartTotalCycles", "PartTimeSince", "PartSinceCode", "ComponentMake",
    "ComponentModel", "ComponentName", "ComponentPartNumber",
    "ComponentSerialNumber", "ComponentLocation", "ComponentTotalTime",
    "ComponentTotalCycles", "ComponentTimeSince", "ComponentSinceCode",
    "FuselageStationFrom", "FuselageStationTo", "StringerFrom", "StringerFromSide",
    "StringerTo", "StringerToSide", "WingStationFrom", "WingStationFromSide",
    "WingStationTo", "WingStationToSide", "ButtLineFrom", "ButtLineFromSide",
    "ButtlineTo", "ButtlineToSide", "WaterLineFrom", "WaterLineTo", "CrackLength",
    "NumberOfCracks", "CorrosionLevel", "StructuralOther", "Discrepancy"
]
NB_COLONNES = len(COLUMNS_FAA)


def _to_snake_case(nom: str) -> str:
    """`OperatorControlNumber` → `operator_control_number`.

    Le reste du lake est en snake_case (`engine_id`, `flight_year`). Garder le
    PascalCase de la FAA imposerait des guillemets à chaque requête SQL et
    jurerait avec le dbt prévu en aval. Le renommage ne perd aucune information
    et reste réversible : c'est une convention, pas un nettoyage.

    Deux passes, parce que les en-têtes FAA contiennent des ACRONYMES. Couper
    devant chaque majuscule donnerait `JASCCode` → `j_a_s_c_code`. La 1re passe
    isole un mot capitalisé qui suit un acronyme (`JASC|Code`), la 2nde coupe
    entre une minuscule et une majuscule (`Registry|NNumber`).
    """
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", nom)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _verifier_schema(df: pd.DataFrame, path: Path) -> None:
    """Échoue si le fichier reçu n'a pas exactement le schéma FAA attendu.

    Même principe que le contrôle de colonnes du loader C-MAPSS : mieux vaut
    refuser un fichier que produire un DataFrame silencieusement faux. Mais ici
    le CSV porte un en-tête, donc on peut être plus strict qu'un simple comptage
    et vérifier les noms ET leur ordre.

    Le message nomme ce qui manque et ce qui est en trop : face à un fichier FAA
    de 76 colonnes, « schéma inattendu » n'aiderait personne à 3 h du matin.
    """
    recus = list(df.columns)
    if recus == COLUMNS_FAA:
        return

    manquantes = [c for c in COLUMNS_FAA if c not in recus]
    en_trop = [c for c in recus if c not in COLUMNS_FAA]

    detail = []
    if manquantes:
        detail.append(f"manquantes : {manquantes}")
    if en_trop:
        detail.append(f"en trop : {en_trop}")
    if not detail:
        # Mêmes noms, ordre différent — le plus sournois des trois cas.
        detail.append("mêmes colonnes mais dans un ordre différent")

    raise ValueError(
        f"{path.name}: schéma FAA inattendu "
        f"({len(recus)} colonnes lues, {NB_COLONNES} attendues). "
        + " | ".join(detail)
    )


def _read_raw(path: Path) -> pd.DataFrame:
    """Lit un CSV SDR brut, sans typer ni nettoyer.

    TROIS PIÈGES, TROIS PARADES
    ---------------------------
    1. `Discrepancy` est du texte libre de maintenance, et il CONTIENT des
       retours à la ligne. Le fichier 2022 compte 64 993 lignes physiques pour
       62 612 enregistrements. Tout découpage ligne à ligne décalerait le
       fichier en silence ; le parseur CSV de pandas gère les champs guillemetés
       et reste donc la seule lecture correcte.

    2. `dtype=str` sur TOUT. Sans cela, pandas infère : `AircraftSerialNumber`
       « 0123 » deviendrait 123.0 — un numéro de série corrompu, et irrécupérable
       une fois écrit en Parquet. Le typage est un choix d'analyse, il appartient
       au silver.

    3. `keep_default_na=False` : par défaut, pandas convertit les chaînes « NA »,
       « NULL », « N/A » en valeur manquante. Dans un champ de texte libre rempli
       par un mécanicien, « N/A » est une RÉPONSE, pas une absence de réponse.
       Seule la cellule réellement vide devient NA.
    """
    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8",
    )

    _verifier_schema(df, path)

    df.columns = [_to_snake_case(c) for c in df.columns]
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Type les deux dates et dérive les clés de partitionnement.

    LES CHAÎNES BRUTES SONT CONSERVÉES, en `*_raw`. Convertir une date est une
    interprétation : « 01/03/2022 » ne devient le 3 janvier que SI l'on admet
    que la FAA écrit en MM/DD/YYYY. Garder l'original permet à un auditeur de
    vérifier cette hypothèse sans re-télécharger le fichier FAA. Le nom canonique
    porte la valeur typée, le suffixe `_raw` la trace.

    DEUX DATES, DEUX NATURES
    -----------------------
    `difficulty_date` est le jour du CONSTAT, sans heure ni fuseau : c'est une
    date civile, on la laisse naïve. L'y coller un fuseau inventerait une
    précision qui n'existe pas dans la donnée.

    `submission_date` est l'instant de la DÉCLARATION, horodaté. Les trois
    millésimes 2022-2024 n'utilisent qu'un seul décalage, `-05:00` (EST fixe,
    sans heure d'été) — `utc=True` n'y est donc pas strictement nécessaire
    AUJOURD'HUI. C'est une garde : si un millésime futur mélangeait les
    décalages, `to_datetime` lèverait `ValueError: Mixed timezones detected` et
    l'ingestion entière échouerait. Une ligne de garde vaut mieux qu'une panne
    dans deux ans. Le décalage d'origine reste lisible dans `submission_date_raw`.

    Passer en UTC décale l'horodatage de 5 heures : une déclaration du 3 janvier
    à 21 h EST tombe le 4 janvier en UTC. Sans conséquence ici, car on partitionne
    sur `difficulty_date` (naïve, jour du constat), jamais sur la déclaration.
    """
    df = df.copy()

    df["difficulty_date_raw"] = df["difficulty_date"]
    df["submission_date_raw"] = df["submission_date"]

    df["difficulty_date"] = pd.to_datetime(
        df["difficulty_date_raw"], format=FORMAT_DATE_FAA, errors="coerce"
    )
    df["submission_date"] = pd.to_datetime(
        df["submission_date_raw"], format="ISO8601", utc=True, errors="coerce"
    )

    # `errors="coerce"` rend NaT au lieu de lever : une date illisible ne doit
    # pas faire échouer l'ingestion des 191 378 autres lignes. Mais elle ne doit
    # pas passer inaperçue non plus — le compte est remonté à l'appelant, qui
    # l'affiche. Le bronze CONSTATE la qualité, il ne la corrige pas.
    #
    # La ligne est conservée, sa `difficulty_date` reste NaT, et elle atterrit
    # dans la partition de quarantaine `difficulty_year=-1` — visible d'un `ls`,
    # et relisible, contrairement à une partition nulle.
    illisibles = int(df["difficulty_date"].isna().sum())
    if illisibles:
        print(f"  [!] {illisibles} difficulty_date illisibles (conservées en NaT)")

    # Clés de partitionnement, alignées sur `engine_sensors` (flight_year/month).
    #
    # `int32` et NON `Int16` nullable, et c'est tout sauf un détail de style :
    # une colonne de partition nullable (ou flottante, ou textuelle) produit un
    # dataset que pyarrow écrit sans broncher mais refuse ensuite de relire —
    # `NotImplementedError: dictionary<values=int32>` pour le type nullable,
    # `ArrowInvalid: Cannot yet unify dictionaries with nulls` dès qu'une valeur
    # manque. La panne ne se déclare qu'à la LECTURE, donc potentiellement des
    # mois après l'ingestion. On la rend impossible à l'écriture.
    for col, source in (("difficulty_year", "year"), ("difficulty_month", "month")):
        df[col] = (
            getattr(df["difficulty_date"].dt, source)
            .fillna(PARTITION_DATE_INCONNUE)
            .astype("int32")
        )

    return df


def _add_lineage(df: pd.DataFrame, source_file: Path) -> pd.DataFrame:
    """Ajoute les colonnes de traçabilité.

    Volontairement dupliqué depuis `bronze.py` plutôt que factorisé : les deux
    ingestions doivent pouvoir évoluer séparément. Une source FAA qui change de
    format ne doit pas obliger à toucher au code qui lit C-MAPSS.

    Pas d'équivalent de `fd_subset` / `split` ici : un SDR n'appartient ni à un
    sous-jeu ni à un découpage train/test. `source_file` suffit à remonter au
    millésime d'origine.
    """
    df = df.copy()
    df["source_file"] = source_file.name
    df["ingested_at"] = datetime.now(timezone.utc)
    df["pipeline_version"] = PIPELINE_VERSION
    return df


def ingest_year(year: int, data_dir: Path) -> pd.DataFrame:
    """Charge un millésime SDR complet : lecture, typage des dates, traçabilité."""
    data_dir = Path(data_dir)
    fichier = data_dir / f"SDR-{year}.csv"

    if not fichier.exists():
        raise FileNotFoundError(f"Fichier manquant : {fichier}")

    return _add_lineage(_parse_dates(_read_raw(fichier)), fichier)


def write_sdr(df: pd.DataFrame, out_dir: str, filesystem=None) -> str:
    """Écrit les SDR en Parquet partitionné par année/mois du CONSTAT.

    POURQUOI PARTITIONNER SUR `difficulty_date` ET NON SUR LA DÉCLARATION ?
    Parce que la question métier porte sur le moment où l'anomalie s'est
    produite, pas sur celui où la paperasse est arrivée. L'écart entre les deux
    atteint 1 498 jours sur le millésime 2022 : partitionner sur la déclaration
    éparpillerait un même mois d'exploitation sur quatre ans de dossiers.

    Une `difficulty_date` illisible atterrit dans la partition de quarantaine
    `difficulty_year=-1/difficulty_month=-1` : la ligne est conservée et isolée,
    jamais perdue ni silencieusement rattachée à une date inventée. Sa valeur
    d'origine reste lisible dans `difficulty_date_raw`.

    Ne PAS la laisser en NULL, ce qui produirait `__HIVE_DEFAULT_PARTITION__` :
    pyarrow écrit cette partition puis échoue à relire le dataset entier
    (`Cannot yet unify dictionaries with nulls`). Une seule date illisible
    rendrait ainsi les 191 378 autres lignes inaccessibles.
    """
    pq.write_to_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        root_path=out_dir,
        filesystem=filesystem,
        partition_cols=["difficulty_year", "difficulty_month"],
        existing_data_behavior="delete_matching",
        compression="snappy",
    )
    return out_dir


def run(data_dir=DATA_DIR, out_dir=None, years=None, filesystem=None) -> pd.DataFrame:
    """Ingère les millésimes demandés et les écrit dans le lake.

    `out_dir` et `filesystem` sont explicites pour la même raison que dans
    `bronze.run` : ils permettent aux tests d'écrire sur un disque local et de
    rester indépendants de MinIO.
    """
    years = years or YEARS
    frames = [ingest_year(y, Path(data_dir)) for y in years]
    df = pd.concat(frames, ignore_index=True)

    if filesystem is None:
        filesystem = get_lake_filesystem()
    if out_dir is None:
        out_dir = lake_path("bronze", DATASET)

    write_sdr(df, out_dir, filesystem=filesystem)
    return df


def _bilan(df: pd.DataFrame, destination: str) -> None:
    """Affiche ce que l'ingestion a vu, y compris ce qui cloche.

    Le bronze ne corrige pas la qualité, mais il n'a aucune raison de la taire.
    Afficher ici les anomalies (déclarations antérieures au constat, délais
    aberrants) les rend visibles dans les logs sans toucher à la donnée — et
    donne au silver une liste de tests qualité à écrire.
    """
    ata = df.jasc_code.str.zfill(4).str[:2]
    motopropulseur = ata.isin([str(c) for c in range(71, 81)])
    ecart = (df.submission_date.dt.tz_localize(None) - df.difficulty_date).dt.days

    print(f"\n✓ {len(df):,} lignes → {destination}")
    print(f"  Millésimes     : {', '.join(sorted(df.source_file.unique()))}")
    print(f"  Période        : {df.difficulty_date.min().date()} → "
          f"{df.difficulty_date.max().date()}")
    print(f"  Partitions     : {df.groupby(['difficulty_year', 'difficulty_month']).ngroups}")
    print(f"  Immatriculations: {df.registry_n_number.nunique():,} N-numbers distincts")
    print(f"  Motopropulseur : {motopropulseur.sum():,} ({motopropulseur.mean() * 100:.1f} %) "
          f"dont ATA 72 moteur : {(ata == '72').sum():,}")

    print("\n  Qualité constatée (non corrigée) :")
    illisibles = int((df.difficulty_year == PARTITION_DATE_INCONNUE).sum())
    print(f"    dates de constat illisibles     : {illisibles}")
    print(f"    déclarations avant le constat   : {int((ecart < 0).sum())}")
    print(f"    délai constat→déclaration       : médiane {ecart.median():.0f} j, "
          f"max {ecart.max():.0f} j")


def main() -> int:
    p = argparse.ArgumentParser(description="Ingestion bronze des SDR FAA → Parquet")
    p.add_argument("--data-dir", default=DATA_DIR)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--years", nargs="+", type=int, default=YEARS, choices=YEARS)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="ingère et affiche le bilan sans rien écrire dans le lake",
    )
    args = p.parse_args()

    if not Path(args.data_dir).exists():
        print(f"[ERREUR] Dossier introuvable : {args.data_dir}")
        return 1

    print(f"Ingestion SDR {', '.join(map(str, args.years))} depuis {args.data_dir}...")
    try:
        frames = [ingest_year(y, Path(args.data_dir)) for y in args.years]
    except FileNotFoundError as e:
        print(f"[ERREUR] {e}")
        return 1

    df = pd.concat(frames, ignore_index=True)

    if args.dry_run:
        destination = "(dry-run : rien n'a été écrit)"
    else:
        out_dir = args.out_dir or lake_path("bronze", DATASET)
        try:
            destination = write_sdr(df, out_dir, filesystem=get_lake_filesystem())
        except KeyError as e:
            print(f"[ERREUR] Variable d'environnement MinIO manquante : {e}")
            return 1

    _bilan(df, destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
