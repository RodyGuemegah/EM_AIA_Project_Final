import pandas as pd
import pytest

from src.models.dataset import split_par_moteur


@pytest.fixture
def faux_moteurs():
    """10 moteurs, 5 cycles chacun — 50 lignes au total."""
    return pd.DataFrame({
        "engine_id": [m for m in range(1, 11) for _ in range(5)],
        "valeur": range(50),
    })

def test_aucun_moteur_deux_cotes(faux_moteurs):

    train, test = split_par_moteur(faux_moteurs, test_size=0.2, seed=42)

    moteurs_train = set(train["engine_id"])
    moteurs_test = set(test["engine_id"])

    assert moteurs_train.isdisjoint(moteurs_test)

def test_aucune_ligne_perdue(faux_moteurs):
    train, test = split_par_moteur(faux_moteurs, test_size=0.2, seed=42)
    assert len(train) + len(test) == len(faux_moteurs)

def test_reproductible(faux_moteurs):

    train1, test1 = split_par_moteur(faux_moteurs, test_size=0.2, seed=42)
    train2, test2 = split_par_moteur(faux_moteurs, test_size=0.2, seed=42)

    assert train1.equals(train2)
    assert test1.equals(test2)

def test_taille_correcte(faux_moteurs):

    train, test = split_par_moteur(faux_moteurs, test_size=0.2, seed=42)
    assert len(test) == len(faux_moteurs) * 0.2  # 20% de 50 lignes = 10 lignes
    assert len(train) == len(faux_moteurs) * 0.8  # 80% de 50 lignes = 40 lignes