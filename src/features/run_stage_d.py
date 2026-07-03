"""Exécute l'étape D sur data/artifacts/notes_long_pseudo.csv (déjà pseudonymisé).

Usage : python src/features/run_stage_d.py
Écrit data/artifacts/notes_long_with_aggregates.csv et affiche un résumé court.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from features.aggregate import add_subject_aggregates

ARTIFACTS_DIR = "data/artifacts"
INPUT_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_pseudo.csv")
OUTPUT_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_with_aggregates.csv")


def run(input_path: str = INPUT_PATH, output_path: str = OUTPUT_PATH) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    df = add_subject_aggregates(df)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return df


def _print_summary(df: pd.DataFrame) -> None:
    print("=== Etape D : resume ===")
    print(f"Enregistrements traites          : {len(df)}")
    print("Distribution n_composantes utilisees :")
    print(df["n_composantes"].value_counts().sort_index().to_dict())
    print(f"Moyenne matiere - NaN (aucune composante) : {df['moyenne_matiere'].isna().sum()}")
    print(f"Tendance matiere calculee (>=3 points)     : {df['tendance_matiere'].notna().sum()}")
    print("Moyenne matiere - stats globales :")
    print(df["moyenne_matiere"].describe().round(2).to_dict())
    print(f"Ecrit : {OUTPUT_PATH}")


if __name__ == "__main__":
    df = run()
    _print_summary(df)
