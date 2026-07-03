"""Étape 6 — classification des élèves à risque, features précoces uniquement.

Usage : python src/models/run_stage6_classification.py
Écrit :
- data/artifacts/classification_report.json (baseline + CV + test + par niveau)
- data/artifacts/models/logistic_regression.joblib
- data/artifacts/models/random_forest.joblib
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.early_features import (
    EARLY_CATEGORICAL_FEATURES,
    EARLY_FEATURE_COLUMNS,
    EARLY_NUMERIC_FEATURES,
    assemble_dataset,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"
MODELS_DIR = os.path.join(ARTIFACTS_DIR, "models")
LONG_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_pseudo.csv")
PROFILE_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
REPORT_PATH = os.path.join(ARTIFACTS_DIR, "classification_report.json")

RANDOM_STATE = 42
PASSING_GRADE = 10.0
N_SPLITS = 5
CV_SCORING = ["accuracy", "precision", "recall", "f1", "roc_auc"]


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


def compute_metrics(y_true, y_pred, y_score=None) -> dict:
    metrics = {
        "n": int(len(y_true)),
        "n_a_risque": int(np.sum(y_true)),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }
    if y_score is not None and len(set(y_true)) > 1:
        metrics["roc_auc"] = round(roc_auc_score(y_true, y_score), 4)
    else:
        metrics["roc_auc"] = None
    return metrics


def baseline_predict(df: pd.DataFrame) -> np.ndarray:
    """Règle de seuil, sans fuite : moyenne des seules composantes précoces C1/C2."""
    return (df["early_generale"] < PASSING_GRADE).astype(int).to_numpy()


def per_niveau_metrics(df: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    out = {}
    for niveau in sorted(df["niveau"].unique()):
        mask = (df["niveau"] == niveau).to_numpy()
        if mask.sum() == 0:
            continue
        out[niveau] = compute_metrics(y_true[mask], y_pred[mask])
    return out


def run() -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    df_long = pd.read_csv(LONG_PATH)
    df_profile = pd.read_csv(PROFILE_PATH)
    dataset = assemble_dataset(df_long, df_profile)

    train = dataset[dataset["split"] == "train"].reset_index(drop=True)
    test = dataset[dataset["split"] == "test"].reset_index(drop=True)

    X_train, y_train = train[EARLY_FEATURE_COLUMNS], train["a_risque"].to_numpy()
    X_test, y_test = test[EARLY_FEATURE_COLUMNS], test["a_risque"].to_numpy()

    report = {
        "features_utilisees": EARLY_FEATURE_COLUMNS,
        "n_train": len(train),
        "n_test": len(test),
    }

    # --- Baseline : règle de seuil sur moyenne précoce (C1/C2), pas de fuite ---
    baseline_train_pred = baseline_predict(train)
    baseline_test_pred = baseline_predict(test)
    report["baseline"] = {
        "regle": f"early_generale < {PASSING_GRADE}",
        "train": compute_metrics(y_train, baseline_train_pred),
        "test": compute_metrics(y_test, baseline_test_pred),
        "par_niveau_train": per_niveau_metrics(train, y_train, baseline_train_pred),
        "par_niveau_test": per_niveau_metrics(test, y_test, baseline_test_pred),
    }

    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    models = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=RANDOM_STATE
        ),
    }

    for name, model in models.items():
        pipeline = build_pipeline(model)

        cv_results = cross_validate(
            pipeline, X_train, y_train, cv=skf, scoring=CV_SCORING, return_train_score=False
        )
        cv_summary = {
            metric: {
                "mean": round(float(np.mean(cv_results[f"test_{metric}"])), 4),
                "std": round(float(np.std(cv_results[f"test_{metric}"])), 4),
            }
            for metric in CV_SCORING
        }

        oof_pred = cross_val_predict(pipeline, X_train, y_train, cv=skf, method="predict")

        pipeline.fit(X_train, y_train)
        test_pred = pipeline.predict(X_test)
        test_score = (
            pipeline.predict_proba(X_test)[:, 1] if hasattr(pipeline, "predict_proba") else None
        )

        report[name] = {
            "cv_5fold_train": cv_summary,
            "oof_train": compute_metrics(y_train, oof_pred),
            "oof_train_par_niveau": per_niveau_metrics(train, y_train, oof_pred),
            "test": compute_metrics(y_test, test_pred, test_score),
            "test_par_niveau": per_niveau_metrics(test, y_test, test_pred),
        }

        joblib.dump(pipeline, os.path.join(MODELS_DIR, f"{name}.joblib"))

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return report


def _print_summary(report: dict) -> None:
    print("=== Etape 6 : resume classification ===")
    print(f"Features ({len(report['features_utilisees'])}) : {report['features_utilisees']}")
    print(f"Train n={report['n_train']}  Test n={report['n_test']}")

    print("\n--- Baseline (regle early_generale < 10) ---")
    print(f"  train: {report['baseline']['train']}")
    print(f"  test : {report['baseline']['test']}")

    for name in ("logistic_regression", "random_forest"):
        r = report[name]
        print(f"\n--- {name} ---")
        print("  CV 5-fold (train) :")
        for metric, stats in r["cv_5fold_train"].items():
            print(f"    {metric:10s}: {stats['mean']:.4f} +/- {stats['std']:.4f}")
        print(f"  OOF train (recall/precision/f1) : "
              f"{r['oof_train']['recall']} / {r['oof_train']['precision']} / {r['oof_train']['f1']}")
        print(f"  Test (recall/precision/f1/auc)  : "
              f"{r['test']['recall']} / {r['test']['precision']} / {r['test']['f1']} / {r['test']['roc_auc']}")
        print("  OOF train par niveau (recall) :")
        for niveau, m in r["oof_train_par_niveau"].items():
            print(f"    {niveau}: recall={m['recall']} precision={m['precision']} n_a_risque={m['n_a_risque']}/{m['n']}")
        print("  Test par niveau (recall) :")
        for niveau, m in r["test_par_niveau"].items():
            print(f"    {niveau}: recall={m['recall']} precision={m['precision']} n_a_risque={m['n_a_risque']}/{m['n']}")

    print(f"\nEcrit : {REPORT_PATH}")
    print(f"Modeles sauvegardes dans : {MODELS_DIR}")


if __name__ == "__main__":
    report = run()
    _print_summary(report)
