# Registre des activités de traitement — article 30 du RGPD

**Plateforme de maintenance prédictive · version 1.0 · 26 septembre 2026**

## Responsable et champ d'application

| rubrique | contenu |
|---|---|
| Responsable de traitement | l'exploitant de la plateforme — dans le cadre du projet : SODJI Rodney, porteur du projet de certification |
| Délégué à la protection des données | à désigner en exploitation réelle |
| Application territoriale | le RGPD s'applique aux traitements réalisés dans le cadre d'un établissement situé dans l'Union, **quelle que soit la nationalité des personnes concernées** (art. 3.1). Les propriétaires d'aéronefs américains cités dans les SDR sont donc couverts. |

*Les qualifications juridiques de ce registre sont à valider par le DPO.*

---

## Sources sans données personnelles

Ces sources restent hors du registre. On consigne pourquoi, car
l'absence de données personnelles est une conclusion, pas une
évidence.

| source | motif |
|---|---|
| NASA C-MAPSS | simulation de moteurs, aucune personne derrière les unités |
| Open-Meteo | observations météorologiques rattachées à des aéroports |
| Calendrier de vols (`src/fleet`) | immatriculations **générées**, ne désignant aucun appareil réel |

---

## T1 — Analyse des rapports de difficultés en service (SDR FAA)

| rubrique (art. 30.1) | contenu |
|---|---|
| **Finalité** | analyser les défaillances déclarées sur flotte réelle, pour documenter l'historique de maintenance et les rapports techniques en texte libre. **Aucune finalité de ciblage ni d'évaluation de personnes.** |
| **Base légale** (art. 6) | intérêt légitime — amélioration de la sécurité et de la maintenance aéronautique (art. 6.1.f). Mise en balance : données publiques, indirectes, sans conséquence pour les personnes. |
| **Personnes concernées** | propriétaires d'aéronefs lorsqu'il s'agit de **personnes physiques** ; personnes éventuellement nommées dans le texte libre |
| **Catégories de données** | immatriculation de l'aéronef — identifiante **indirectement**, via le registre public de la FAA · texte libre `Discrepancy`, susceptible de contenir des noms. Aucune donnée sensible au sens de l'article 9. |
| **Source** | données publiques de la FAA, non collectées auprès des personnes |
| **Destinataires** | data engineer et ML engineer de la plateforme. Aucune communication à un tiers. |
| **Transferts hors UE** | aucun — le lac est hébergé localement (MinIO). Récupérer une donnée publique américaine ne constitue pas un transfert. |
| **Durée de conservation** | bronze : **3 ans après l'ingestion du millésime**, puis purge — *proposée, à valider* · silver : pseudonymisé, aligné sur le bronze |
| **Mesures de sécurité** (art. 32) | voir plan de gouvernance §4 · accès au bronze limité au data engineer · pseudonymisation au passage en silver |

### Mesures propres à ce traitement

| mesure | statut |
|---|---|
| **Minimisation** : les SDR ne sont jamais joints aux données capteurs ; aucune donnée personnelle n'alimente le modèle | en place |
| **Pseudonymisation** des immatriculations au passage en silver, par **HMAC-SHA256 avec clé secrète** stockée hors du lac | prévu |
| Purge du bronze à l'échéance de conservation | prévu |

**Pourquoi une clé secrète, et pas un simple hachage.** Il existe
environ 300 000 immatriculations américaines. Un hachage non salé se
casse en quelques secondes : on hache tout le registre public et on
compare. Seul un hachage à clé (HMAC), dont la clé n'est jamais
stockée avec les données, résiste à cette attaque.

**Une donnée pseudonymisée reste une donnée personnelle** (considérant
26) : le traitement reste au registre après pseudonymisation.

### Information des personnes (art. 14)

Les données n'ont pas été collectées auprès des personnes. L'article 14
impose en principe de les informer. **L'exception de l'article 14.5.b**
— information impossible ou exigeant des efforts disproportionnés —
est invoquée : les propriétaires ne sont connus qu'à travers un
registre étranger, et les contacter serait disproportionné au regard
d'un traitement sans effet sur eux. *À valider par le DPO.*

### Tension d'architecture, arbitrée

Le bronze ne se nettoie jamais (ADR 0002), pour rester rejouable. La
minimisation demande au contraire de ne pas conserver les
immatriculations en clair.

**Arbitrage :** le bronze garde la donnée brute, mais pour une **durée
limitée** et avec un **accès restreint** au seul data engineer. La
pseudonymisation s'applique en silver, couche consultée par les autres
rôles. La rejouabilité est préservée pendant la durée de conservation ;
au-delà, elle cède devant la minimisation.

---

## T2 — Traçabilité des expérimentations et des accès

| rubrique (art. 30.1) | contenu |
|---|---|
| **Finalité** | tracer qui a entraîné, évalué et promu chaque modèle — condition de l'auditabilité des décisions (ADR 0004 MLOps) |
| **Base légale** | intérêt légitime — traçabilité d'un système d'aide à la décision en maintenance |
| **Personnes concernées** | personnels de la plateforme : data engineer, ML engineer, responsable maintenance |
| **Catégories de données** | nom d'utilisateur système, **enregistré automatiquement par MLflow** dans le tag `mlflow.user` de chaque run · identifiant de compte MinIO · horodatages |
| **Destinataires** | équipe de la plateforme, auditeurs |
| **Transferts hors UE** | aucun |
| **Durée de conservation** | celle du registre de modèles : les runs forment la piste d'audit des promotions |
| **Mesures de sécurité** | registre accessible aux seuls hôtes listés · base SQLite locale · authentification prévue (plan de gouvernance §4) |

*Ce traitement n'a pas été conçu : il a été découvert en inventoriant
les données personnelles. MLflow renseigne `mlflow.user` sans
instruction explicite. C'est précisément la fonction d'un registre.*

---

## T3 — Journal des prédictions *(prévu)*

Le plan de gouvernance prévoit de journaliser chaque prédiction de
l'API (§5.2). Ce journal contiendra un identifiant de moteur et
d'aéronef.

Pour une flotte de compagnie, l'aéronef appartient à une personne
morale : **pas de donnée personnelle a priori**. Le traitement sera
inscrit au registre si le journal venait à enregistrer l'identité de
l'utilisateur qui consulte l'alerte.

---

## Analyse d'impact (art. 35)

**Non requise a priori.** Aucun des critères usuels n'est réuni : pas
de données sensibles, pas de profilage ni d'évaluation de personnes,
pas de décision produisant des effets sur une personne, pas de
surveillance systématique. Les décisions de la plateforme portent sur
des moteurs, pas sur des individus. *Conclusion à confirmer par le DPO.*

---

## Exercice des droits

Les demandes (accès, rectification, effacement, opposition) sont
instruites par le data engineer, sous la responsabilité du DPO — voir
le RACI du plan de gouvernance. Pour T1, l'effacement porte sur le
bronze et le silver ; la pseudonymisation par HMAC permet de retrouver
les lignes d'une immatriculation donnée sans la stocker en clair.