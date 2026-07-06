"""Étape C — la pseudonymisation ne doit laisser aucune PII résiduelle."""
from datetime import date

import pandas as pd
import pytest

from anonymization.anonymize import (
    anonymize_dataframe,
    assert_no_pii,
    build_identity_mapping,
    dob_to_age,
    age_to_band,
    pseudonymize_code,
)

REFERENCE_DATE = date(2025, 9, 1)


def _raw_long_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id_interne": 13532978,
                "student_code": "F182055553",
                "nom_complet": "الشافعي أيمن",
                "dob_raw": "05-10-2012",
                "niveau": "1APIC",
                "classe": "1APIC-1",
                "matiere": "MATHEMATIQUES",
                "c1": 12.0,
                "c2": 14.0,
                "c3": None,
                "c4": None,
                "activites": None,
                "remarque": "Bon travail, peut s'améliorer",
                "source_file": "Export_28847E_1APIC-1_MATHEMATIQUES_x.xlsx",
            },
            {
                "id_interne": 13548608,
                "student_code": "F182057176",
                "nom_complet": "عرنوسي أميمة",
                "dob_raw": "04-11-2012",
                "niveau": "1APIC",
                "classe": "1APIC-1",
                "matiere": "MATHEMATIQUES",
                "c1": 6.0,
                "c2": 4.0,
                "c3": None,
                "c4": None,
                "activites": None,
                "remarque": "Travail faible, fais attention",
                "source_file": "Export_28847E_1APIC-1_MATHEMATIQUES_x.xlsx",
            },
        ]
    )


def test_anonymize_dataframe_drops_all_pii_columns(local_tmp_path):
    df = _raw_long_df()
    salt_file = str(local_tmp_path / ".salt")
    out = anonymize_dataframe(df, REFERENCE_DATE, salt_file=salt_file)

    for col in ("id_interne", "student_code", "nom_complet", "dob_raw", "age"):
        assert col not in out.columns, f"colonne PII résiduelle : {col}"

    assert_no_pii(out)  # ne doit pas lever


def test_anonymize_dataframe_no_pii_values_leaked_via_other_columns(local_tmp_path):
    """Aucune valeur nominative brute (nom, code élève, id interne) ne doit
    apparaître ailleurs dans la table de sortie (ex. recopiée dans une colonne
    texte par erreur)."""
    df = _raw_long_df()
    salt_file = str(local_tmp_path / ".salt")
    out = anonymize_dataframe(df, REFERENCE_DATE, salt_file=salt_file)

    pii_values = {"13532978", "13548608", "F182055553", "F182057176", "الشافعي أيمن", "عرنوسي أميمة"}
    for col in out.columns:
        col_as_str = out[col].astype(str)
        for pii in pii_values:
            assert not col_as_str.str.contains(pii, regex=False).any(), (
                f"valeur PII '{pii}' retrouvée dans la colonne '{col}'"
            )


def test_pseudonymize_code_is_deterministic_and_distinct():
    salt = b"fixed-test-salt"
    p1a = pseudonymize_code("F182055553", salt)
    p1b = pseudonymize_code("F182055553", salt)
    p2 = pseudonymize_code("F182057176", salt)
    assert p1a == p1b
    assert p1a != p2


def test_pseudonymize_code_differs_across_salts():
    p_salt1 = pseudonymize_code("F182055553", b"salt-one")
    p_salt2 = pseudonymize_code("F182055553", b"salt-two")
    assert p_salt1 != p_salt2


@pytest.mark.parametrize(
    "dob_str,expected_age",
    [
        ("01-09-2010", 15),  # anniversaire le jour même de la référence
        ("02-09-2010", 14),  # anniversaire le lendemain, pas encore fêté
        ("31-08-2010", 15),  # anniversaire la veille, déjà fêté
    ],
)
def test_dob_to_age_reference_september_first(dob_str, expected_age):
    assert dob_to_age(dob_str, REFERENCE_DATE) == expected_age


def test_age_to_band_boundaries():
    assert age_to_band(11) == "<=11"
    assert age_to_band(12) == "12"
    assert age_to_band(16) == ">=16"
    assert age_to_band(20) == ">=16"
    assert age_to_band(None) is None


def test_identity_mapping_contains_name_but_not_national_id(local_tmp_path):
    """La table d'identité (usage exclusif : loader Supabase authentifié) porte
    le nom réel, mais jamais le code national ni l'id interne Massar — le hash
    stable (student_pseudo) suffit à faire le lien avec le reste du pipeline."""
    df = _raw_long_df()
    salt_file = str(local_tmp_path / ".salt")
    mapping = build_identity_mapping(df, REFERENCE_DATE, salt_file=salt_file)

    assert set(mapping.columns) == {"student_pseudo", "nom_complet", "age", "niveau"}
    assert set(mapping["nom_complet"]) == {"الشافعي أيمن", "عرنوسي أميمة"}
    assert len(mapping) == 2  # une ligne par élève, dédupliquée


def test_identity_mapping_pseudo_matches_anonymize_dataframe(local_tmp_path):
    """Même sel, même élève -> même student_pseudo des deux côtés : la table
    d'identité doit pouvoir se joindre exactement sur la table longue
    pseudonymisée sans divergence de hash."""
    df = _raw_long_df()
    salt_file = str(local_tmp_path / ".salt")

    long_pseudo = anonymize_dataframe(df, REFERENCE_DATE, salt_file=salt_file)
    mapping = build_identity_mapping(df, REFERENCE_DATE, salt_file=salt_file)

    assert set(mapping["student_pseudo"]) == set(long_pseudo["student_pseudo"])
