"""Import additif : ajoute un ou plusieurs fichiers matière à une année
scolaire déjà partiellement importée, sans réentraîner et sans exiger que
tous les fichiers d'une classe arrivent en un seul lot (cf. score_import.py
pour le cas d'un premier import complet — cette fonction gère aussi ce cas :
un lot dont aucun élève n'existe encore pour cette année se comporte
identiquement à run_import()).

Incident réel ayant motivé ce module : un import contenant uniquement un
fichier Éducation physique produisait 0% de risque, faute de signal sur les 7
matières modélisées (Maths/Physique-Chimie/SVT/langues/Histoire-Géo). La
contrainte students_pseudo_academic_year_unique refusait ensuite tout second
import pour compléter l'année. Ce module corrige les deux : un élève déjà
présent cette année est ré-profilé et re-scoré sur l'ENSEMBLE de ses matières
(anciennes, relues depuis Supabase via persistence.fetch.fetch_full_grades,
+ nouvelles), pas seulement le fichier qui vient d'arriver."""
from __future__ import annotations

import os
import sys
import uuid

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from anonymization.anonymize import anonymize_dataframe, assert_no_pii, build_identity_mapping
from cleaning.clean import build_coverage_matrix
from features.aggregate import add_subject_aggregates
from features.profile import build_student_profile
from models.targets import add_risk_label
from persistence.fetch import fetch_full_grades
from persistence.supabase_client import SupabaseRestClient
from recommendation.rules import MATIERES_FR
from score_import import (
    MODELS_DIR,
    _assign_clusters,
    _build_recommendations,
    _ingest_and_clean,
    _reference_date,
    _score_risk_and_regression,
)


def run_incremental_import(raw_dir: str, academic_year: str, models_dir: str = MODELS_DIR) -> dict:
    reference_date = _reference_date(academic_year)

    # --- A + B : ingestion, nettoyage (fichiers de CE lot uniquement) ---
    df, n_files_discovered, quarantined, bounds_anomalies, duplicate_anomalies = _ingest_and_clean(raw_dir)

    # --- C : anonymisation ---
    df_pseudo = anonymize_dataframe(df, reference_date)
    assert_no_pii(df_pseudo)
    identity_mapping = build_identity_mapping(df, reference_date)

    # --- D : agrégats par matière, sur les fichiers de CE lot ---
    new_df_agg = add_subject_aggregates(df_pseudo)

    # --- Classification élève par élève : déjà importé cette année scolaire,
    # ou nouveau — décide qui doit être fusionné avec ses matières existantes
    # avant re-scoring, et qui insérer tel quel (cf. score_import.run_import). ---
    client = SupabaseRestClient()
    new_pseudos = sorted(new_df_agg["student_pseudo"].dropna().unique().tolist())
    existing_rows = (
        client.select(
            "students",
            {
                "select": "id,student_pseudo",
                "student_pseudo": f"in.({','.join(new_pseudos)})",
                "academic_year": f"eq.{academic_year}",
            },
        )
        if new_pseudos
        else []
    )
    existing_id_by_pseudo = {r["student_pseudo"]: r["id"] for r in existing_rows}
    pseudo_to_id = {p: existing_id_by_pseudo.get(p, str(uuid.uuid4())) for p in new_pseudos}
    existing_student_ids = list(existing_id_by_pseudo.values())

    # --- Fusion : matières déjà en base (élèves existants) + nouveau fichier.
    # Une matière resoumise (même élève, même code matière déjà présent en
    # base) est remplacée par la version du nouveau fichier (keep="last"). ---
    old_grades = fetch_full_grades(client, existing_student_ids)
    df_agg = pd.concat([old_grades, new_df_agg], ignore_index=True) if not old_grades.empty else new_df_agg
    df_agg = df_agg.drop_duplicates(subset=["student_pseudo", "matiere"], keep="last")

    # --- Couverture (classe x matière) sur l'ensemble fusionné. ---
    all_niveaux = sorted(df_agg["niveau"].dropna().unique().tolist())
    all_classes = sorted(df_agg["classe"].dropna().unique().tolist())
    all_matieres = list(MATIERES_FR.keys())
    coverage = build_coverage_matrix(df_agg, all_niveaux, all_classes, all_matieres)
    coverage_counts = coverage["statut"].value_counts().to_dict()

    # --- E : profil élève sur l'ensemble fusionné (une ligne par élève
    # affecté par ce lot — nouveau ou déjà existant). ---
    profile, profile_issues = build_student_profile(df_agg)
    profile = add_risk_label(profile)

    # --- Score-only : classification + régression + clustering + recos,
    # sur le profil fusionné (corrige l'incident "Éducation physique seule
    # -> 0% de risque" : les 7 matières modélisées sont à nouveau visibles
    # dès qu'un élève existant en avait déjà en base). ---
    profile = _score_risk_and_regression(profile, df_agg, models_dir)
    clusters, cluster_exclusions = _assign_clusters(profile, models_dir)
    profile = profile.merge(
        clusters[["student_pseudo", "cluster_id", "cluster_label", "pca_1", "pca_2"]],
        on="student_pseudo",
        how="left",
    )
    recommendations, dispersion_seuils_source = _build_recommendations(profile, df_agg, models_dir)

    return {
        "academic_year": academic_year,
        "reference_date": reference_date.isoformat(),
        "n_files_discovered": n_files_discovered,
        "n_files_parsed_ok": n_files_discovered - len(quarantined),
        "n_files_quarantined": len(quarantined),
        "n_students": len(profile),
        "n_students_nouveaux": len(new_pseudos) - len(existing_student_ids),
        "n_students_completes": len(existing_student_ids),
        "n_a_risque_observe": int(profile["a_risque"].sum()),
        "n_a_risque_predit": int(profile["a_risque_predit"].sum()),
        "n_recommendations": len(recommendations),
        "cluster_exclusions": cluster_exclusions,
        "dispersion_seuils_source": dispersion_seuils_source,
        "quarantined_files": quarantined,
        "n_anomalies_bornes": len(bounds_anomalies),
        "n_doublons": len(duplicate_anomalies),
        "profile_issues": profile_issues,
        "coverage_counts": coverage_counts,
        "niveaux": all_niveaux,
        "classes": all_classes,
        "matieres": all_matieres,
        # Données en mémoire pour la persistance (push_scored_import.push_incremental_import).
        "profile": profile,
        "identity_mapping": identity_mapping,
        "pseudo_to_id": pseudo_to_id,
        "notes_long_new": new_df_agg,
        "notes_long_aggregated": df_agg,
        "coverage": coverage,
        "recommendations": recommendations,
    }
