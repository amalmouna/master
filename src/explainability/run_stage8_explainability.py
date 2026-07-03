"""Étape 8 — explicabilité, sur les modèles retenus (Logistic Regression, Ridge).

Usage : python src/explainability/run_stage8_explainability.py
Écrit :
- data/artifacts/explainability_global.json   (importance des variables, les deux modèles)
- data/artifacts/explanations_students.csv    (explication locale FR par élève, les 481)
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from explainability.explain import global_importance, local_explanation
from models.early_features import EARLY_FEATURE_COLUMNS, assemble_regression_dataset

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"
MODELS_DIR = os.path.join(ARTIFACTS_DIR, "models")
LONG_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_pseudo.csv")
PROFILE_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
CLUSTERS_PATH = os.path.join(ARTIFACTS_DIR, "clusters.csv")
GLOBAL_REPORT_PATH = os.path.join(ARTIFACTS_DIR, "explainability_global.json")
STUDENT_EXPLANATIONS_PATH = os.path.join(ARTIFACTS_DIR, "explanations_students.csv")


def run() -> tuple[dict, pd.DataFrame]:
    df_long = pd.read_csv(LONG_PATH)
    df_profile = pd.read_csv(PROFILE_PATH)
    df_clusters = pd.read_csv(CLUSTERS_PATH)

    dataset = assemble_regression_dataset(df_long, df_profile, df_clusters)
    dataset = dataset.merge(df_profile[["student_pseudo", "a_risque"]], on="student_pseudo", how="left")

    train = dataset[dataset["split"] == "train"].reset_index(drop=True)

    clf_pipeline = joblib.load(os.path.join(MODELS_DIR, "logistic_regression.joblib"))
    reg_pipeline = joblib.load(os.path.join(MODELS_DIR, "ridge.joblib"))

    X_background = train[EARLY_FEATURE_COLUMNS]

    global_report = {
        "logistic_regression": global_importance(clf_pipeline, X_background, task="classification").to_dict(
            orient="records"
        ),
        "ridge": global_importance(reg_pipeline, X_background, task="regression").to_dict(
            orient="records"
        ),
    }
    with open(GLOBAL_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(global_report, f, ensure_ascii=False, indent=2, default=str)

    rows = []
    for i in range(len(dataset)):
        X_row = dataset.iloc[[i]][EARLY_FEATURE_COLUMNS]
        risk_pred = int(clf_pipeline.predict(X_row)[0])
        risk_proba = float(clf_pipeline.predict_proba(X_row)[0, 1])
        moyenne_predite = float(reg_pipeline.predict(X_row)[0])

        risk_expl = local_explanation(clf_pipeline, X_background, X_row, task="classification")
        reg_expl = local_explanation(reg_pipeline, X_background, X_row, task="regression")

        rows.append(
            {
                "student_pseudo": dataset.iloc[i]["student_pseudo"],
                "niveau": dataset.iloc[i]["niveau"],
                "classe": dataset.iloc[i]["classe"],
                "a_risque_reel": int(dataset.iloc[i]["a_risque"]),
                "a_risque_predit": risk_pred,
                "probabilite_risque": round(risk_proba, 4),
                "explication_risque_fr": risk_expl["texte"],
                "moyenne_generale_predite": round(moyenne_predite, 2),
                "explication_moyenne_fr": reg_expl["texte"],
            }
        )

    explanations_df = pd.DataFrame(rows)
    explanations_df.to_csv(STUDENT_EXPLANATIONS_PATH, index=False, encoding="utf-8-sig")
    return global_report, explanations_df


def _print_summary(global_report: dict, explanations_df: pd.DataFrame) -> None:
    print("=== Etape 8 : resume explicabilite ===")
    for model_name, rows in global_report.items():
        print(f"\n--- Importance globale : {model_name} ---")
        for r in rows[:6]:
            print(f"  {r['feature']:30s} shap_abs_moyen={r['shap_abs_moyen']:.4f}  coef_std={r['coefficient_standardise']:.4f}")

    print(f"\nExplications locales generees pour {len(explanations_df)} eleves.")
    print("\nExemples (3 a risque predits, 2 non a risque) :")
    sample_risk = explanations_df[explanations_df["a_risque_predit"] == 1].head(3)
    sample_safe = explanations_df[explanations_df["a_risque_predit"] == 0].head(2)
    for _, row in pd.concat([sample_risk, sample_safe]).iterrows():
        print(f"\n  [{row['student_pseudo'][:8]}] proba_risque={row['probabilite_risque']}")
        print(f"    {row['explication_risque_fr']}")
        print(f"    moyenne predite={row['moyenne_generale_predite']} | {row['explication_moyenne_fr']}")

    print(f"\nEcrit : {GLOBAL_REPORT_PATH}")
    print(f"Ecrit : {STUDENT_EXPLANATIONS_PATH}")


if __name__ == "__main__":
    global_report, explanations_df = run()
    _print_summary(global_report, explanations_df)
