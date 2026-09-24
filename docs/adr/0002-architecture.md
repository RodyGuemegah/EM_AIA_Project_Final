# ADR 0002 — Architecture médaillon, couche gold spécifiée mais non implémentée

**Date** : 6 septembre 2026 · **Statut** : accepté

## Contexte

Le lac doit accueillir des données de natures très différentes — séries
temporelles de capteurs, événements de maintenance en texte libre,
observations météorologiques — et servir deux usages distincts :
l'entraînement de modèles et la restitution analytique.

## Décision

Trois couches, aux responsabilités strictement séparées :

- **bronze** — la donnée brute, augmentée des seules colonnes de
  traçabilité (`source_file`, `ingested_at`, `pipeline_version`). Le
  bronze ne nettoie jamais rien : il doit permettre de rejouer un
  traitement et de retrouver le fichier d'origine.
- **silver** — la donnée nettoyée et enrichie des features
  d'historique (`_moy20`, `_pente`, `_derive`). C'est la couche que
  consomment les modèles.
- **gold** — schéma en étoile pour la restitution analytique.
  **Spécifié, non implémenté.**

## Conséquences

- La séparation bronze/silver rend les décisions de nettoyage
  réversibles : supprimer un capteur plat est un choix de silver, jamais
  d'ingestion.
- L'absence de gold signifie qu'aucune requête métier n'est servie
  directement : un analyste devrait passer par le silver, dont le grain
  et la dénormalisation ne sont pas pensés pour lui.
- La compétence de modélisation dimensionnelle est démontrée par la
  spécification (`docs/architecture/gold_schema.md`), non par le code.

## Alternatives écartées

- **Implémenter le gold.** Environ six heures, prises sur la chaîne de
  décision — seuil, explicabilité, supervision de dérive. L'inférence
  consommant le silver, le gold n'aurait servi aucun livrable évalué du
  bloc modélisation. L'implémentation est identifiée comme l'évolution
  immédiate.
- **Fusionner bronze et silver.** Aurait interdit de rejouer un
  nettoyage sans re-télécharger les sources — dont les SDR de la FAA,
  qui sont republiés et donc non reproductibles à l'identique.