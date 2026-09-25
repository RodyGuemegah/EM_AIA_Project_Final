# Plan de gouvernance — plateforme de maintenance prédictive

**SODJI Rodney · 25 septembre 2026 · version 1.0**

## 0. Objet et périmètre

Ce plan fixe les règles qui encadrent les données, les modèles et les
décisions de la plateforme : qui fait quoi, selon quelles règles, et qui
répond du résultat.

Il couvre les deux dépôts du projet : `safran-data-platform` (ingestion,
lac, transformations) et `safran-mlops` (modèles, registre, service,
supervision). Il s'appuie sur les décisions déjà tracées dans leurs ADR
et y renvoie plutôt que de les répéter.

**Chaque règle porte un statut** : *en place* (implémenté et vérifiable
dans le code), *partiel*, ou *prévu* (spécifié, non implémenté). Un plan
de gouvernance qui ne distingue pas ce qui existe de ce qui est promis
ne permet pas d'auditer.

> **Dans le cadre du projet, tous les rôles sont tenus par une seule
> personne.** La séparation des rôles ci-dessous est spécifiée pour un
> déploiement réel ; elle ne peut pas être démontrée par un projet
> individuel.

---

## 1. Rôles et responsabilités

| rôle | responsabilité |
|---|---|
| **Data engineer (DE)** | ingestion, lac, qualité des pipelines |
| **ML engineer (MLE)** | entraînement, évaluation, registre, service |
| **Responsable maintenance (RM)** | répond des décisions opérationnelles de dépose ; décideur final sur ce qui part en production |
| **Data owner (DO)** | propriétaire métier d'un domaine de données ; arbitre les règles d'usage |
| **DPO** | conformité RGPD, registre des traitements |
| **RSSI** | sécurité, accès, secrets |

### Matrice RACI

*R : réalise · A : répond du résultat (un seul par ligne) · C : consulté · I : informé*

| activité | DE | MLE | RM | DO | DPO | RSSI |
|---|---|---|---|---|---|---|
| Ajouter une source de données | R | | | A | C | C |
| Modifier le schéma du silver | R | C | | A | | |
| Entraîner un modèle | | R/A | | | | |
| **Promouvoir un modèle en production** | | R | **A** | C | I | |
| **Modifier le seuil d'alerte** | | R | **A** | C | | |
| Traiter une alerte de dérive | C | R | A | I | | |
| Retirer un modèle de production | | R | A | I | | |
| Accorder un accès au lac | R | | | C | | A |
| Répondre à une demande d'exercice de droits | R | | | C | A | |

**Pourquoi le responsable maintenance, et non l'ingénieur ML, répond de
la promotion et du seuil :** ce sont les deux décisions qui déterminent
si un moteur casse en vol. Celui qui en répond doit être celui qui en
porte la conséquence opérationnelle. C'est la traduction
organisationnelle de l'ADR 0004 (MLOps) : la machine entraîne, un
humain décide — et le RACI dit lequel.

---

## 2. Gouvernance des données

### 2.1 Inventaire des sources

| source | nature | volume | données personnelles | conditions d'usage |
|---|---|---|---|---|
| NASA C-MAPSS FD001–FD004 | simulation | **265 256 lignes après ingestion des trajectoires FD001–FD004** | aucune | diffusion publique NASA |
| FAA Service Difficulty Reports 2022–2024 | réelle |**191 379 rapports après ingestion des fichiers FAA 2022–2024** | **oui, indirectes** — voir §5 | données publiques de l'administration fédérale américaine |
| Open-Meteo, archives | réelle | 7 610 observations | aucune | CC BY 4.0, attribution requise |
| Calendrier de vols (`src/fleet`) | générée | 1 416 appareils | aucune | interne |

*Conditions d'usage à confirmer à la source avant toute exploitation
hors du cadre du projet.*

### 2.2 Règles

| règle | mise en œuvre | statut |
|---|---|---|
| **Lignage** — toute ligne du lac est rattachable à son fichier d'origine | colonnes `source_file`, `ingested_at`, `pipeline_version` ajoutées au bronze | en place |
| **Rejouabilité** — le bronze n'est jamais nettoyé | tout filtrage appartient au silver (ADR 0002) | en place |
| **Échec explicite** sur schéma inattendu | vérification des noms **et** de l'ordre des 76 colonnes SDR ; erreur si le nombre de colonnes C-MAPSS est faux | en place |
| **Hypothèses vérifiables** | dates SDR conservées en clair (`*_raw`) à côté des dates typées ; coordonnées météo demandées **et** servies conservées | en place |
| **Quarantaine** plutôt que perte | une date illisible part en partition `difficulty_year=-1` | en place |
| **Contrôles de cohérence** sur les données générées | tests : un appareil ne change pas d'aéroport sans voler, un moteur porte une seule immatriculation | en place |
| **Anti-fuite** entre apprentissage et examen | découpage par moteur, vérifié en CI à chaque poussée | en place |

### 2.3 Accès

| zone | lecture | écriture | statut |
|---|---|---|---|
| bronze | DE | pipelines d'ingestion uniquement | partiel |
| silver | DE, MLE | pipeline de transformation uniquement | partiel |
| registre MLflow | MLE, RM | MLE (versions) ; alias `production` : sur décision du RM | partiel |

*Partiel : la séparation est garantie par l'architecture — le dépôt
MLOps est client du lac et ne l'écrit jamais (ADR 0004) — mais MinIO
fonctionne avec un compte unique. En production : un compte de service
par pipeline, avec des politiques d'accès par préfixe de bucket.*

### 2.4 Conservation

| donnée | durée | justification | statut |
|---|---|---|---|
| bronze | durée de vie de la plateforme | seule copie rejouable ; les SDR sont republiés par la FAA et ne sont pas reproductibles à l'identique | prévu |
| silver | recalculable à tout moment | dérivé du bronze | — |
| runs et versions MLflow | sans limite | piste d'audit des décisions de promotion | en place |
| données personnelles des SDR | limitée à la finalité — voir registre RGPD | minimisation | prévu |

*En exploitation réelle, la durée de conservation du bronze doit
s'aligner sur les obligations de conservation des enregistrements de
maintenance applicables — à fixer avec le data owner.*

---

## 3. Gouvernance des modèles

### 3.1 Cycle de vie

```
entraîner ──► évaluer ──► enregistrer ──► PROMOUVOIR ──► servir ──► superviser
 (auto)       (auto)       (auto)         (humain)                     │
    ▲                                                                  │
    └──────────────────── réentraîner ◄── alerte de dérive ◄───────────┘
```

| étape | règle | statut |
|---|---|---|
| Entraînement | graine fixée, découpage par moteur, mêmes conditions pour tout modèle comparé (ADR 0006) | en place |
| Évaluation | métrique technique (RMSE) **et** métrique économique (coût au seuil optimal) enregistrées à chaque run | en place |
| Enregistrement | toute version au registre, avec sa signature d'entrée | en place |
| **Promotion** | **manuelle uniquement**, par déplacement de l'alias `production`, après comparaison avec la version en place (ADR 0004) | en place |
| Recalcul du seuil | obligatoire à chaque promotion — un nouveau modèle a un nouveau biais (ADR 0001) | en place |
| Service | le modèle est résolu par alias, jamais par numéro de version (ADR 0003) | en place |
| Supervision | coût par moteur ; la RMSE n'est qu'un indicateur secondaire (ADR 0005) | partiel |
| Retrait | retour à la version précédente par simple déplacement de l'alias | en place |

### 3.2 Critères de promotion

Une version n'est promue que si, face à la version en place :

1. **aucune panne ratée supplémentaire** sur les flottes du périmètre ;
2. un coût par moteur **inférieur ou équivalent** sur ces flottes ;
3. la dégradation éventuelle sur une flotte est **explicitement
   arbitrée** contre le gain sur une autre, et consignée dans un ADR.

*Application réelle : la version 6 a été promue le 22 septembre —
dérive corrigée sur FD003 (48 % de pannes ratées → 0 %) pour +2,9 % de
coût sur FD001. ADR 0007 (MLOps).*

### 3.3 Supervision et escalade

| déclencheur | action | responsable | statut |
|---|---|---|---|
| coût par moteur > **2 ×** la référence nominale | réentraînement, puis décision de promotion | MLE → RM | partiel |
| nouvelle flotte hors périmètre d'apprentissage | **pas de mise en service** avant évaluation dédiée | RM | en place (règle) |
| service indisponible | le conteneur est marqué `unhealthy` par sa sonde | — | en place |

*Partiel : l'indicateur est calculé par `src/monitoring/drift.py`, mais
son déclenchement n'est pas automatisé. Il est surtout **rétrospectif** :
le coût exige de connaître le RUL réel, donc d'attendre la panne. Un
indicateur avancé sur les distributions d'entrée est prévu en
complément.*

### 3.4 Périmètre d'emploi déclaré

Le modèle en production est validé sur **FD001 et FD003 uniquement**.
Sur FD004 — six conditions de vol, jamais vues — il laisse passer 100 %
des pannes, et la politique optimale y consiste à ne pas alerter.

**Toute application à une flotte dont les conditions d'exploitation
diffèrent de celles du périmètre est interdite sans évaluation
préalable.** C'est la conséquence directe de ce qui a été mesuré.

---

## 4. Sécurité

| règle | mise en œuvre | statut |
|---|---|---|
| Aucun secret dans Git | identifiants MinIO dans un fichier d'environnement exclu par `.gitignore` | en place |
| Service sans privilèges | le conteneur de l'API tourne sous un utilisateur dédié, jamais `root` | en place |
| Registre non ouvert à tous | MLflow n'accepte que les hôtes explicitement listés (`--allowed-hosts`) | en place |
| Surface minimale | l'image de l'API n'embarque que ses propres dépendances (`requirements-api.txt`) | en place |
| Authentification du service et du registre | reverse proxy authentifié devant l'API et MLflow | prévu |
| Rotation des secrets | — | prévu |
| Base de métadonnées concurrente | SQLite, suffisante pour un utilisateur ; PostgreSQL en production | prévu |

---

## 5. Conformité

### 5.1 RGPD

**Le pipeline peut contenir des données susceptibles de constituer des données à caractère personnel, notamment via certains identifiants d'aéronefs ou le contenu textuel libre des rapports. Le
registre de la FAA étant public, l'immatriculation d'un appareil détenu
par un particulier permet d'identifier son propriétaire : c'est une
donnée personnelle indirecte. Le champ texte libre `Discrepancy` peut
par ailleurs mentionner des personnes.

| mesure | statut |
|---|---|
| Finalité déterminée : analyse des défaillances, **aucun ciblage de personnes** | en place (règle) |
| Aucune donnée personnelle n'alimente le modèle | en place — les SDR ne sont pas joints aux capteurs |
| Pseudonymisation des immatriculations au passage en silver | **prévu** |
| Registre des traitements (article 30) | voir `docs/registre_rgpd.md` |

### 5.2 AI Act

La qualification détaillée figure dans `docs/conformite.md`. En résumé :
a maintenance aéronautique n'est pas, en tant que telle, un cas d'usage listé à l'Annexe III de l'AI Act. La qualification au titre de l'article 6(1) doit néanmoins être examinée séparément si le système est destiné à constituer un composant de sécurité d'un produit relevant de la législation sectorielle applicable à l'aviation et soumis aux conditions d'évaluation de conformité prévues par cette législation. Dans le périmètre de ce projet, le modèle est présenté comme un outil d'aide à la décision au sol et n'est pas intégré à un système embarqué ni déclaré comme composant de sécurité. La qualification réglementaire définitive relèverait néanmoins d'une analyse juridique et réglementaire du système réel.
**Le projet applique néanmoins volontairement** les exigences de
transparence, d'explicabilité, de supervision humaine et de
documentation :

| exigence | mise en œuvre | statut |
|---|---|---|
| Explicabilité | chaque prédiction de l'API renvoie ses trois causes principales (SHAP) | en place |
| Supervision humaine | promotion manuelle ; l'alerte déclenche une décision, pas une dépose | en place |
| Traçabilité | version du modèle renvoyée dans chaque réponse ; runs MLflow conservés | partiel |
| Documentation technique | 13 ADR, note de substitution, benchmarks | en place |

*Partiel : l'API renvoie la version du modèle, mais **ne journalise pas
ses prédictions**. Si un moteur tombe en panne, on ne peut pas retrouver
aujourd'hui ce que le système avait prédit ce jour-là. Un journal des
prédictions est prévu.*

---

## 6. Matrice des risques

*Probabilité (P) et impact (I) de 1 à 3 ; criticité = P × I.
🔴 ≥ 6 · 🟠 3–4 · 🟢 ≤ 2*

| n° | risque | P | I | crit. | parade | statut | résiduel |
|---|---|---|---|---|---|---|---|
| R1 | **Dérive** : la flotte évolue, le modèle se périme | 3 | 3 | 🔴 9 | supervision par le coût ; réentraînement ; périmètre d'emploi déclaré | partiel | 🟠 — alerte rétrospective |
| R2 | **Optimisme du modèle** près de la panne (81 % de surestimation) | 3 | 3 | 🔴 9 | marge intégrée au seuil, calculée par matrice de coûts | en place | 🟢 |
| R3 | **Promotion d'un modèle dégradé** | 2 | 3 | 🔴 6 | promotion manuelle, critères §3.2, comparaison MLflow | en place | 🟢 |
| R4 | **Emploi hors périmètre** (flotte type FD004) | 2 | 3 | 🔴 6 | interdiction sans évaluation (§3.4) | règle | 🟠 — non outillé |
| R5 | **Surconfiance** de l'utilisateur dans l'alerte | 2 | 3 | 🔴 6 | causes SHAP affichées ; l'alerte déclenche une décision humaine | en place | 🟠 |
| R6 | **Fuite de données** train/test : performance surévaluée | 2 | 3 | 🔴 6 | découpage par moteur, test en CI | en place | 🟢 |
| R7 | **Hypothèses de coût erronées** (AOG, dépose) | 2 | 2 | 🟠 4 | analyse de sensibilité : seuil stable du ratio 2 au ratio 50 | en place | 🟢 |
| R8 | **Changement de format** d'une source (FAA) | 2 | 2 | 🟠 4 | vérification stricte du schéma, échec explicite | en place | 🟢 |
| R9 | **Registre indisponible** : l'API ne démarre pas | 2 | 2 | 🟠 4 | sonde de vivacité ; en production, registre haute disponibilité | partiel | 🟠 |
| R10 | **Réidentification** via les immatriculations SDR | 1 | 3 | 🟠 3 | aucune jointure avec d'autres données ; pseudonymisation | prévu | 🟠 |
| R11 | **Absence de journal** des prédictions : décision non auditable | 2 | 2 | 🟠 4 | version renvoyée dans chaque réponse | partiel | 🟠 |
| R12 | **Accès non autorisé** au registre ou à l'API | 1 | 3 | 🟠 3 | liste blanche d'hôtes ; conteneur non-root | partiel | 🟠 — pas d'authentification |
| R13 | **Représentativité** : données publiques ≠ flotte SAFRAN | 3 | 2 | 🔴 6 | note de substitution ; limites déclarées | en place (documenté) | 🟠 — inhérent au projet |

**Lecture :** les risques techniques du modèle (R2, R3, R6) sont
maîtrisés. Les risques résiduels les plus élevés sont **organisationnels
et d'exploitation** — dérive rétrospective, emploi hors périmètre,
absence de journal, absence d'authentification. Ce sont les priorités
d'un passage en production.

---

## 7. Écarts connus et feuille de route

| écart | priorité |
|---|---|
| Journal des prédictions de l'API | haute |
| Authentification devant l'API et MLflow | haute |
| Indicateur de dérive avancé, sur les distributions d'entrée | haute |
| Pseudonymisation des immatriculations SDR | moyenne |
| Comptes de service distincts par pipeline sur MinIO | moyenne |
| Élargissement de l'apprentissage aux six conditions de FD004 | moyenne |
| PostgreSQL pour les métadonnées MLflow | basse |

## 8. Limites du projet

1. Les données C-MAPSS sont simulées et ne représentent pas une flotte
   réelle SAFRAN.

2. Les données FAA SDR sont externes au système industriel SAFRAN.

3. L'absence de données historiques de maintenance SAFRAN empêche de
   valider la performance sur une flotte réelle.

4. Les coûts utilisés pour optimiser le seuil sont des hypothèses de
   simulation.

5. La validation réglementaire présentée dans ce document constitue
   une analyse de cadrage et non une qualification réglementaire
   industrielle.