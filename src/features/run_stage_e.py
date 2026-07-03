"""Exécute l'étape E sur data/artifacts/notes_long_with_aggregates.csv.

Usage : python src/features/run_stage_e.py
Écrit data/artifacts/student_profile_wide.csv et affiche un résumé court.
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from features.profile import build_student_profile

ARTIFACTS_DIR = "data/artifacts"
INPUT_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_with_aggregates.csv")
OUTPUT_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_wide.csv")
ISSUES_PATH = os.path.join(ARTIFACTS_DIR, "stage_e_issues.json")


def run(input_path: str = INPUT_PATH, output_path: str = OUTPUT_PATH) -> tuple[pd.DataFrame, list[dict]]:
    df = pd.read_csv(input_path)
    profile, issues = build_student_profile(df)
    profile.to_csv(output_path, index=False, encoding="utf-8-sig")
    with open(ISSUES_PATH, "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2, default=str)
    return profile, issues


def _print_summary(profile: pd.DataFrame, issues: list[dict]) -> None:
    print("=== Etape E : resume ===")
    print(f"Eleves dans le profil             : {len(profile)}")
    print(f"Colonnes du profil ({len(profile.columns)}) : {list(profile.columns)}")
    print("nb_matieres_suivies - distribution :")
    print(profile["nb_matieres_suivies"].value_counts().sort_index().to_dict())
    print("moyenne_generale - stats :")
    print(profile["moyenne_generale"].describe().round(2).to_dict())
    print(f"Eleves sans dispersion calculable (1 seule matiere) : {(profile['nb_matieres_suivies'] <= 1).sum()}")
    print(f"remarque_encodee manquante (aucun remarque exploitable) : {profile['remarque_encodee'].isna().sum()}")
    print(f"Incidents identite/remarque journalises : {len(issues)}")
    if issues:
        types = {}
        for i in issues:
            types[i["type"]] = types.get(i["type"], 0) + 1
        print(f"  detail : {types}")
    print(f"Ecrit : {OUTPUT_PATH}")
    print(f"Ecrit : {ISSUES_PATH}")


if __name__ == "__main__":
    profile, issues = run()
    _print_summary(profile, issues)
