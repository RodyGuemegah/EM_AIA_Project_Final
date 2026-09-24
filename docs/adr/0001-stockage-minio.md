# ADR 0001 — Stockage objet MinIO plutôt qu'un service cloud managé

**Date** : 5 septembre 2026 · **Statut** : accepté

## Contexte

Le projet doit démontrer une architecture de lac de données capable de
recevoir plusieurs téraoctets par an, alimentée par trois sources.
Le stockage doit être compatible S3, puisque c'est
l'interface que pyarrow, DuckDB et l'écosystème analytique attendent.

Deux contraintes s'ajoutent : aucun budget d'infrastructure n'est
alloué au projet, et l'environnement de développement doit être
reproductible par un évaluateur sans compte cloud.

## Décision

MinIO, déployé en conteneur Docker, expose une API S3 sur le poste de
développement. Le code n'accède au lac qu'à travers
`src/storage/lake.py`, qui construit un `pyarrow.fs.S3FileSystem`.

Le passage à AWS S3 ne demande que deux paramètres : retirer
`endpoint_override` et `scheme`. Aucune autre ligne du projet ne
connaît la nature du stockage.

## Conséquences

- Le projet est reproductible intégralement sans compte cloud ni carte
  bancaire — condition pour qu'un évaluateur puisse le rejouer.
- La réversibilité est vérifiable : l'isolation dans un seul module est
  contrôlée par le fait que `grep -r "S3FileSystem" src/` ne renvoie
  qu'un fichier.
- Les fonctionnalités managées de S3 — cycles de vie, classes de
  stockage, réplication inter-régions — ne sont pas démontrées. Elles
  relèveraient de la configuration, non du code.
- MinIO tourne sur un poste unique : ni haute disponibilité, ni
  durabilité réelle. Le lac est un environnement de démonstration.

## Alternatives écartées

- **AWS S3.** Coût, et dépendance à un compte pour rejouer le projet.
- **Système de fichiers local.** Ne démontre aucune compétence de
  stockage distribué, et ne prépare aucun passage à l'échelle. Le code
  aurait été écrit contre `LocalFileSystem`, qu'il aurait fallu
  réécrire ensuite.
- **HDFS.** Surdimensionné pour la volumétrie réelle du projet, et
  écosystème en déclin face au stockage objet.