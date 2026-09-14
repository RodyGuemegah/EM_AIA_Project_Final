# Note de substitution des données

**Projet de certification — Plateforme IA de maintenance prédictive, SAFRAN Aircraft Engines**
SODJI Rodney · 14 septembre 2026

---

## Objet

Les données propriétaires de SAFRAN n'étant pas accessibles, ce projet s'appuie sur des jeux de données publics. Cette note déclare, source par source, ce qui est réel et ce qui est généré, et documente les limites de la substitution.

Elle répond au retour du jury : *« il faut démontrer ou simuler de façon crédible les autres sources, volumes et flux, sans prétendre que C-MAPSS suffit à lui seul »*.

**Six sources réelles, trois éléments générés.** Ce qui est fabriqué n'est pas la donnée — c'est le rattachement entre des jeux réels.

---

## Tableau des sources

| Source annoncée (doc §2) | Substitut retenu | Nature | Volume | Limite assumée |
|---|---|---|---|---|
| Capteurs embarqués | NASA C-MAPSS, FD001–FD004 | Réel (simulation NASA) | 265 256 lignes, 1 416 moteurs | 21 capteurs contre plusieurs centaines ; un point agrégé par vol |
| Historique de maintenance ERP | FAA Service Difficulty Reports | **Réel** | 191 379 rapports, 2022-2024 | Colonnes moteur renseignées à moins de 3 % |
| Rapports techniciens en texte libre | FAA SDR, champ `Discrepancy` | **Réel** | 191 379 textes, 100 % de remplissage | Rédigés en anglais, sur flotte américaine |
| Données météorologiques | Open-Meteo, archives historiques | **Réel** | 7 610 observations, 10 aéroports | Maille du modèle à 4,5 km de l'aéroport |
| Référentiel aéroportuaire | Codes OACI réels | **Réel** | 10 aéroports européens | Sous-ensemble restreint |
| Nomenclature composants | Codes JASC / chapitres ATA | **Standard public** | 2 066 rapports ATA 72 (moteur) | — |
| Plans de vol et immatriculations | Généré par `src.fleet` | Généré | 1 416 appareils | Rotations simulées, non issues de données réelles |
| Identités de techniciens | Généré, pseudonymisées | Généré | — | Nécessaire pour rendre le RGPD applicable |
| Appariement moteur ↔ avion ↔ vols | Généré | Généré | — | Aucun référentiel public ne permet ce rattachement |

---

## Réponse aux trois axes du jury

### Sources

Le socle capteurs C-MAPSS est complété par **deux sources publiques réelles**.

Les **Service Difficulty Reports de la FAA** apportent 191 379 signalements de panne déclarés entre 2022 et 2024, portant sur 12 103 appareils. Chaque rapport contient un descriptif rédigé par un mécanicien, un code de système JASC, la pièce concernée et son état. Cette source comble d'un seul tenant deux cases du document : l'historique de maintenance et les rapports d'intervention en texte libre.

Les **archives Open-Meteo** apportent 7 610 observations météorologiques quotidiennes sur les dix aéroports de la flotte simulée. Au-delà de la donnée, cette source démontre un **second mode d'acquisition** : un flux réseau, là où les autres sources sont des fichiers. Elle valide la « couche d'ingestion unifiée » annoncée au bloc 2.

Le lac contient ainsi trois jeux de données de natures distinctes : séries temporelles multivariées, événements datés accompagnés de texte libre, et observations externes. La **variété** des 3V est établie par construction.

### Volumes

La volumétrie n'est pas revendiquée, elle est **mesurée et extrapolée** (voir `docs/benchmarks/volumetrie.md`).

Mesures à deux échelles, ×1 et ×10 :

- coût par ligne stable à **84 octets**, identique aux deux échelles — la réplication n'a pas biaisé la compression
- le gain du partitionnement **croît avec le volume** : 13,8× à ×1, **21,9× à ×10**
- lire un mois dans le lac dix fois plus gros (26 ms) reste **deux fois plus rapide** que scanner intégralement le lac initial (56 ms)
- Parquet divise le stockage par **8,5** face au CSV, répondant à la contrainte de maîtrise budgétaire

Extrapolation à la flotte cible — 15 000 moteurs × 800 vols, soit 12 millions de vols annuels :

| granularité | volume annuel |
|---|---|
| 1 ligne par vol, 21 capteurs *(mesuré)* | 1 Go |
| 1 ligne par vol, 250 capteurs | 12 Go |
| enregistrement continu 1 Hz sur 2 h de vol | **86 To** |

**Cette table explique l'écart avec le document de présentation**, qui annonce « plusieurs téraoctets par an ». Cette volumétrie correspond à un enregistrement continu en vol — 7 200 points par vol. C-MAPSS ne fournit qu'un point agrégé par vol. Les deux chiffres sont cohérents une fois la granularité explicitée.

### Flux

C-MAPSS numérote les vols en cycles mais **ne les date pas**. Sans calendrier, la contrainte de fraîcheur J+24h annoncée au §1.2 serait sans objet, et le pipeline batch n'aurait rien à traiter chaque jour.

Le module `src.fleet` reconstitue ce calendrier : chaque moteur reçoit une immatriculation, une base, une date de mise en service et un rythme d'exploitation de 2 à 4 vols par jour. Les cycles sont projetés sur les dates correspondantes, avec des rotations cohérentes — l'aéroport d'arrivée d'un vol est l'aéroport de départ du suivant, ce que vérifie un test automatisé.

Le flux couvre du 1er janvier 2022 au 27 janvier 2024, réparti sur 25 partitions mensuelles.

---

## Ce qui reste généré, et pourquoi

**L'appariement moteur ↔ avion ↔ vols.** Aucun référentiel public ne relie une unité C-MAPSS à un appareil réel et à son historique de vols. Ce rattachement est tiré de façon déterministe, reproductible par graine fixée.

**Les identités de techniciens.** Les SDR sont anonymisés. Or le bloc 1 exige une gouvernance RGPD applicable : sans données à caractère personnel dans le pipeline, la pseudonymisation serait décorative. Ces identités sont générées puis pseudonymisées par hachage salé.

**Le facteur d'échelle.** Utilisé uniquement pour le benchmark de volumétrie, avec de nouveaux identifiants de moteurs à chaque réplication afin de ne pas biaiser la mesure de compression.

---

## Limites assumées

**Les colonnes moteur des SDR sont inexploitables** : `EngineMake` est renseigné à 2,8 %, `EngineTotalCycles` à 1,5 %. Elles sont conservées dans le bronze au titre de la traçabilité mais ne fondent aucun traitement.

**Les données météorologiques ne sont pas utilisées comme variables du modèle.** Le rattachement moteur-aéroport étant généré, aucune corrélation physique ne peut exister. Sur données d'exploitation réelles — démarrages à froid, ingestion de particules, corrosion saline — ces variables seraient exploitables sans modification de la chaîne.

**La météo n'est pas celle de l'aéroport** mais celle de la maille du modèle la plus proche, à 4,5 km au maximum. Les coordonnées demandées et servies sont conservées pour que cet écart reste mesurable.

**La granularité est agrégée**, un point par vol, là où un enregistreur réel produit un point par seconde.

**Le passage à N-CMAPSS a été envisagé et écarté.** Ce jeu de 2021 apporterait des profils de vol réels et sept modes de défaillance. L'objection sur la volumétrie ayant été traitée par la mesure et l'extrapolation plutôt que par l'ajout de données brutes, et les sources manquantes ayant été comblées par deux jeux réels, la bascule aurait imposé une refonte du socle capteurs et du scénario de dérive à dix jours du rendu, pour un gain marginal au regard des critères d'évaluation. Elle est identifiée comme évolution naturelle du projet.

---

## Contrôles de crédibilité

Les données générées font l'objet de tests automatisés vérifiant leur cohérence physique, au même titre que les données réelles :

- aucun appareil ne change d'aéroport sans avoir volé
- un moteur porte une et une seule immatriculation
- la clé primaire des SDR est unique sur les trois millésimes réunis
- aucun moteur ne figure simultanément dans les jeux d'apprentissage et d'examen

Ces contrôles ont détecté des anomalies réelles, dont **deux déclarations antérieures au constat** parmi les 191 379 enregistrements publics de la FAA.
