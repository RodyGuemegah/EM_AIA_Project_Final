# Architecture — vue d'ensemble

## 1. Les composants

```mermaid
flowchart LR
    subgraph SRC["Sources"]
        CM["NASA C-MAPSS<br/>265 256 lignes<br/>simulation"]
        SDR["FAA SDR<br/>191 379 rapports<br/>réel"]
        OM["Open-Meteo<br/>7 610 observations<br/>réel, via API"]
        FL["src/fleet<br/>calendrier de vols<br/>généré"]
    end

    subgraph DP["safran-data-platform"]
        ING["Ingestion<br/>lignage · schéma strict"]
        TR["Transformation"]
        subgraph LAKE["Lac MinIO · S3 · Parquet partitionné par mois"]
            BR[("bronze<br/>brut + traçabilité")]
            SI[("silver<br/>nettoyé + features d'historique")]
            GO[("gold<br/>schéma en étoile<br/>spécifié")]
        end
    end

    subgraph ML["safran-mlops"]
        SPLIT{{"Découpage par moteur<br/>graine 42 · anti-fuite"}}
        TRAIN["Apprentissage<br/>XGBoost · 80 % des moteurs"]
        TEST["Examen<br/>20 % des moteurs"]
        EVAL["Évaluation<br/>RMSE + coût"]
        SEUIL["Seuil<br/>matrice de coûts"]
        SHAPG["SHAP global<br/>classement des capteurs"]
        subgraph MLF["MLflow"]
            RUNS[("runs<br/>paramètres · métriques · figures")]
            REG[("registre<br/>versions + alias")]
        end
        subgraph SERV["API FastAPI · conteneur Docker"]
            PRED["Prédiction<br/>RUL en vols"]
            DEC["Alerte<br/>RUL sous le seuil"]
            SHAPL["SHAP local<br/>3 causes principales"]
        end
        DRIFT["Supervision<br/>coût par moteur"]
        SIGNAL["Signal de dérive"]
        DECR{"Décision de réentraîner<br/>responsable maintenance"}
    end

    RM(["Responsable<br/>maintenance"])
    TECH(["Technicien<br/>de maintenance"])
    CI["CI GitHub Actions<br/>ruff + pytest"]

    CM --> ING
    SDR --> ING
    OM --> ING
    FL --> ING
    ING --> BR --> TR --> SI
    SI -.-> GO

    SI --> SPLIT
    SPLIT -->|"80 %"| TRAIN
    SPLIT -->|"20 %"| TEST
    TRAIN --> EVAL
    TEST --> EVAL
    EVAL --> SEUIL --> RUNS
    EVAL --> SHAPG --> RUNS
    TRAIN --> REG

    RM -->|"promotion manuelle"| REG
    REG -->|"@production"| PRED
    PRED --> DEC
    PRED --> SHAPL
    DEC --> TECH
    SHAPL --> TECH

    SI --> DRIFT
    REG --> DRIFT
    DRIFT -->|"coût au-delà de 2× la référence"| SIGNAL
    SIGNAL --> DECR
    DECR --> TRAIN
    TECH -.->|"constat réel après dépose<br/>prévu"| DRIFT

    CI -.-> DP
    CI -.-> ML

    classDef reel fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    classDef genere fill:#fff3e0,stroke:#ef6c00,color:#e65100
    classDef prevu fill:#f5f5f5,stroke:#9e9e9e,color:#616161,stroke-dasharray: 5 5
    classDef humain fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    class SDR,OM reel
    class FL genere
    class GO prevu
    class RM,TECH,DECR humain
```

**Légende**

| couleur ou trait | signification |
|---|---|
| vert | source **réelle** |
| orange | donnée **générée** |
| bleu | **humain** : les points où une personne décide |
| gris, pointillés | **spécifié, non implémenté** |
| flèche en pointillés | lien **prévu** ou non bloquant |

**Cinq lectures à retenir**

- **Deux dépôts, une dépendance à sens unique** : `safran-mlops` lit le
  silver, il ne l'écrit jamais (ADR 0004).
- **Un découpage par moteur, jamais par ligne** : aucun moteur ne figure
  à la fois dans l'apprentissage et dans l'examen. Il n'y a **pas de
  jeu de validation dans cette version du projet** : le choix du modèle et du seuil ayant été effectué à partir de l'examen, les performances rapportées sont susceptibles d'être optimistes.
- **Deux SHAP, deux usages** : le SHAP global, calculé à
  l'entraînement, classe les capteurs et vérifie que le modèle s'appuie
  sur la physique ; le SHAP local, calculé par l'API à chaque requête,
  explique au technicien pourquoi *ce* moteur alerte.
- **Deux humains dans la boucle, trois décisions** : le responsable
  maintenance promeut et décide du réentraînement, le technicien décide
  de la dépose. La machine n'agit jamais seule (ADR 0004, MLOps).
- **Une boucle fermée, et son maillon manquant** : la supervision
  n'enclenche pas l'entraînement, elle **émet un signal de dérive**
  quand le coût dépasse 2× la référence ; c'est le responsable
  maintenance qui décide de réentraîner (ADR 0005, MLOps). La
  supervision a besoin du RUL réel, que seul le technicien constate
  après la dépose : ce retour terrain est prévu, pas encore outillé.

## 2. Le cycle de vie d'un modèle, tel qu'il a été vécu

```mermaid
flowchart TD
    A["Entraîner<br/>FD001 · version 4<br/>RMSE 14,54"] --> B["Évaluer<br/>RMSE et coût en dollars"]
    B --> C{"Promouvoir ?<br/>décision humaine"}
    C -->|"oui"| D["Servir<br/>API @production<br/>seuil 10 vols"]
    C -->|"non"| A
    D --> E["Superviser<br/>coût par moteur"]
    E -->|"FD003 : 48 % de pannes ratées<br/>coût ×5"| F["Réentraîner<br/>FD001 + FD003 · version 6"]
    F --> G["Recalculer le seuil<br/>10 → 14 vols"]
    G --> C
    E -->|"FD004 : 100 % de pannes ratées"| H["Restreindre l'emploi<br/>périmètre déclaré"]

    classDef humain fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef alerte fill:#ffebee,stroke:#c62828,color:#b71c1c
    class C humain
    class H alerte
```

Ce diagramme n'est pas théorique : **chaque nœud porte un chiffre
mesuré**. La branche rouge rappelle que tout ne se corrige pas par
réentraînement — une flotte jamais vue impose de restreindre l'emploi.