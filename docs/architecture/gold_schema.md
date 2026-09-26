# Couche gold — spécification

**Statut : spécifiée, non implémentée** (ADR 0002).

Schéma en **constellation** : deux tables de faits partagent les
dimensions date et aéroport.

```mermaid
erDiagram
    DIM_MOTEUR   ||--o{ FAIT_VOL   : "motorise"
    DIM_AVION    ||--o{ FAIT_VOL   : "effectue"
    DIM_DATE     ||--o{ FAIT_VOL   : "date"
    DIM_AEROPORT ||--o{ FAIT_VOL   : "origine"
    DIM_AEROPORT ||--o{ FAIT_VOL   : "destination"
    DIM_DATE     ||--o{ FAIT_METEO : "date"
    DIM_AEROPORT ||--o{ FAIT_METEO : "observe"

    FAIT_VOL {
        bigint vol_sk PK
        int moteur_sk FK
        int avion_sk FK
        int date_sk FK
        int origine_sk FK
        int destination_sk FK
        int time_in_cycles "numéro du vol dans la vie du moteur"
        float rul_reel "plafonné à 125"
        float rul_predit
        boolean alerte
        string version_modele "traçabilité de la prédiction"
    }
    FAIT_METEO {
        int aeroport_sk FK
        int date_sk FK
        float temp_max
        float temp_min
        float precipitations
        float vent_max
    }
    DIM_MOTEUR {
        int moteur_sk PK
        string engine_id "clé naturelle"
        string fd_subset "flotte d'origine"
        date mise_en_service
    }
    DIM_AVION {
        int avion_sk PK
        string tail_number "généré"
        string base
    }
    DIM_DATE {
        int date_sk PK
        date jour
        int annee
        int mois
        int jour_semaine
    }
    DIM_AEROPORT {
        int aeroport_sk PK
        string code_oaci
        float latitude
        float longitude
    }
```

## Choix de modélisation

| choix | justification |
|---|---|
| **Grain de `FAIT_VOL` : un vol d'un moteur** | c'est le grain natif de C-MAPSS — un point agrégé par vol |
| **Clés de substitution** (`_sk`) | isolent le gold des identifiants sources, qui peuvent changer |
| **Aéroport en double rôle** : origine et destination | une seule dimension, deux relations — évite de dupliquer la table |
| **`FAIT_METEO` séparé**, au grain aéroport × jour | la météo n'a pas le grain du vol ; la fusionner dupliquerait chaque observation sur tous les vols du jour |
| **`version_modele` dans le fait** | répond à l'exigence de journalisation : retrouver quel modèle a prédit quoi (conformité, art. 12) |
| **Les SDR sont absents** | aucune clé commune avec la flotte simulée ; les rattacher serait inventer une jointure (README) |

## Questions auxquelles le gold répondrait

- Combien d'alertes par aéroport de base et par mois ?
- Les alertes sont-elles plus fréquentes après des journées de fortes
  précipitations ? *(sur données réelles uniquement — voir note de
  substitution)*
- Quelle version du modèle a émis chaque alerte d'un trimestre ?