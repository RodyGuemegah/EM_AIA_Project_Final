# Décisions d'architecture — plateforme de données

Chaque dépôt du projet tient sa propre série d'ADR : une décision
documente une architecture. Les ADR de la chaîne de modélisation et de service se trouvent dans
`safran-mlops/docs/adr/`.

| n° | décision |
|---|---|
| 0001 | Stockage objet MinIO plutôt qu'un service cloud managé |
| 0002 | Architecture médaillon — gold spécifié, non implémenté |
| 0003 | Parquet partitionné par mois de vol |
| 0004 | Deux dépôts séparés : plateforme de données et MLOps |
| 0005 | Substitution des données SAFRAN par des sources publiques |
| 0006 | Calendrier de vols généré pour donner un flux à C-MAPSS |

Les décisions de moindre portée — plafond du RUL, capteurs constants
conservés, SDR ingérés sans filtrage, dates brutes préservées — sont
documentées dans le tableau « Choix de conception » du README.