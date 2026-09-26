# Analyse de conformité — AI Act

**Plateforme de maintenance prédictive · version 1.0 · 26 septembre 2026**

> Ce document présente un raisonnement de qualification, pas un avis
> juridique. Chaque conclusion s'appuie sur le texte cité et doit être
> validée par un juriste avant toute mise en exploitation. Textes
> consultés dans leur état au 26 septembre 2026, **après l'entrée en
> vigueur du Digital Omnibus sur l'IA** (règlement (UE) 2026/1744,
> en vigueur depuis le 27 juillet 2026).

---

## 1. Le système

| rubrique | description |
|---|---|
| **Fonction** | estimer la durée de vie résiduelle d'un moteur, en nombre de vols, à partir de ses données capteurs |
| **Sortie** | un RUL estimé, une alerte si le RUL passe sous le seuil de 14 vols, et les trois capteurs qui expliquent le plus la prédiction |
| **Utilisateurs** | personnel de maintenance au sol |
| **Décision** | **humaine.** L'alerte déclenche un examen par un technicien, pas une dépose automatique. |
| **Environnement** | au sol. Aucune fonction embarquée, aucune action sur l'aéronef. |

---

## 2. Qualification

### 2.1 Est-ce un système d'IA ? — **Oui**

Le modèle XGBoost infère, à partir des données qu'il reçoit, des
prédictions qui influencent une décision (art. 3.1). Le règlement
s'applique.

### 2.2 Pratique interdite ? — **Non**

Aucune des pratiques de l'article 5 n'est concernée : pas de
manipulation, pas de notation sociale, pas de biométrie, pas de
reconnaissance des émotions. Le système traite des moteurs, pas des
personnes.

### 2.3 Haut risque par l'annexe III ? — **Non**

L'annexe III énumère des **domaines d'usage** : biométrie,
infrastructures critiques, éducation, emploi, services essentiels,
répression, migration, justice. La maintenance aéronautique n'y figure
pas.

### 2.4 Haut risque par l'annexe I ? — **Non**

L'article 6.1 qualifie de haut risque un système d'IA qui est
**composant de sécurité** d'un produit couvert par la législation
d'harmonisation de l'annexe I, **et** soumis à une évaluation de
conformité par un tiers.

Le règlement (UE) 2018/1139 — règlement de base de l'EASA — figure bien
à l'annexe I, section B, point 20. Mais **avec une restriction de
portée** : il n'est visé qu'en tant qu'il concerne la conception, la
production et la mise sur le marché des **aéronefs sans équipage à
bord**, de leurs moteurs, hélices, pièces et équipements de commande à
distance.

Un moteur de ligne sur aéronef habité n'entre pas dans ce périmètre.

**Second motif, indépendant du premier :** le système n'est pas un
composant de sécurité. C'est un outil d'aide à la planification, au
sol, dont la sortie est examinée par un technicien avant toute
décision. Sa défaillance retarde ou avance une dépose ; elle n'agit
pas sur le vol.

### 2.5 Obligations de transparence de l'article 50 ? — **Non applicables**

Elles visent les systèmes qui dialoguent avec des personnes, génèrent
du contenu, ou reconnaissent des émotions. Aucun cas ici.

### 2.6 Conclusion

> **Le système ne relève pas de la catégorie haut risque.** La seule
> obligation directement applicable est l'**article 4**, maîtrise de
> l'IA, qui vaut pour tous les fournisseurs et déployeurs. Depuis le
> Digital Omnibus, c'est une obligation de moyens : prendre des mesures
> pour soutenir la maîtrise de l'IA du personnel, sans garantir un
> niveau donné.

**Calendrier, pour mémoire.** Même si la qualification évoluait — par
exemple si le système devenait embarqué — les obligations de haut
risque pour les produits de l'annexe I ne s'appliqueraient qu'à partir
du **2 août 2028**, date fixée par le Digital Omnibus.

---

## 3. La voie sectorielle : l'EASA

La qualification au titre de l'AI Act ne clôt pas la question. En
aviation, le régulateur de référence est l'EASA.

Sa **NPA 2025-07** propose des spécifications détaillées sur la
fiabilité de l'IA (tâche réglementaire RMT.0742). Elle distingue :

- le **niveau 1** — l'IA **assiste** l'humain ;
- le **niveau 2** — l'humain et l'IA travaillent **en équipe**.

**Ce système relève du niveau 1** : il éclaire une décision que
l'humain prend seul.

Une seconde NPA est annoncée pour 2026, pour décliner ce cadre générique
dans les réglementations de chaque domaine. **C'est elle qui fixera les
exigences applicables à la maintenance** : à suivre avant toute mise en
exploitation.

---

## 4. Alignement volontaire

Le système n'est pas à haut risque. Il applique pourtant les exigences
du chapitre III, section 2 — pour trois raisons :

1. elles répondent aux risques identifiés dans la matrice des risques ;
2. la NPA de l'EASA les reprend comme base de la fiabilité de l'IA ;
3. un système conçu ainsi n'a rien à refaire si sa qualification
   change.

| article | exigence | mise en œuvre | statut |
|---|---|---|---|
| **9** | gestion des risques | matrice des risques, plan de gouvernance §6 | en place |
| **10** | données et gouvernance des données | lignage, anti-fuite vérifié en CI, limites de représentativité déclarées dans la note de substitution | en place |
| **11** | documentation technique | 13 ADR, README, note de substitution, benchmarks | en place |
| **12** | journalisation | version du modèle renvoyée dans chaque réponse ; runs MLflow conservés ; **pas de journal des prédictions** | partiel |
| **13** | transparence envers les utilisateurs | trois causes SHAP par prédiction ; périmètre d'emploi déclaré ; fiche modèle | partiel |
| **14** | contrôle humain | promotion manuelle (ADR 0004 MLOps) ; l'alerte déclenche un examen, jamais une dépose | en place |
| **15** | exactitude, robustesse, cybersécurité | performance déclarée en RMSE **et** en coût ; dérive mesurée sur trois flottes ; robustesse aux valeurs manquantes (ADR 0006 MLOps) ; authentification absente | partiel |

### Ce que la mise en conformité a révélé

**Article 15 — la robustesse a une limite mesurée.** Sur FD004, flotte
jamais vue, le modèle laisse passer 100 % des pannes. L'exigence de
robustesse se traduit donc par une **restriction d'emploi** : le
système n'est validé que sur les conditions de FD001 et FD003.

**Article 13 — l'explication existe, pas encore sa notice.** L'API
renvoie les causes de chaque alerte, mais aucun document n'explique à
un mécanicien comment les lire. C'est le chantier de l'article 4.

---

## 5. Article 4 — maîtrise de l'IA

Seule obligation directement applicable.

| mesure | objectif | statut |
|---|---|---|
| **Guide d'interprétation de l'alerte** : ce que signifie un RUL, pourquoi le seuil est à 14 vols, comment lire une contribution SHAP négative | éviter la surconfiance — risque R5 | prévu |
| Rappel du **périmètre d'emploi** dans chaque interface | éviter l'emploi hors périmètre — risque R4 | prévu |
| Présentation des **limites** : le modèle est optimiste près de la panne | faire comprendre pourquoi la marge existe | prévu |

*Obligation de moyens depuis le Digital Omnibus : il s'agit de
démontrer que ces mesures ont été prises, pas que chaque technicien a
atteint un niveau donné.*

---

## 6. Points à vérifier avant exploitation

- Relire le **texte consolidé** de l'AI Act après le règlement
  2026/1744 : articles 2, 4, 6 et 50, annexe I section B.
- Suivre la **seconde NPA de l'EASA** : elle peut créer des exigences
  propres à la maintenance.
- Faire valider la qualification par un juriste.

## Sources

- [AI Act — annexe I, AI Act Service Desk (Commission européenne)](https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-1)
- [EASA — NPA 2025-07, AI trustworthiness](https://www.easa.europa.eu/en/document-library/notices-of-proposed-amendment/npa-2025-07)
- [Entrée en vigueur du Digital Omnibus sur l'IA — White & Case](https://www.whitecase.com/insight-alert/eu-ai-omnibus-enters-force-amending-ai-act)
- [Article 4 réécrit par le Digital Omnibus — lawandtechnology.eu](https://lawandtechnology.eu/en/ai-literacy-digital-omnibus-article-4-ai-act/)