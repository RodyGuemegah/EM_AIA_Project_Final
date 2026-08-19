"""Tests du loader C-MAPSS, sur données factices au bon format."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.cmapss import COLUMNS, constant_sensors, load_test, load_train


def _fake_cmapss(tmp_path, units=(1, 2, 3), lengths=(50, 80, 30), seed=0):
    """Génère un fichier au format C-MAPSS : 26 colonnes, séparateur espace."""
    rng = np.random.default_rng(seed)
    rows = []
    for u, n in zip(units, lengths, strict=True):
        for c in range(1, n + 1):
            sensors = rng.normal(size=21)
            sensors[0] = 518.67  # capteur constant, comme dans le vrai FD001
            rows.append([u, c, *rng.normal(size=3), *sensors])

    df = pd.DataFrame(rows, columns=COLUMNS)
    path = tmp_path / "train_FD001.txt"
    df.to_csv(path, sep=" ", header=False, index=False)
    return path


def test_charge_le_bon_nombre_de_colonnes(tmp_path):
    df = load_train(_fake_cmapss(tmp_path))
    assert list(df.columns) == [*COLUMNS, "rul"]


def test_rul_decroit_et_atteint_zero(tmp_path):
    df = load_train(_fake_cmapss(tmp_path), rul_cap=None)
    for _, g in df.groupby("unit_number"):
        g = g.sort_values("time_in_cycles")
        assert g.rul.iloc[-1] == 0, "le dernier cycle doit avoir un RUL nul"
        assert g.rul.is_monotonic_decreasing, "le RUL doit décroître"


def test_plafond_rul_applique(tmp_path):
    df = load_train(_fake_cmapss(tmp_path), rul_cap=30)
    assert df.rul.max() == 30


def test_detection_capteur_constant(tmp_path):
    df = load_train(_fake_cmapss(tmp_path))
    assert "sensor_01" in constant_sensors(df)


def test_erreur_si_mauvais_nombre_de_colonnes(tmp_path):
    path = tmp_path / "casse.txt"
    path.write_text("1 2 3\n4 5 6\n")
    with pytest.raises(ValueError, match="colonnes"):
        load_train(path)


def test_load_test_ajoute_le_rul_final(tmp_path):
    path = _fake_cmapss(tmp_path, units=(1, 2), lengths=(10, 20))
    rul_path = tmp_path / "RUL_FD001.txt"
    rul_path.write_text("40\n15\n")

    df = load_test(path, rul_path, rul_cap=None)

    # Moteur 1 : 40 au dernier cycle, donc 40 + 9 au premier
    u1 = df[df.unit_number == 1].sort_values("time_in_cycles")
    assert u1.rul.iloc[-1] == 40
    assert u1.rul.iloc[0] == 49
