"""Pousse le résultat de score_import.run_import() (import score-only, sans
réentraînement) vers Supabase, pour une nouvelle academic_year.

Contrairement à load_to_supabase.py (pipeline d'entraînement complet), ce
module ne crée JAMAIS de nouvelle ligne model_runs : un import score-only ne
recalcule aucune métrique d'entraînement, donc n'a rien de nouveau à
consigner. Il RÉUTILISE les model_runs déjà créés lors du dernier
entraînement complet (cf. lookup_model_run_ids). Si aucun model_run
correspondant n'existe encore en base (ex. tout premier import), les colonnes
model_run_id / model_run_*_id sont laissées NULL (elles sont nullable dans le
schéma) plutôt que d'échouer.

Ne construit aucune explication SHAP (explication_risque_fr/
explication_moyenne_fr, colonnes texte de `predictions`) : l'étape 8
(explicabilité) n'est pas exécutée par score_import.run_import() — elle
nécessite le jeu d'entraînement complet comme fond SHAP, hors périmètre d'un
score-only. Ces deux colonnes sont laissées NULL pour les imports score-only ;
c'est une limitation connue, pas un oubli silencieux.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.targets import risk_config as compute_risk_config
from persistence.load_to_supabase import build_grades_payload, build_students_payload, build_subjects_payload
from persistence.serialize import records_json_safe
from persistence.supabase_client import SupabaseRestClient
from recommendation.rules import MATIERES_FR


def lookup_model_run_ids(client: SupabaseRestClient, niveaux: list[str]) -> dict[str, str | None]:
    """Retrouve les model_runs les plus récents (classification retenue,
    régression retenue, clustering par niveau) déjà présents en base — sans
    en créer de nouveaux. None si absent pour une catégorie donnée (ex. aucun
    entraînement complet n'a encore été chargé) : les FK correspondantes sont
    nullable, donc ce n'est pas bloquant."""
    ids: dict[str, str | None] = {}

    rows = client.select(
        "model_runs",
        {"select": "id", "type": "eq.classification", "algo": "eq.logistic_regression", "order": "created_at.desc", "limit": "1"},
    )
    ids["classification_retenu"] = rows[0]["id"] if rows else None

    rows = client.select(
        "model_runs",
        {"select": "id", "type": "eq.regression", "algo": "eq.ridge", "order": "created_at.desc", "limit": "1"},
    )
    ids["regression_retenu"] = rows[0]["id"] if rows else None

    for niveau in niveaux:
        rows = client.select(
            "model_runs",
            {"select": "id", "type": "eq.clustering", "niveau": f"eq.{niveau}", "order": "created_at.desc", "limit": "1"},
        )
        ids[f"clustering_{niveau}"] = rows[0]["id"] if rows else None

    return ids


def _build_clusters_payload(dataset_id: str, pseudo_to_id: dict, run_ids: dict, profile: pd.DataFrame) -> list[dict]:
    clusters_df = profile[["student_pseudo", "niveau", "cluster_id", "cluster_label", "pca_1", "pca_2"]].dropna(
        subset=["cluster_id"]
    )
    out = clusters_df.copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["model_run_id"] = out["niveau"].map(lambda n: run_ids.get(f"clustering_{n}"))
    out["cluster_id"] = out["cluster_id"].astype(int)
    out = out.drop(columns=["student_pseudo", "niveau"])
    return records_json_safe(out)


def _build_predictions_payload(dataset_id: str, pseudo_to_id: dict, run_ids: dict, profile: pd.DataFrame) -> list[dict]:
    out = profile[["student_pseudo", "a_risque_predit", "probabilite_risque", "moyenne_generale_predite"]].copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["model_run_classification_id"] = run_ids.get("classification_retenu")
    out["model_run_regression_id"] = run_ids.get("regression_retenu")
    out["a_risque_predit"] = out["a_risque_predit"].astype(bool)
    out["explication_risque_fr"] = None
    out["explication_moyenne_fr"] = None
    out = out.drop(columns=["student_pseudo"])
    return records_json_safe(out)


def _build_recommendations_payload(dataset_id: str, pseudo_to_id: dict, recommendations: list[dict], profile: pd.DataFrame) -> list[dict]:
    profile_idx = profile.set_index("student_pseudo")
    rows = []
    for rec in recommendations:
        pseudo = rec["student_pseudo"]
        prow = profile_idx.loc[pseudo]
        risk_status = "à risque" if bool(prow["a_risque"]) else "non à risque"
        profil = f"{prow.get('cluster_label') or 'n/a'}, {risk_status}"
        rows.append(
            {
                "student_id": pseudo_to_id[pseudo],
                "dataset_id": dataset_id,
                "priorite": rec["priorite"],
                "type": rec["type"],
                "justification": rec["justification"],
                "action": rec["action"],
                "matieres_concernees": rec["matieres_concernees"],
                "profil": profil,
                "tendance_previsionnelle_moyenne_predite": prow.get("moyenne_generale_predite"),
            }
        )
    if not rows:
        return []
    return records_json_safe(pd.DataFrame(rows))


def push_scored_import(result: dict, label: str, semestre: str = "Semestre 1") -> dict:
    """Envoie le résultat en mémoire de score_import.run_import() vers
    Supabase pour result['academic_year']. Renvoie {'dataset_id', 'counts'}.
    Lève RuntimeError si l'année scolaire a déjà été importée pour au moins un
    de ces élèves (contrainte students_pseudo_academic_year_unique)."""
    academic_year = result["academic_year"]
    profile = result["profile"]
    identity = result["identity_mapping"]
    long_agg = result["notes_long_aggregated"]
    recommendations = result["recommendations"]

    niveaux = result["niveaux"]
    dataset_id = str(uuid.uuid4())

    quality_summary = {
        "n_files_discovered": result["n_files_discovered"],
        "n_files_parsed_ok": result["n_files_parsed_ok"],
        "n_files_quarantined": result["n_files_quarantined"],
        "n_students_uniques": result["n_students"],
        "n_enregistrements": len(long_agg),
        "niveaux": niveaux,
        "classes": result["classes"],
        "matieres": result["matieres"],
        "coverage_counts": result["coverage_counts"],
        "n_anomalies_bornes": result["n_anomalies_bornes"],
        "n_doublons": result["n_doublons"],
    }

    dataset_row = {
        "id": dataset_id,
        "label": label,
        "annee_scolaire": academic_year,
        "semestre": semestre,
        "date_import": datetime.now(timezone.utc).isoformat(),
        "n_eleves": result["n_students"],
        "n_enregistrements": len(long_agg),
        "statut": "charge",
        "quality_summary": quality_summary,
        "risk_config": compute_risk_config(),
    }

    subjects = build_subjects_payload()
    students, pseudo_to_id = build_students_payload(dataset_id, academic_year, profile, identity)
    grades = build_grades_payload(dataset_id, pseudo_to_id, long_agg)

    client = SupabaseRestClient()
    run_ids = lookup_model_run_ids(client, niveaux)

    clusters = _build_clusters_payload(dataset_id, pseudo_to_id, run_ids, profile)
    predictions = _build_predictions_payload(dataset_id, pseudo_to_id, run_ids, profile)
    recs = _build_recommendations_payload(dataset_id, pseudo_to_id, recommendations, profile)

    counts_local = {
        "subjects": len(subjects),
        "students": len(students),
        "grades": len(grades),
        "clusters": len(clusters),
        "predictions": len(predictions),
        "recommendations": len(recs),
    }

    client.insert("subjects", subjects, upsert_on_conflict="code")
    client.insert("datasets", [dataset_row])
    try:
        client.insert("students", students)
    except RuntimeError as exc:
        if "students_pseudo_academic_year_unique" in str(exc):
            raise RuntimeError(
                f"Import refusé : au moins un élève a déjà une ligne pour l'année "
                f"scolaire {academic_year!r} (contrainte students_pseudo_academic_year_unique)."
            ) from exc
        raise
    client.insert("grades", grades)
    if clusters:
        client.insert("clusters", clusters)
    if predictions:
        client.insert("predictions", predictions)
    if recs:
        client.insert("recommendations", recs)

    return {"dataset_id": dataset_id, "counts": counts_local, "model_run_ids_reused": run_ids}
