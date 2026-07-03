"""Étape 7 — régression de moyenne_generale, features précoces uniquement (même
discipline anti-fuite qu'à l'étape 6 : seules C1/C2 alimentent les features,
jamais moyenne_matiere/domaines/dispersion de l'étape E).

Usage : python src/models/run_stage7_regression.py
Écrit :
- data/artifacts/regression_report.json (baseline + CV + test + erreurs par profil/niveau)
- data/artifacts/models/ridge.joblib
- data/artifacts/models/random_forest_regressor.joblib
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.early_features import (
    EARLY_CATEGORICAL_FEATURES,
    EARLY_FEATURE_COLUMNS,
    EARLY_NUMERIC_FEATURES,
    assemble_regression_dataset,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"
MODELS_DIR = os.path.join(ARTIFACTS_DIR, "models")
LONG_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_pseudo.csv")
PROFILE_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
CLUSTERS_PATH = os.path.join(ARTIFACTS_DIR, "clusters.csv")
REPORT_PATH = os.path.join(ARTIFACTS_DIR, "regression_report.json")

RANDOM_STATE = 42
N_SPLITS = 5
CV_SCORING = ["neg_mean_absolute_error", "neg_root_mean_squared_error", "r2"]


def build_pipeline(model) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                EARLY_NUMERIC_FEATURES,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                EARLY_CATEGORICAL_FEATURES,
            ),
        ]
    )
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def compute_metrics(y_true, y_pred) -> dict:
    return {
        "n": int(len(y_true)),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(root_mean_squared_error(y_true, y_pred)), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def grouped_metrics(df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, group_col: str) -> dict:
    out = {}
    for group in sorted(df[group_col].dropna().unique()):
        mask = (df[group_col] == group).to_numpy()
        if mask.sum() < 3:
            continue
        out[str(group)] = compute_metrics(y_true[mask], y_pred[mask])
    return out


def run() -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    df_long = pd.read_csv(LONG_PATH)
    df_profile = pd.read_csv(PROFILE_PATH)
    df_clusters = pd.read_csv(CLUSTERS_PATH)
    dataset = assemble_regression_dataset(df_long, df_profile, df_clusters)

    train = dataset[dataset["split"] == "train"].reset_index(drop=True)
    test = dataset[dataset["split"] == "test"].reset_index(drop=True)

    X_train, y_train = train[EARLY_FEATURE_COLUMNS], train["moyenne_generale"].to_numpy()
    X_test, y_test = test[EARLY_FEATURE_COLUMNS], test["moyenne_generale"].to_numpy()

    report = {
        "features_utilisees": EARLY_FEATURE_COLUMNS,
        "cible": "moyenne_generale",
        "n_train": len(train),
        "n_test": len(test),
    }

    # --- Baseline : prédicteur constant = moyenne du train (aucune fuite possible) ---
    baseline = DummyRegressor(strategy="mean").fit(X_train, y_train)
    baseline_train_pred = baseline.predict(X_train)
    baseline_test_pred = baseline.predict(X_test)
    report["baseline"] = {
        "regle": "moyenne(moyenne_generale) du train",
        "train": compute_metrics(y_train, baseline_train_pred),
        "test": compute_metrics(y_test, baseline_test_pred),
    }

    kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    models = {
        "ridge": RidgeCV(alphas=np.logspace(-2, 3, 30)),
        "random_forest_regressor": RandomForestRegressor(
            n_estimators=300, random_state=RANDOM_STATE
        ),
    }

    for name, model in models.items():
        pipeline = build_pipeline(model)

        cv_results = cross_validate(
            pipeline, X_train, y_train, cv=kf, scoring=CV_SCORING, return_train_score=False
        )
        cv_summary = {
            "mae": {
                "mean": round(float(-np.mean(cv_results["test_neg_mean_absolute_error"])), 4),
                "std": round(float(np.std(cv_results["test_neg_mean_absolute_error"])), 4),
            },
            "rmse": {
                "mean": round(
                    float(-np.mean(cv_results["test_neg_root_mean_squared_error"])), 4
                ),
                "std": round(float(np.std(cv_results["test_neg_root_mean_squared_error"])), 4),
            },
            "r2": {
                "mean": round(float(np.mean(cv_results["test_r2"])), 4),
                "std": round(float(np.std(cv_results["test_r2"])), 4),
            },
        }

        oof_pred = cross_val_predict(pipeline, X_train, y_train, cv=kf)

        pipeline.fit(X_train, y_train)
        test_pred = pipeline.predict(X_test)

        report[name] = {
            "cv_5fold_train": cv_summary,
            "oof_train": compute_metrics(y_train, oof_pred),
            "oof_train_par_profil": grouped_metrics(train, y_train, oof_pred, "cluster_label"),
            "oof_train_par_niveau": grouped_metrics(train, y_train, oof_pred, "niveau"),
            "test": compute_metrics(y_test, test_pred),
            "test_par_profil": grouped_metrics(test, y_test, test_pred, "cluster_label"),
            "test_par_niveau": grouped_metrics(test, y_test, test_pred, "niveau"),
        }
        if name == "ridge":
            report[name]["alpha_retenu"] = float(pipeline.named_steps["model"].alpha_)

        joblib.dump(pipeline, os.path.join(MODELS_DIR, f"{name}.joblib"))

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return report


def _print_summary(report: dict) -> None:
    print("=== Etape 7 : resume regression ===")
    print(f"Cible : {report['cible']}  |  Train n={report['n_train']}  Test n={report['n_test']}")

    print("\n--- Baseline (moyenne du train) ---")
    print(f"  train: {report['baseline']['train']}")
    print(f"  test : {report['baseline']['test']}")

    for name in ("ridge", "random_forest_regressor"):
        r = report[name]
        print(f"\n--- {name} ---" + (f" (alpha={r.get('alpha_retenu'):.3g})" if "alpha_retenu" in r else ""))
        print("  CV 5-fold (train) :")
        for metric, stats in r["cv_5fold_train"].items():
            print(f"    {metric:6s}: {stats['mean']:.4f} +/- {stats['std']:.4f}")
        print(f"  OOF train : {r['oof_train']}")
        print(f"  Test      : {r['test']}")
        print("  Erreur par profil (OOF train) :")
        for profil, m in r["oof_train_par_profil"].items():
            print(f"    {profil}: MAE={m['mae']} RMSE={m['rmse']} n={m['n']}")
        print("  Erreur par niveau (OOF train) :")
        for niveau, m in r["oof_train_par_niveau"].items():
            print(f"    {niveau}: MAE={m['mae']} RMSE={m['rmse']} n={m['n']}")

    print(f"\nEcrit : {REPORT_PATH}")
    print(f"Modeles sauvegardes dans : {MODELS_DIR}")


if __name__ == "__main__":
    report = run()
    _print_summary(report)
