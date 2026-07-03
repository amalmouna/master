"""Étape F — la définition C de la cible « à risque » doit être appliquée
exactement telle que documentée : moyenne_generale < 10 OU proportion de
matières sous 10 >= seuil (défaut 0.5), jamais un compte brut."""
import pandas as pd
import pytest

from models.targets import PASSING_GRADE, PROPORTION_THRESHOLD, add_risk_label, risk_config


def _profile(**rows_kwargs) -> pd.DataFrame:
    return pd.DataFrame(rows_kwargs)


@pytest.mark.parametrize(
    "moyenne_generale,nb_sous_10,nb_suivies,expected",
    [
        (12.0, 0, 7, 0),   # bon profil, rien ne déclenche
        (9.9, 0, 7, 1),    # moyenne sous la barre -> à risque, peu importe la proportion
        (9.99, 0, 3, 1),   # idem, profil à 3 matières
        (10.0, 0, 7, 0),   # égal à la barre : PAS à risque (comparaison stricte <)
        (12.0, 4, 7, 1),   # bon average mais 4/7 = 57% sous 10 -> polarisé -> à risque
        (12.0, 3, 7, 0),   # 3/7 = 43% sous 10 -> sous le seuil -> pas à risque
        (12.0, 2, 4, 1),   # 2/4 = 50% pile -> déclenche (>=), profil partiel
        (12.0, 1, 4, 0),   # 1/4 = 25% -> pas à risque, profil partiel (pas de biais de compte brut)
        (12.0, 3, 3, 1),   # profil très partiel mais 100% sous 10 -> à risque
    ],
)
def test_definition_c_risk_rule(moyenne_generale, nb_sous_10, nb_suivies, expected):
    df = _profile(
        moyenne_generale=[moyenne_generale],
        nb_matieres_sous_10=[nb_sous_10],
        nb_matieres_suivies=[nb_suivies],
    )
    out = add_risk_label(df)
    assert int(out["a_risque"].iloc[0]) == expected


def test_definition_c_does_not_penalize_sparse_profile_with_raw_count():
    """La proportion, pas le compte brut, doit gouverner le volet polarisation :
    un élève à 3 matières ne peut jamais atteindre un compte brut de 3 matières
    sous 10 sans que ce soit déjà 100% de son profil (donc légitimement à risque),
    alors qu'un élève à 7 matières avec 3 sous 10 (43%) ne doit PAS être neutralisé
    par un seuil de compte brut historique (ex. >=3, cf. définition B rejetée)."""
    df = _profile(
        moyenne_generale=[12.0, 12.0],
        nb_matieres_sous_10=[2, 3],
        nb_matieres_suivies=[3, 7],
    )
    out = add_risk_label(df)
    # 2/3 = 67% -> à risque (profil partiel, mais légitimement polarisé)
    assert int(out["a_risque"].iloc[0]) == 1
    # 3/7 = 43% -> pas à risque (la définition B, avec seuil brut >=3, l'aurait marqué à risque à tort)
    assert int(out["a_risque"].iloc[1]) == 0


def test_custom_thresholds_are_respected():
    df = _profile(moyenne_generale=[11.0], nb_matieres_sous_10=[2], nb_matieres_suivies=[5])
    out_default = add_risk_label(df)
    assert int(out_default["a_risque"].iloc[0]) == 0  # 2/5=40% < 0.5, avg>=10

    out_lower_threshold = add_risk_label(df, proportion_threshold=0.3)
    assert int(out_lower_threshold["a_risque"].iloc[0]) == 1  # 40% >= 30%


def test_risk_config_documents_passing_grade_and_leakage_columns():
    cfg = risk_config()
    assert cfg["passing_grade"] == PASSING_GRADE == 10.0
    assert cfg["proportion_threshold"] == PROPORTION_THRESHOLD == 0.5
    for leaking_col in ("moyenne_generale", "dispersion_intermatiere", "remarque_encodee", "a_risque"):
        assert leaking_col in cfg["colonnes_fuite_exclues"]
