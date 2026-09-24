# ADR 0003 — Parquet partitionné par mois de vol

**Date** : 7 septembre 2026 · **Statut** : accepté

## Contexte

Le lac doit absorber 265 256 lignes de capteurs, 191 379 rapports de
maintenance et 7 610 observations météorologiques, et rester
interrogeable à une volumétrie cible cent fois supérieure. Le format
de stockage et le schéma de partitionnement conditionnent à la fois le
coût de stockage et le temps de réponse.

## Décision

Parquet, partitionné selon la convention Hive sur `flight_year` et
`flight_month`.

Mesuré (`docs/benchmarks/volumetrie.md`), à deux échelles :

- coût par ligne stable à **84 octets**, identique à ×1 et ×10 — la
  compression ne se dégrade pas avec le volume
- gain du partitionnement **croissant** : 13,8× à ×1, **21,9× à ×10**
- lire un mois dans le lac dix fois plus gros (26 ms) reste **deux fois
  plus rapide** que scanner intégralement le lac initial (56 ms)
- Parquet divise le stockage par **8,5** face au CSV



## Conséquences

- Les requêtes datées ne lisent que les partitions concernées.
- Le stockage colonnaire permet de ne lire que les colonnes demandées —
  ce dont `load_silver(columns=...)` tire parti.
- Les clés de partition sont en `int32` **non nullables** : une colonne
  de partition nullable produit un dataset que pyarrow écrit mais
  refuse de relire. Une date illisible part en quarantaine
  `difficulty_year=-1` plutôt que de casser le dataset.
- Le partitionnement est figé à l'écriture : le changer imposerait de
  réécrire le lac.

## Alternatives écartées

- **CSV.** 8,5 fois plus volumineux, aucun typage, aucune sélection de
  colonnes.
- **Partitionner par `fd_subset`.** Aurait épousé la structure du jeu
  de données NASA plutôt que l'usage réel : les requêtes d'exploitation
  sont datées, pas indexées par sous-jeu. `fd_subset` reste une colonne
  filtrable.
- **Delta Lake / Iceberg.** Apporteraient les transactions et le
  voyage dans le temps, au prix d'une dépendance supplémentaire non
  justifiée par un pipeline batch à écrivain unique.