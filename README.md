# safran-data-platform

Plateforme de maintenance prédictive des moteurs d'avion — dépôt n°1 (blocs 1, 2, 3).
Projet de certification Mastère 2 Architecte en IA — SODJI Rodney.

> ⚠️ **Note de substitution des données** — les données propriétaires SAFRAN n'étant pas
> accessibles, ce projet s'appuie sur le jeu public NASA C-MAPSS (Turbofan Engine
> Degradation Simulation) du domaine aéronautique.

---

## Démarrage

```bash
make install          # crée .venv et installe les dépendances
make test             # 22 tests sur données factices — doit passer sans données réelles
```

`make test` fonctionne **avant** tout téléchargement : les tests génèrent eux-mêmes
des fichiers au format C-MAPSS. C'est voulu — la CI ne doit jamais dépendre
de la présence d'un jeu de données lourd.

## Récupérer C-MAPSS

1. Télécharger le jeu *Turbofan Engine Degradation Simulation* (NASA Prognostics Data
   Repository, ou miroir Kaggle).
2. Dézipper dans `data/raw/CMAPSSData/` — tu dois obtenir `train_FD001.txt`,
   `test_FD001.txt`, `RUL_FD001.txt`, etc.
3. Vérifier :

```bash
make sanity
```

Sortie attendue sur le vrai FD001 : **20 631 lignes, 100 moteurs, 6 capteurs constants**
(`sensor_01, 05, 10, 16, 18, 19`). Le `sensor_06` ne prend que 2 valeurs distinctes :
quasi-constant, à traiter comme les précédents — décision à consigner en ADR.

> Le dossier `data/` est ignoré par Git. Aucune donnée lourde ne doit être versionnée —
> seul un échantillon léger le sera, en fin de projet, pour rendre la démo reproductible.

## Utilisation

```python
from src.cmapss import load_train, load_test, constant_sensors

train = load_train("data/raw/CMAPSSData/train_FD001.txt")
test  = load_test("data/raw/CMAPSSData/test_FD001.txt",
                  "data/raw/CMAPSSData/RUL_FD001.txt")

train = train.drop(columns=constant_sensors(train))
```

## Choix de conception

| Décision | Justification |
|---|---|
| RUL plafonné à 125 cycles | En début de vie, la dégradation n'est pas observable par les capteurs. Un RUL linéaire ferait apprendre du bruit au modèle. Valeur de référence dans la littérature C-MAPSS. |
| Capteurs constants détectés, pas supprimés d'office | La suppression est une décision d'expérimentation, pas de chargement. Le loader informe, l'utilisateur décide. |
| Tests sur données factices | La CI reste rapide et ne dépend d'aucun téléchargement. |
| Erreur explicite si le nombre de colonnes est faux | Échouer vite et clairement plutôt que produire un DataFrame silencieusement décalé. |

## Structure

```
src/cmapss/loader.py      chargement C-MAPSS + calcul du RUL
src/fleet/scheduler.py    planificateur de vols simulé (projette les cycles C-MAPSS sur un calendrier)
src/ingestion/bronze.py   ingestion vers la couche bronze (Parquet partitionné, MinIO)
src/storage/lake.py       accès au data lake MinIO (S3FileSystem)
src/models/dataset.py     préparation du dataset ML (split train/test par moteur)
src/sanity.py             contrôle de bon fonctionnement
tests/                    tests unitaires sur données factices
data/                     données locales (non versionnées)
```

## Prochaines étapes

- [x] Planificateur de vols — projeter les cycles C-MAPSS sur un calendrier réel
- [x] Ingestion vers MinIO en Parquet partitionné (couche bronze)
- [ ] Couches silver / gold
- [ ] Star schema dbt + tests qualité
- [ ] DAG Airflow post-vol
