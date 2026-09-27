"""Modèle témoin — régression linéaire sur les capteurs bruts.

Ce n'est PAS le modèle final. C'est le point de comparaison : si XGBoost
ne bat pas ces chiffres la semaine prochaine, il ne sert à rien.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.cmapss import SENSORS, constant_sensors
from src.models.dataset import load_bronze, split_par_moteur

RUL_CAP = 125
SEED = 42
MODEL_PATH = Path("models/baseline.joblib")


def preparer_donnees(subset="FD001"):
    """Charge, sépare par moteur, plafonne le RUL."""
    df = load_bronze(subset=subset, split="train")
    train, test = split_par_moteur(df, test_size=0.2, seed=SEED)

    # Le plafond est un choix de modélisation : il se prend ici, pas au stockage.
    train = train.assign(rul=train.rul.clip(upper=RUL_CAP))
    test = test.assign(rul=test.rul.clip(upper=RUL_CAP))
    return train, test


def choisir_features(train):
    """Capteurs utiles, calculés sur l'APPRENTISSAGE seul.

    Passer le DataFrame complet ferait entrer une information des moteurs
    d'examen dans la sélection : c'est une fuite, même minuscule.
    """
    plats = constant_sensors(train)
    return [s for s in SENSORS if s not in plats]


def entrainer():
    train, test = preparer_donnees()
    features = choisir_features(train)

    # X = ce que le modèle regarde (un DataFrame de 14 colonnes)
    # y = ce qu'il doit deviner (une seule colonne)
    X_train, y_train = train[features], train["rul"]
    X_test, y_test = test[features], test["rul"]

    # L'apprentissage tient en une ligne : il cherche les 14 coefficients
    # qui minimisent l'écart entre prédiction et réalité.
    model = LinearRegression()
    model.fit(X_train, y_train)

    # On évalue sur les 20 moteurs jamais vus.
    pred = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
    mae = float(mean_absolute_error(y_test, pred))

    print(f"Features        : {len(features)} capteurs sur 21")
    print(f"Apprentissage   : {train.engine_id.nunique()} moteurs, {len(train):,} vols")
    print(f"Examen          : {test.engine_id.nunique()} moteurs, {len(test):,} vols")
    print(f"\nRMSE            : {rmse:.2f} cycles")
    print(f"MAE             : {mae:.2f} cycles")

    # On sauvegarde le modèle ET tout ce qu'il faut pour le rejouer.
    # Sans la liste des features, l'API ne saurait pas quelles colonnes
    # envoyer ni dans quel ordre — et scikit-learn ne préviendrait pas.
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": features,
            "rul_cap": RUL_CAP,
            "seed": SEED,
            "rmse": rmse,
            "mae": mae,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        },
        MODEL_PATH,
    )
    print(f"\nModèle sauvegardé : {MODEL_PATH}")
    return rmse


if __name__ == "__main__":
    entrainer()