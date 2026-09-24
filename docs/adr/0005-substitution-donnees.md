# ADR 0005 — Substitution des données SAFRAN par des sources publiques

**Date** : 14 septembre 2026 · **Statut** : accepté

## Contexte

Les données propriétaires de SAFRAN ne sont pas accessibles. Le retour
du jury a par ailleurs relevé un écart entre l'architecture annoncée —
plusieurs téraoctets, ERP, textes libres, météo — et le seul jeu
C-MAPSS, limité à des séries temporelles de capteurs.

## Décision

Trois sources, dont **deux réelles et indépendantes de C-MAPSS** :

| source annoncée | substitut | nature | volume |
|---|---|---|---|
| capteurs embarqués | NASA C-MAPSS FD001–FD004 | simulation NASA | 265 256 lignes |
| historique de maintenance + textes techniciens | FAA Service Difficulty Reports | **réel** | 191 379 rapports |
| données météorologiques | archives Open-Meteo | **réel** | 7 610 observations |

Les volumes ne sont pas revendiqués mais **mesurés puis extrapolés**
(ADR 0003), ce qui explique l'écart avec « plusieurs téraoctets » : la
volumétrie annoncée correspond à un enregistrement continu à 1 Hz
(86 To/an), là où C-MAPSS fournit un point agrégé par vol (1 Go/an).

Le détail source par source, avec ce qui est réel et ce qui est généré,
figure dans `docs/note_substitution_donnees.md`.

## Conséquences

- La variété des 3V est établie par construction : séries temporelles,
  événements datés avec texte libre, observations externes.
- Open-Meteo démontre un **second mode d'acquisition** — un flux
  réseau, là où les autres sources sont des fichiers.
- Les colonnes moteur des SDR sont inexploitables (`EngineMake`
  renseigné à 2,8 %). Conservées au bronze pour la traçabilité, elles
  ne fondent aucun traitement.
- Les données météorologiques ne sont pas utilisées comme variables du
  modèle : le rattachement moteur-aéroport étant généré, aucune
  corrélation physique ne peut exister. La chaîne les accepterait sans
  modification sur des données d'exploitation réelles.

## Alternatives écartées

- **N-CMAPSS (2021).** Apporterait des profils de vol réels et sept
  modes de défaillance. Écarté le 13 septembre : l'objection portait
  sur les sources, les volumes et les flux, tous trois traités
  autrement. N-CMAPSS n'aurait répondu qu'au socle capteurs, en
  imposant une refonte de toute la chaîne aval à dix jours du rendu.
  Identifié comme évolution immédiate.
- **Générer des données synthétiques de maintenance.** Aurait posé de
  la fabrication sur de la fabrication. Les SDR, réels, sont plus
  défendables même incomplets.