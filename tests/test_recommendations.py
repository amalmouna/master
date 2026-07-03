"""Étape 9 — contrainte critique : aucune recommandation ne doit jamais porter
sur une matière que l'élève ne suit pas. Un élève de 1APIC sans curriculum
scientifique (moyenne_scientifique = NaN) ne doit recevoir aucune recommandation
de type soutien_scientifique, ni aucune matière scientifique dans
matieres_concernees, quels que soient ses autres résultats."""
import numpy as np
import pandas as pd
import pytest

from recommendation.rules import DOMAINS, MATIERES_FR, generate_recommendations

ALL_MATIERES = list(MATIERES_FR.keys())
SCIENCE_MATIERES = set(DOMAINS["scientifique"])


def _base_row(**overrides) -> pd.Series:
    """Élève par défaut : toutes matières suivies, moyennes confortables, non à risque."""
    base = {
        "moyenne_scientifique": 15.0,
        "moyenne_linguistique": 15.0,
        "moyenne_sciences_humaines": 15.0,
        "moyenne_generale": 15.0,
        "dispersion_intermatiere": 1.0,
        "matiere_min": 14.0,
        "matiere_min_nom": "MATHEMATIQUES",
        "tendance_globale": 0.0,
        "a_risque": 0,
        "nb_matieres_sous_10": 0,
    }
    for m in ALL_MATIERES:
        base[f"moy_{m}"] = 15.0
    base.update(overrides)
    return pd.Series(base)


def test_no_science_recommendation_for_student_without_science_curriculum():
    """Cas central : élève de 1APIC sans Maths/PC/SVT (moyenne_scientifique NaN,
    et les moy_<matiere> scientifiques également NaN), mais faible en langues."""
    overrides = {
        "moyenne_scientifique": np.nan,
        "moyenne_linguistique": 6.0,
        "matiere_min": 6.0,
        "matiere_min_nom": "LANGUE FRANCAISE",
        "dispersion_intermatiere": 5.0,
        "a_risque": 1,
        "nb_matieres_sous_10": 2,
    }
    for m in SCIENCE_MATIERES:
        overrides[f"moy_{m}"] = np.nan
    for m in DOMAINS["linguistique"]:
        overrides[f"moy_{m}"] = 6.0
    row = _base_row(**overrides)

    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})

    assert not any(r["type"] == "soutien_scientifique" for r in recs), (
        "recommandation scientifique générée pour un élève sans curriculum scientifique"
    )
    for r in recs:
        for matiere in r["matieres_concernees"]:
            assert matiere not in SCIENCE_MATIERES, (
                f"matière scientifique '{matiere}' citée alors que l'élève ne suit aucune science"
            )


def test_matieres_concernees_never_references_unfollowed_subject():
    """Vérification générale, tous domaines : matieres_concernees ne doit contenir
    que des matières où moy_<matiere> est renseigné (notna) pour cet élève."""
    overrides = {
        "moyenne_scientifique": np.nan,
        "moyenne_sciences_humaines": 5.0,
        "matiere_min": 5.0,
        "matiere_min_nom": "HISTOIRE GEOGRAPHIE",
        "dispersion_intermatiere": 5.0,
        "a_risque": 1,
        "nb_matieres_sous_10": 3,
    }
    for m in SCIENCE_MATIERES:
        overrides[f"moy_{m}"] = np.nan
    overrides["moy_HISTOIRE GEOGRAPHIE"] = 5.0
    row = _base_row(**overrides)

    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})

    followed_matieres = {m for m in ALL_MATIERES if pd.notna(row.get(f"moy_{m}"))}
    for r in recs:
        for matiere in r["matieres_concernees"]:
            assert matiere in followed_matieres, (
                f"matière '{matiere}' recommandée mais absente du profil de l'élève (non suivie)"
            )


def test_domain_rule_does_not_fire_when_domain_average_is_nan():
    """Même si une matière individuelle du domaine avait par erreur une valeur,
    le domaine entier doit être NaN pour un élève qui ne le suit pas du tout —
    la règle est gardée sur la moyenne de domaine, pas sur les matières individuelles."""
    row = _base_row(moyenne_scientifique=np.nan)
    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})
    assert not any(r["type"] == "soutien_scientifique" for r in recs)


def test_domain_rule_fires_only_for_subjects_actually_weak_and_followed():
    """Élève suivant PC et Maths (pas SVT dans ce cas), PC faible, Maths correct :
    matieres_concernees ne doit contenir que Physique-Chimie."""
    row = _base_row(
        moyenne_scientifique=9.0,
        **{
            "moy_PHYSIQUE CHIMIE": 6.0,
            "moy_MATHEMATIQUES": 12.0,
            "moy_SC. DE LA VIE ET DE LA TERRE": np.nan,
        },
    )
    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})
    sci_recs = [r for r in recs if r["type"] == "soutien_scientifique"]
    assert len(sci_recs) == 1
    assert sci_recs[0]["matieres_concernees"] == ["PHYSIQUE CHIMIE"]


def test_no_recommendation_at_all_for_a_strong_student():
    row = _base_row()
    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})
    assert recs == []


def test_plan_prioritaire_only_fires_when_at_risk_and_multiple_weak_subjects():
    row = _base_row(a_risque=0, nb_matieres_sous_10=5)
    recs = generate_recommendations(row, dispersion_seuil=3.0, trends={})
    assert not any(r["type"] == "plan_remediation_prioritaire" for r in recs)

    row2 = _base_row(a_risque=1, nb_matieres_sous_10=3, moyenne_generale=8.0)
    for m in ALL_MATIERES[:3]:
        row2[f"moy_{m}"] = 7.0
    recs2 = generate_recommendations(row2, dispersion_seuil=3.0, trends={})
    plan = [r for r in recs2 if r["type"] == "plan_remediation_prioritaire"]
    assert len(plan) == 1
    assert plan[0]["priorite"] == 1
