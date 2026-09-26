# Guide de déploiement

**Plateforme de maintenance prédictive · version 1.0 · 26 septembre 2026**

Ce guide amène une machine vierge jusqu'à une API qui sert des
prédictions. Il couvre les deux dépôts du projet.

**Durée estimée :** 45 minutes, hors téléchargement des données.

---

## 0. Vue d'ensemble

```
  safran-data-platform                      safran-mlops
  ════════════════════                      ════════════

  données brutes ──► bronze ──► silver ─────► entraînement ──► registre MLflow
  (C-MAPSS, SDR,     ╰──── MinIO ────╯                           │
   météo)                                                        │ @production
                                                                 ▼
                                                          API (conteneur)
```

| service | port | lancé depuis |
|---|---|---|
| MinIO, API S3 | 9000 | `safran-data-platform` |
| MinIO, console | 9001 | `safran-data-platform` |
| MLflow | 5001 | `safran-mlops` |
| API de prédiction | 8000 | `safran-mlops` |

**L'ordre de démarrage est imposé :** MinIO, puis MLflow, puis l'API.
L'API charge son modèle depuis MLflow au démarrage et refuse de
démarrer sans lui (ADR 0002 et 0003, MLOps).

---

## 1. Prérequis

| élément | version | vérification |
|---|---|---|
| Docker Desktop | récent, **lancé** | `docker ps` répond sans erreur |
| Python | **3.11** | `python3.11 --version` |
| Git | — | `git --version` |
| OpenMP (macOS uniquement) | — | `brew install libomp` — requis par XGBoost |

**Sur macOS, le port 5000 est occupé** par le Récepteur AirPlay. C'est
pourquoi MLflow tourne sur le 5001.

---

## 2. Récupération des dépôts

```bash
mkdir projet-certification && cd projet-certification
git clone <https://github.com/RodyGuemegah/EM_AIA_Project_Final.git>/EM_AIA_Project_Final.git safran-data-platform
git clone <https://github.com/RodyGuemegah/EM_AIA_Project_MLOps.git>/EM_AIA_Project_MLOps.git safran-mlops
```

Les deux dossiers doivent être **voisins** : c'est le conteneur MinIO de
`safran-data-platform` qui héberge le lac que `safran-mlops` lit.

### Environnements Python — un par dépôt

```bash
cd safran-data-platform
make install
cd ../safran-mlops
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 3. Configuration

Les identifiants de MinIO ne sont **jamais** versionnés. Un modèle est
fourni.

```bash
cd safran-data-platform
cp .env.example .env
```

Renseigne dans `.env` :

```
MINIO_ROOT_USER=<identifiant>
MINIO_ROOT_PASSWORD=<mot de passe, 8 caractères minimum>
```

**Copie ce même fichier dans `safran-mlops/`**, qui lit le lac avec les
mêmes identifiants :

```bash
cp .env ../safran-mlops/.env
```

Variables facultatives, valeurs par défaut :

| variable | défaut | rôle |
|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9000` | adresse du lac |
| `MINIO_SCHEME` | `http` | `https` pour un stockage S3 réel |
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:5001` | adresse du registre |

---

## 4. Infrastructure — MinIO

```bash
cd safran-data-platform
docker compose up -d
docker ps
```

Attendu : `safran-minio` au statut `Up`.

### Créer les buckets — étape manuelle

**Le code ne crée pas les buckets.** Sans eux, la première écriture
échoue.

1. Ouvrir **http://127.0.0.1:9001** et se connecter avec les
   identifiants du `.env`.
2. **Buckets → Create Bucket** : créer `bronze`.
3. Recommencer pour `silver`.

---

## 5. Données

### 5.1 Téléchargement

| source | emplacement attendu | obtention |
|---|---|---|
| NASA C-MAPSS | `data/raw/CMAPSSData/` | *Turbofan Engine Degradation Simulation*, NASA Prognostics Data Repository |
| FAA SDR | `data/raw/sdr/SDR-2022.csv`, `SDR-2023.csv`, `SDR-2024.csv` | export annuel du système SDR de la FAA |
| Météo | — | téléchargée par le pipeline, **connexion internet requise** |

Le dossier `data/` est exclu de Git : aucune donnée n'est versionnée.

### 5.2 Ingestion et transformation

*Depuis `safran-data-platform`*

| commande | résultat attendu |
|---|---|
| `make sanity` | FD001 : **20 631 lignes, 100 moteurs** |
| `make ingest` | C-MAPSS écrit dans `bronze/engine_sensors` |
| `make ingest-sdr` | **191 379 lignes**, 36 partitions mensuelles |
| `make ingest-weather` | **7 610 lignes**, 25 partitions mensuelles |
| `python -m src.transformation` | silver écrit dans `silver/engine_features` |

---

## 6. Modèle

*Depuis `safran-mlops`, dans un terminal dédié qui reste ouvert :*

```bash
make port        # doit afficher « 5001 libre »
make mlflow
```

Interface : **http://127.0.0.1:5001**

### 6.1 Reproduire le modèle en production

Un clone neuf n'a **ni registre ni modèle** : `mlflow.db` et
`mlartifacts/` sont exclus de Git.

*Depuis `safran-mlops`, dans un autre terminal :*

```bash
.venv/bin/python -m src.models.explain       # figures SHAP, jointes au run
make train                                   # modèle de référence FD001
.venv/bin/python -m src.models.retrain       # modèle FD001 + FD003
```

**`make train` seul ne suffit pas.** Il produit le modèle FD001, dont le
seuil optimal vaut 10. Le seuil configuré dans `src/config.py` — **14** —
est celui du modèle réentraîné (ADR 0007, MLOps). Servir l'un avec le
seuil de l'autre appliquerait une marge de sécurité calculée pour un
autre modèle.

Attendu en sortie de `retrain` : `Nouveau seuil optimal : 14 vols`.

### 6.2 Promouvoir — acte manuel

L'API ne sert que la version portant l'alias `production`. **Aucun
script ne le pose** : la promotion est une décision humaine (ADR 0004,
MLOps).

```bash
.venv/bin/python -c "
from mlflow import MlflowClient
c = MlflowClient('http://127.0.0.1:5001')
v = max(c.search_model_versions(\"name='rul-xgboost'\"), key=lambda v: int(v.version))
c.set_registered_model_alias('rul-xgboost', 'production', v.version)
print('production → version', v.version)
"
```

---

## 7. Service — l'API

*Depuis `safran-mlops`, dans un terminal dédié :*

```bash
make docker-build
docker rm -f rul-api        # sans effet s'il n'existe pas
make docker-run
```

Attendu : `Modèle rul-xgboost vN chargé — 87 features`.

Interface de test : **http://127.0.0.1:8000/docs**

---

## 8. Vérification

*Depuis `safran-mlops`, dans un quatrième terminal :*

| contrôle | commande | attendu |
|---|---|---|
| API vivante | `curl -s http://127.0.0.1:8000/health` | `"statut":"ok"` |
| Conteneur sain | `docker ps` | `rul-api` … `(healthy)` |
| Bout en bout | `.venv/bin/python -m src.api.demo` | moteur en fin de vie : **alerte OUI, seuil 14** · moteur jeune : **alerte non** |
| Qualité | `make lint && make test` | aucun avertissement, tous les tests au vert |

---

## 9. Exploitation courante

La procédure complète, avec les responsabilités, est dans le plan de
gouvernance (§3). En résumé :

| situation | commande | décision |
|---|---|---|
| Superviser la dérive | `python -m src.monitoring.drift` | coût par moteur > **2 ×** la référence → réentraîner |
| Réentraîner | `python -m src.models.retrain` | crée une version, **ne la promeut pas** |
| Promouvoir | commande du §6.2, avec le numéro choisi | responsable maintenance, après comparaison dans MLflow |
| Revenir en arrière | même commande, avec l'ancien numéro | idem |

**Après toute promotion :** reporter le nouveau seuil dans
`src/config.py`, puis reconstruire et redémarrer l'API (§7). Le
conteneur ne relit ni le registre ni la configuration à chaud (ADR 0002).

---

## 10. Arrêt

```bash
docker rm -f rul-api                      # depuis n'importe où
pkill -f "mlflow server"                  # MLflow et ses workers
cd safran-data-platform && docker compose down
```

Les données du lac sont conservées dans `data/minio/`. Le registre est
conservé dans `safran-mlops/mlflow.db` et `mlartifacts/`.

---

## 11. Dépannage

| symptôme | cause | solution |
|---|---|---|
| `Failed to connect to localhost port 9000` | MinIO arrêté | `docker compose up -d` dans `safran-data-platform` |
| `The specified bucket does not exist` | buckets non créés | §4 |
| `Address already in use` au lancement de MLflow | ancien serveur actif | `make port`, puis `pkill -f "mlflow server"` |
| `403` à l'appel de MLflow | hôte absent de la liste blanche | lancer MLflow par `make mlflow`, qui la fournit |
| `container name "/rul-api" is already in use` | ancien conteneur | `docker rm -f rul-api` |
| `Network is unreachable` depuis le conteneur | résolution IPv6 de l'hôte | utiliser `make docker-run`, qui force `host-gateway` |
| `No such artifact` au démarrage de l'API | version enregistrée avant `--serve-artifacts` | réentraîner avec MLflow lancé par `make mlflow`, puis promouvoir la nouvelle version |
| `RegisteredModel … alias production not found` | aucune promotion faite | §6.2 |
| `libomp` introuvable (macOS) | OpenMP absent | `brew install libomp` |
| terminal bloqué sur `dquote>` | guillemet non fermé | **Ctrl + C** |

Le détail des trois incidents propres à la conteneurisation figure
dans `safran-mlops/docs/depannage-artefacts-docker.md`.

---

## 12. Limites de ce déploiement

Ce guide décrit un **environnement de démonstration** sur un poste
unique. En production :

| ici | en production |
|---|---|
| MinIO, un seul nœud, un seul compte | stockage objet répliqué, un compte de service par pipeline |
| MLflow sur SQLite | PostgreSQL |
| artefacts MLflow sur disque local | artefacts sur le stockage objet |
| API et MLflow sans authentification | reverse proxy authentifié |
| lancement manuel | orchestrateur, réseau Docker déclaré |
| buckets créés à la main | infrastructure décrite en code |