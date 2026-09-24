# ADR 0004 — Deux dépôts séparés : plateforme de données et MLOps

**Date** : 15 septembre 2026 · **Statut** : accepté

## Contexte

Le projet couvre deux domaines aux cycles de vie distincts :
l'ingestion et la transformation des données d'une part, la
modélisation et le service d'autre part. Il fallait décider s'ils
vivaient dans un dépôt unique ou séparés.

## Décision

Deux dépôts.

- `safran-data-platform` — ingestion, bronze, silver, benchmarks.
  **Propriétaire de l'infrastructure** : c'est lui qui porte le
  `docker-compose.yml` de MinIO.
- `safran-mlops` — modélisation, seuil, explicabilité, registre, API,
  supervision. **Client du lac**, jamais producteur.

Le module `src/storage/lake.py` est dupliqué dans les deux dépôts.

## Conséquences

- La dépendance est explicite et à sens unique : `safran-mlops` lit le
  lac, il ne l'alimente pas. Un développeur du dépôt MLOps ne peut pas
  modifier le silver par inadvertance.
- Les deux dépôts ont leur propre CI, leurs propres dépendances et leur
  propre rythme de livraison : `requirements.txt` du dépôt MLOps
  embarque mlflow, shap et xgboost, inutiles à l'ingestion.
- **La duplication de `lake.py` est assumée.** En extraire une
  bibliothèque partagée imposerait un dépôt supplémentaire, un cycle de
  publication et une gestion de versions, pour quarante lignes stables
  depuis la première semaine.
- L'ordre de démarrage devient une contrainte d'exploitation :
  l'infrastructure se lance depuis `safran-data-platform`. Documenté en
  tête du guide de déploiement.

## Alternatives écartées

- **Dépôt unique.** Aurait mêlé les dépendances et rendu la CI plus
  lente et plus fragile : un échec d'installation de shap aurait bloqué
  la livraison d'un correctif d'ingestion.
- **Monorepo avec gestionnaire de paquets.** Outillage disproportionné
  pour deux composants.
- **Bibliothèque partagée publiée.** Coût de maintenance supérieur au
  coût de la duplication, pour un module qui n'a pas changé.