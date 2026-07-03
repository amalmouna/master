"""Exécute l'étape F sur data/artifacts/student_profile_wide.csv.

Usage : python src/models/run_stage_f.py
Écrit :
- data/artifacts/student_profile_labeled.csv  (profil + a_risque + split)
- data/artifacts/risk_config.json             (seuils documentés)
Affiche un résumé court (prévalence globale et par split, par niveau, par nb_matieres).
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.split import make_split, split_report
from models.targets import TARGET_RISK, add_risk_label, risk_config

ARTIFACTS_DIR = "data/artifacts"
INPUT_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_wide.csv")
OUTPUT_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
CONFIG_PATH = os.path.join(ARTIFACTS_DIR, "risk_config.json")


def run() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(INPUT_PATH)
    df = add_risk_label(df)
    df = make_split(df)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    cfg = risk_config()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return df, cfg


def _print_summary(df: pd.DataFrame) -> None:
    print("=== Etape F : resume ===")
    print(f"Eleves                          : {len(df)}")
    print(f"A risque (global)               : {int(df[TARGET_RISK].sum())} "
          f"({100*df[TARGET_RISK].mean():.1f}%)")
    print("Split (stratifie sur a_risque)  :")
    for name, r in split_report(df).items():
        print(f"  {name:5s}: n={r['n']:3d}  a_risque={r['n_a_risque']:3d}  "
              f"prevalence={100*r['prevalence_risque']:.1f}%")
    print("Prevalence par niveau           :")
    for niveau, g in df.groupby("niveau"):
        print(f"  {niveau}: {100*g[TARGET_RISK].mean():.1f}% (n={len(g)})")
    print("Prevalence par nb_matieres_suivies :")
    for k, g in df.groupby("nb_matieres_suivies"):
        print(f"  {k} matieres: {100*g[TARGET_RISK].mean():.1f}% (n={len(g)})")
    print(f"Ecrit : {OUTPUT_PATH}")
    print(f"Ecrit : {CONFIG_PATH}")


if __name__ == "__main__":
    df, cfg = run()
    _print_summary(df)
