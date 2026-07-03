"""Étape D — moyenne_matiere ne doit moyenner que les composantes qui existent
réellement dans le fichier source (colonne présente ET valeur renseignée),
jamais un jeu fixe de composantes."""
import numpy as np
import pandas as pd
import pytest

from features.aggregate import compute_moyenne_matiere, compute_tendance_matiere


def _row(**overrides) -> pd.Series:
    base = {
        "c1": np.nan,
        "c2": np.nan,
        "c3": np.nan,
        "c4": np.nan,
        "activites": np.nan,
        "c1_colonne_existe": False,
        "c2_colonne_existe": False,
        "c3_colonne_existe": False,
        "c4_colonne_existe": False,
        "activites_colonne_existe": False,
    }
    base.update(overrides)
    return pd.Series(base)


def test_moyenne_uses_only_columns_that_exist_in_file():
    # Schéma à 3 colonnes (C1, C2, Activités) : C3/C4 n'existent pas dans ce fichier.
    row = _row(
        c1=12.0, c1_colonne_existe=True,
        c2=14.0, c2_colonne_existe=True,
        activites=16.0, activites_colonne_existe=True,
    )
    moyenne, n = compute_moyenne_matiere(row)
    assert n == 3
    assert moyenne == pytest.approx((12.0 + 14.0 + 16.0) / 3)


def test_moyenne_excludes_column_that_exists_but_is_empty():
    """Distinction clé : une colonne présente dans le schéma mais vide (élève pas
    encore noté) ne doit PAS être comptée comme une composante disponible."""
    row = _row(
        c1=10.0, c1_colonne_existe=True,
        c2=np.nan, c2_colonne_existe=True,  # colonne existe, valeur manquante
        c3=8.0, c3_colonne_existe=True,
    )
    moyenne, n = compute_moyenne_matiere(row)
    assert n == 2
    assert moyenne == pytest.approx((10.0 + 8.0) / 2)


def test_moyenne_never_uses_column_absent_from_file_even_if_value_present():
    """Garde-fou : si une valeur traîne dans une colonne marquée comme absente du
    fichier (ne devrait pas arriver après l'étape A, mais on le vérifie), elle ne
    doit pas être utilisée — la fuite structurelle serait pire que l'oubli."""
    row = _row(
        c1=12.0, c1_colonne_existe=True,
        c2=14.0, c2_colonne_existe=True,
        c4=20.0, c4_colonne_existe=False,  # valeur résiduelle, colonne absente du schéma
    )
    moyenne, n = compute_moyenne_matiere(row)
    assert n == 2
    assert moyenne == pytest.approx((12.0 + 14.0) / 2)


def test_moyenne_returns_nan_when_no_component_available():
    row = _row()
    moyenne, n = compute_moyenne_matiere(row)
    assert n == 0
    assert np.isnan(moyenne)


def test_moyenne_uses_all_five_components_when_all_exist_and_filled():
    row = _row(
        c1=10.0, c1_colonne_existe=True,
        c2=12.0, c2_colonne_existe=True,
        c3=14.0, c3_colonne_existe=True,
        c4=16.0, c4_colonne_existe=True,
        activites=18.0, activites_colonne_existe=True,
    )
    moyenne, n = compute_moyenne_matiere(row)
    assert n == 5
    assert moyenne == pytest.approx((10.0 + 12.0 + 14.0 + 16.0 + 18.0) / 5)


def test_tendance_none_when_fewer_than_three_sequential_points():
    row = _row(c1=10.0, c1_colonne_existe=True, c2=12.0, c2_colonne_existe=True)
    assert compute_tendance_matiere(row) is None


def test_tendance_ignores_activites_as_a_sequential_point():
    """Activités n'est pas un point chronologique comparable à C1..C4 : deux
    points de contrôle + Activités ne doivent PAS suffire à calculer une tendance."""
    row = _row(
        c1=10.0, c1_colonne_existe=True,
        c2=12.0, c2_colonne_existe=True,
        activites=18.0, activites_colonne_existe=True,
    )
    assert compute_tendance_matiere(row) is None


def test_tendance_computed_with_three_sequential_points():
    row = _row(
        c1=8.0, c1_colonne_existe=True,
        c2=10.0, c2_colonne_existe=True,
        c3=12.0, c3_colonne_existe=True,
    )
    slope = compute_tendance_matiere(row)
    assert slope == pytest.approx(2.0)


def test_tendance_uses_c4_when_available_and_ignores_gap_correctly():
    # C1, C2, C4 présents mais pas C3 : positions 1,2,4 (pas 1,2,3) pour la régression.
    row = _row(
        c1=8.0, c1_colonne_existe=True,
        c2=10.0, c2_colonne_existe=True,
        c4=16.0, c4_colonne_existe=True,
    )
    slope = compute_tendance_matiere(row)
    # points (1,8), (2,10), (4,16) -> régression linéaire
    x = np.array([1.0, 2.0, 4.0])
    y = np.array([8.0, 10.0, 16.0])
    expected = np.polyfit(x, y, 1)[0]
    assert slope == pytest.approx(expected)
