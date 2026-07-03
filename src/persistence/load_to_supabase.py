"""Étape 10 — charge les artefacts pseudonymisés dans Supabase.

Usage :
    python src/persistence/load_to_supabase.py --dry-run     # construit tout, n'envoie rien
    python src/persistence/load_to_supabase.py                # charge réellement, puis vérifie

Nécessite SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY dans l'environnement
(jamais codés en dur — voir .env.example). Chaque exécution crée un NOUVEAU
`datasets.id` (historisation d'import, §2.8) : ce n'est pas un upsert, chaque
run correspond à un import distinct.

N'envoie que des artefacts POST-anonymisation (Stage C ou plus tard). Le
rapport de qualité brut (data_quality_report.json) n'est PAS envoyé tel quel :
il est généré à l'étape B, avant anonymisation, et ses listes détaillées
d'anomalies/doublons peuvent contenir des student_code en clair. Seul un
résumé filtré (compteurs, matrice de couverture) est persisté.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from persistence.serialize import records_json_safe
from persistence.supabase_client import SupabaseRestClient
from recommendation.rules import DOMAINS, MATIERES_FR

load_dotenv(".env.local")  # SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY, jamais commité

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"

# Clés explicitement autorisées depuis data_quality_report.json : compteurs et
# matrice de couverture seulement, jamais les listes détaillées (PII pré-anonymisation).
QUALITY_SUMMARY_ALLOWED_KEYS = [
    "n_files_discovered",
    "n_files_parsed_ok",
    "n_files_quarantined",
    "n_students_uniques",
    "n_enregistrements",
    "niveaux",
    "classes",
    "matieres",
    "coverage_counts",
    "n_anomalies_bornes",
    "n_doublons",
    "remplissage_composantes_pct",
    "composantes_disponibilite",
]

MATIERE_TO_DOMAIN = {m: d for d, ms in DOMAINS.items() for m in ms}


def _load_json(name: str) -> dict:
    with open(os.path.join(ARTIFACTS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(ARTIFACTS_DIR, name))


def build_subjects_payload() -> list[dict]:
    return [
        {"code": code, "nom_fr": nom_fr, "domaine": MATIERE_TO_DOMAIN[code]}
        for code, nom_fr in MATIERES_FR.items()
    ]


def build_dataset_payload(dataset_id: str, label: str, annee_scolaire: str, semestre: str) -> dict:
    quality = _load_json("data_quality_report.json")
    quality_summary = {k: quality[k] for k in QUALITY_SUMMARY_ALLOWED_KEYS if k in quality}
    risk_config = _load_json("risk_config.json")
    return {
        "id": dataset_id,
        "label": label,
        "annee_scolaire": annee_scolaire,
        "semestre": semestre,
        "date_import": datetime.now(timezone.utc).isoformat(),
        "n_eleves": quality.get("n_students_uniques"),
        "n_enregistrements": quality.get("n_enregistrements"),
        "statut": "charge",
        "quality_summary": quality_summary,
        "risk_config": risk_config,
    }


def build_students_payload(dataset_id: str) -> tuple[list[dict], dict[str, str]]:
    profile = _load_csv("student_profile_labeled.csv")
    pseudo_to_id = {p: str(uuid.uuid4()) for p in profile["student_pseudo"]}
    cols = [
        "niveau",
        "classe",
        "tranche_age",
        "nb_matieres_suivies",
        "moyenne_generale",
        "dispersion_intermatiere",
        "tendance_globale",
        "a_risque",
        "remarque_encodee",
    ]
    out = profile[["student_pseudo"] + cols].copy()
    out["id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["a_risque"] = out["a_risque"].astype(bool)
    return records_json_safe(out), pseudo_to_id


def build_grades_payload(dataset_id: str, pseudo_to_id: dict[str, str]) -> list[dict]:
    long_df = _load_csv("notes_long_with_aggregates.csv")
    cols = [
        "c1", "c2", "c3", "c4", "activites",
        "c1_colonne_existe", "c2_colonne_existe", "c3_colonne_existe",
        "c4_colonne_existe", "activites_colonne_existe",
        "moyenne_matiere", "n_composantes", "tendance_matiere", "remarque",
    ]
    out = long_df[["student_pseudo", "matiere"] + cols].copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out = out.rename(columns={"matiere": "subject_code", "remarque": "remarque_fr"})
    out = out.drop(columns=["student_pseudo"])
    return records_json_safe(out)


def build_model_runs_payload(dataset_id: str) -> dict[str, str]:
    """Renvoie les model_runs à insérer + les ids nécessaires pour lier
    predictions/clusters : {'classification_retenu': id, 'regression_retenu': id,
    'clustering_<NIVEAU>': id}."""
    clf_report = _load_json("classification_report.json")
    reg_report = _load_json("regression_report.json")
    clu_report = _load_json("clustering_report.json")

    runs = []
    ids = {}

    for algo, retenu in [("logistic_regression", True), ("random_forest", False)]:
        run_id = str(uuid.uuid4())
        runs.append(
            {
                "id": run_id,
                "dataset_id": dataset_id,
                "type": "classification",
                "algo": algo,
                "niveau": None,
                "params": {"retenu": retenu, "features": clf_report["features_utilisees"]},
                "metrics": clf_report[algo],
                "feature_columns": clf_report["features_utilisees"],
                "random_state": 42,
            }
        )
        if retenu:
            ids["classification_retenu"] = run_id

    for algo, retenu in [("ridge", True), ("random_forest_regressor", False)]:
        run_id = str(uuid.uuid4())
        runs.append(
            {
                "id": run_id,
                "dataset_id": dataset_id,
                "type": "regression",
                "algo": algo,
                "niveau": None,
                "params": {"retenu": retenu, "features": reg_report["features_utilisees"]},
                "metrics": reg_report[algo],
                "feature_columns": reg_report["features_utilisees"],
                "random_state": 42,
            }
        )
        if retenu:
            ids["regression_retenu"] = run_id

    for niveau, rep in clu_report.items():
        run_id = str(uuid.uuid4())
        runs.append(
            {
                "id": run_id,
                "dataset_id": dataset_id,
                "type": "clustering",
                "algo": rep["algo_retenu"],
                "niveau": niveau,
                "params": {"k": rep["k_retenu"], "features": rep["features"]},
                "metrics": {"silhouette": rep["silhouette_retenu"], "tailles": rep["tailles_clusters"]},
                "feature_columns": rep["features"],
                "random_state": 42,
            }
        )
        ids[f"clustering_{niveau}"] = run_id

    return runs, ids


def build_clusters_payload(dataset_id: str, pseudo_to_id: dict, run_ids: dict) -> list[dict]:
    clusters = _load_csv("clusters.csv")
    out = clusters[["student_pseudo", "niveau", "cluster_id", "cluster_label", "pca_1", "pca_2"]].copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["model_run_id"] = out["niveau"].map(lambda n: run_ids.get(f"clustering_{n}"))
    out = out.drop(columns=["student_pseudo", "niveau"])
    return records_json_safe(out)


def build_predictions_payload(dataset_id: str, pseudo_to_id: dict, run_ids: dict) -> list[dict]:
    explanations = _load_csv("explanations_students.csv")
    out = explanations[
        [
            "student_pseudo",
            "a_risque_predit",
            "probabilite_risque",
            "moyenne_generale_predite",
            "explication_risque_fr",
            "explication_moyenne_fr",
        ]
    ].copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["model_run_classification_id"] = run_ids["classification_retenu"]
    out["model_run_regression_id"] = run_ids["regression_retenu"]
    out["a_risque_predit"] = out["a_risque_predit"].astype(bool)
    out = out.drop(columns=["student_pseudo"])
    return records_json_safe(out)


def build_recommendations_payload(dataset_id: str, pseudo_to_id: dict) -> list[dict]:
    rec = _load_csv("recommendations.csv")
    out = rec[
        [
            "student_pseudo",
            "priorite",
            "type",
            "justification",
            "action",
            "matieres_concernees",
            "profil",
            "tendance_previsionnelle_moyenne_predite",
        ]
    ].copy()
    out["student_id"] = out["student_pseudo"].map(pseudo_to_id)
    out["dataset_id"] = dataset_id
    out["matieres_concernees"] = out["matieres_concernees"].apply(
        lambda s: [m for m in str(s).split(" | ") if m] if pd.notna(s) else []
    )
    out = out.drop(columns=["student_pseudo"])
    return records_json_safe(out)


def run(dry_run: bool, label: str, annee_scolaire: str, semestre: str) -> None:
    dataset_id = str(uuid.uuid4())
    print(f"Nouveau dataset_id : {dataset_id}")

    subjects = build_subjects_payload()
    dataset_row = build_dataset_payload(dataset_id, label, annee_scolaire, semestre)
    students, pseudo_to_id = build_students_payload(dataset_id)
    grades = build_grades_payload(dataset_id, pseudo_to_id)
    model_runs, run_ids = build_model_runs_payload(dataset_id)
    clusters = build_clusters_payload(dataset_id, pseudo_to_id, run_ids)
    predictions = build_predictions_payload(dataset_id, pseudo_to_id, run_ids)
    recommendations = build_recommendations_payload(dataset_id, pseudo_to_id)

    counts_local = {
        "subjects": len(subjects),
        "datasets": 1,
        "students": len(students),
        "grades": len(grades),
        "model_runs": len(model_runs),
        "clusters": len(clusters),
        "predictions": len(predictions),
        "recommendations": len(recommendations),
    }
    print("Lignes construites localement :")
    for table, n in counts_local.items():
        print(f"  {table:16s}: {n}")

    if dry_run:
        print("\n--dry-run : rien envoyé à Supabase.")
        return

    client = SupabaseRestClient()

    print("\nEnvoi vers Supabase...")
    client.insert("subjects", subjects, upsert_on_conflict="code")
    client.insert("datasets", [dataset_row])
    client.insert("students", students)
    client.insert("grades", grades)
    client.insert("model_runs", model_runs)
    client.insert("clusters", clusters)
    client.insert("predictions", predictions)
    client.insert("recommendations", recommendations)
    print("Envoi terminé.")

    print("\n=== Vérification des comptes (Supabase vs artefacts locaux) ===")
    all_ok = True
    for table in ("students", "grades", "model_runs", "clusters", "predictions", "recommendations"):
        remote = client.count(table, filters={"dataset_id": f"eq.{dataset_id}"})
        local = counts_local[table]
        status = "OK" if remote == local else "ECART"
        if remote != local:
            all_ok = False
        print(f"  {table:16s}: local={local:5d}  supabase={remote:5d}  [{status}]")

    subjects_remote = client.count("subjects")
    print(f"  {'subjects':16s}: local>={len(subjects):<3d} supabase={subjects_remote:5d}  "
          f"[{'OK' if subjects_remote >= len(subjects) else 'ECART'}]")

    print(f"\n{'Toutes les tables correspondent.' if all_ok else 'DES ECARTS SUBSISTENT — ne pas construire le frontend avant correction.'}")
    print(f"dataset_id chargé : {dataset_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Construit les payloads sans rien envoyer.")
    parser.add_argument("--label", default="Import Massar")
    parser.add_argument("--annee-scolaire", default="2025/2026")
    parser.add_argument("--semestre", default="Semestre 1")
    args = parser.parse_args()
    run(args.dry_run, args.label, args.annee_scolaire, args.semestre)
