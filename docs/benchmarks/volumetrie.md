# Volumétrie du data lake — mesures

**Script :** `benchmarks/volumetrie.py` · **Date :** 12 septembre 2026
**Machine :** MacBook Pro, disque local SSD

---

## Protocole

Le bronze `engine_sensors` est répliqué à deux échelles, ×1 et ×10, puis quatre grandeurs sont mesurées à chacune : taille sur disque, temps de scan complet, temps de lecture d'un seul mois, temps de lecture de 4 colonnes sur 41.

Chaque temps est la **médiane de 5 répétitions**, après un premier passage jeté. La médiane plutôt que la moyenne : une seule pause du ramasse-miettes suffirait à décaler une moyenne.

La réplication attribue de **nouveaux identifiants de moteurs** à chaque copie. Sans cette précaution, Parquet ne stockerait qu'une fois chaque valeur distincte et le taux de compression serait environ six fois trop favorable. Le contrôle est visible dans les résultats : **84 octets par ligne à ×1 comme à ×10**.

Un contrôle automatique vérifie que le filtre de partition a réellement élagué, plutôt que de le supposer : un filtre mal formé lirait tout le dataset avant de filtrer en mémoire, produisant un temps honorable et une conclusion fausse.

---

## Résultats

| échelle | lignes | taille | o/ligne | scan complet | un mois | 4 colonnes |
|---|---|---|---|---|---|---|
| ×1 | 265 256 | 22,2 Mo | 84 | 56 ms | 4 ms | 12 ms |
| ×10 | 2 652 560 | 221,7 Mo | 84 | 573 ms | 26 ms | 112 ms |

**Gain des requêtes ciblées** (scan ÷ requête) :

| échelle | un mois | 4 colonnes |
|---|---|---|
| ×1 | 13,8× | 4,7× |
| ×10 | **21,9×** | 5,1× |

**Parquet contre CSV**, même contenu, 41 colonnes :

| format | taille |
|---|---|
| CSV | 81,6 Mo |
| Parquet (snappy) | 9,6 Mo |
| | **÷ 8,5** |

---

## Conclusions

**Le partitionnement gagne en efficacité avec le volume.** Le rapport entre scan complet et lecture d'un mois passe de 13,8× à 21,9× quand le volume est multiplié par dix. Plus le lac grossit, plus il est rentable de ne lire qu'une partition.

Le chiffre le plus parlant : **lire un mois dans le lac dix fois plus gros coûte 26 ms, soit deux fois moins que scanner entièrement le lac initial (56 ms)**. La taille totale de l'entrepôt n'a pas d'incidence sur une requête ciblée.

**Le scan complet reste linéaire** — ×10,2 pour ×10 de données. Attendu : sans filtre, tout doit être lu. Cela confirme que le gain observé sur la lecture d'un mois vient bien du partitionnement, et non d'un artefact de mesure.

**Le format colonnaire rend un facteur constant d'environ 5.** Lire 4 colonnes sur 41 — soit 10 % des colonnes — ne divise pas le temps par 10 mais par 5. L'écart s'explique par le coût fixe d'ouverture des fichiers et de lecture des métadonnées, qui ne dépend pas du nombre de colonnes demandées.

**Parquet divise le volume stocké par 8,5 face au CSV.** Cela répond directement à la contrainte de maîtrise budgétaire du cahier des charges : à volume de données constant, la facture de stockage est divisée d'autant.

---

## Extrapolation à la flotte cible

15 000 moteurs × 800 vols par an = **12 millions de vols annuels**.

| granularité | volume annuel |
|---|---|
| 1 ligne par vol, 21 capteurs *(schéma mesuré)* | 1 Go |
| 1 ligne par vol, 250 capteurs | 12 Go |
| enregistrement continu 1 Hz sur 2 h de vol | **86 To** |

**Cette table explique l'écart apparent avec le document de présentation**, qui annonce « plusieurs téraoctets par an ».

Cette volumétrie correspond à un **enregistrement continu des capteurs en vol** : 7 200 points par vol pour deux heures à 1 Hz. C-MAPSS ne fournit qu'un **point agrégé par vol**, ce qui ramène le même périmètre à 12 Go annuels.

Les deux chiffres sont cohérents une fois la granularité explicitée. L'architecture est dimensionnée et mesurée sur la granularité post-vol agrégée ; le passage à la pleine cadence multiplierait le volume par environ 7 200 sans changer la structure — le partitionnement mensuel resterait valide, le nombre de fichiers par partition augmentant.

---

## Limites assumées

**Les lectures sont chaudes.** Le système d'exploitation conserve les fichiers en cache entre les répétitions. Ces mesures comparent donc des formats et des stratégies d'accès entre eux ; elles ne prédisent pas une latence de production sur stockage objet distant.

**Les mesures sont faites sur disque local**, alors que le lac de production est sur MinIO. Le comportement sur stockage objet diffère : le nombre de requêtes réseau y pèse davantage que le nombre d'octets lus. Une mesure sur MinIO est identifiée comme prolongement.

**L'échelle ×10 est obtenue par réplication**, non par simulation de nouveaux moteurs dégradés. La distribution statistique des capteurs est donc identique d'une copie à l'autre. Cela n'affecte pas les mesures de volumétrie et de temps d'accès, qui sont l'objet de ce benchmark.

**L'extrapolation suppose un coût par ligne constant** à 250 capteurs comme à 21. En pratique, la compression Parquet s'améliore avec le nombre de colonnes corrélées : l'estimation de 86 To est donc majorante.
