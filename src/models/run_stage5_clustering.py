"""Exécute l'étape 5 (clustering des profils) sur data/artifacts/student_profile_labeled.csv.

Usage : python src/models/run_stage5_clustering.py
Écrit :
- data/artifacts/clusters.csv            (student_pseudo, niveau, cluster_id, cluster_label, coords PCA)
- data/artifacts/clustering_report.json  (k retenu, silhouette, tailles, noms, candidats évalués)
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.clustering import run_clustering

ARTIFACTS_DIR = "data/artifacts"
MODELS_DIR = os.path.join(ARTIFACTS_DIR, "models")
INPUT_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
OUTPUT_PATH = os.path.join(ARTIFACTS_DIR, "clusters.csv")
REPORT_PATH = os.path.join(ARTIFACTS_DIR, "clustering_report.json")


def run() -> tuple[pd.DataFrame, dict]:
    os.makedirs(MODELS_DIR, exist_ok=True)
    df = pd.read_csv(INPUT_PATH)
    assignments, report, models_by_niveau = run_clustering(df)
    assignments.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # Persistés pour l'affectation de nouveaux élèves sans réentraînement
    # (score_import.py) : scaler + centroïdes + PCA déjà ajustés par niveau.
    for niveau, bundle in models_by_niveau.items():
        joblib.dump(bundle, os.path.join(MODELS_DIR, f"clustering_{niveau}.joblib"))

    return assignments, report


def _print_summary(assignments: pd.DataFrame, report: dict) -> None:
    print("=== Etape 5 : resume clustering ===")
    for niveau, rep in report.items():
        print(f"\n{niveau} (n_clusterises={rep['n_eleves_clusterises']}, "
              f"exclus_valeurs_manquantes={rep['n_eleves_exclus_valeurs_manquantes']}):")
        print(f"  features       : {rep['features']}")
        print(f"  algo/k retenu  : {rep['algo_retenu']} / k={rep['k_retenu']}")
        print(f"  silhouette     : {rep['silhouette_retenu']}")
        print(f"  tailles        : {rep['tailles_clusters']}")
        print(f"  noms clusters  : {rep['noms_clusters']}")
        print(f"  variance PCA2D : {[round(v,3) for v in rep['variance_expliquee_pca_2d']]}")
    print(f"\nTotal eleves clusterises : {len(assignments)}")
    print(f"Ecrit : {OUTPUT_PATH}")
    print(f"Ecrit : {REPORT_PATH}")


if __name__ == "__main__":
    assignments, report = run()
    _print_summary(assignments, report)
