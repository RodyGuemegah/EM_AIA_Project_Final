# ADR 0006 — Calendrier de vols généré pour donner un flux à C-MAPSS

**Date** : 8 septembre 2026 · **Statut** : accepté

## Contexte

C-MAPSS numérote les vols en cycles mais **ne les date pas**. Sans
calendrier, la contrainte de fraîcheur J+24 h annoncée au cahier des
charges serait sans objet, le partitionnement temporel (ADR 0003)
impossible, et le pipeline batch n'aurait rien à traiter chaque jour.

Aucun référentiel public ne relie une unité C-MAPSS à un appareil réel
et à son historique de vols.

## Décision

Le module `src/fleet` reconstitue ce calendrier de façon déterministe,
à graine fixée. Chaque moteur reçoit une immatriculation, une base, une
date de mise en service et un rythme de 2 à 4 vols par jour sur dix
aéroports aux codes OACI réels. Les cycles sont projetés sur les dates
correspondantes.

Le flux couvre du 1er janvier 2022 au 27 janvier 2024, réparti sur
25 partitions mensuelles.

## Conséquences

- La météo devient **joignable exactement** :
  `engine_sensors.(origin | destination, flight_date)` contre
  `weather_daily.(airport, date)`, sans hypothèse. Les SDR, eux, ne se
  joignent pas — ils portent de vrais immatriculés américains, sans clé
  commune avec une flotte simulée. Le README l'explicite.
- Les rotations sont physiquement cohérentes : l'aéroport d'arrivée
  d'un vol est l'aéroport de départ du suivant. Un test automatisé le
  vérifie, et un second garantit qu'un moteur porte une et une seule
  immatriculation.
- Le rattachement moteur ↔ avion ↔ vols reste **généré**, et aucune
  variable qui en dérive n'alimente le modèle.
- La reproductibilité est totale à graine fixée : un évaluateur
  obtiendra la même flotte.

## Alternatives écartées

- **Dater les cycles par une simple séquence quotidienne.** Aurait
  produit un vol par jour et par moteur, sans escales ni rotations :
  aucune jointure météo réaliste, aucune structure de flotte.
- **Utiliser des données de vol réelles (OpenSky).** Aucun moyen de les
  rattacher à une unité C-MAPSS. Le problème de fabrication se
  déplacerait sans disparaître, en ajoutant une source à ingérer.
- **Renoncer au calendrier.** Aurait vidé de sens le partitionnement
  temporel, la fraîcheur J+24 h et la jointure météo — trois éléments
  du cahier des charges.