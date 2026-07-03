"""Étape 9 — génère les recommandations pédagogiques et les signaux d'établissement.

Usage : python src/recommendation/run_stage9_recommendations.py
Écrit :
- data/artifacts/recommendations.csv            (une ligne par recommandation)
- data/artifacts/recommendations_by_student.json (groupé par élève, trié par priorité)
- data/artifacts/school_level_signals.json       (signaux agrégés pour la vue d'ensemble)
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from recommendation.rules import DOMAINS, MATIERES_FR, SEUIL_DIFFICULTE, SEUIL_SEVERE, generate_recommendations

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"
PROFILE_PATH = os.path.join(ARTIFACTS_DIR, "student_profile_labeled.csv")
CLUSTERS_PATH = os.path.join(ARTIFACTS_DIR, "clusters.csv")
EXPLANATIONS_PATH = os.path.join(ARTIFACTS_DIR, "explanations_students.csv")
AGGREGATES_PATH = os.path.join(ARTIFACTS_DIR, "notes_long_with_aggregates.csv")
REC_CSV_PATH = os.path.join(ARTIFACTS_DIR, "recommendations.csv")
REC_JSON_PATH = os.path.join(ARTIFACTS_DIR, "recommendations_by_student.json")
SIGNALS_PATH = os.path.join(ARTIFACTS_DIR, "school_level_signals.json")

MATIERE_TO_DOMAIN = {m: d for d, ms in DOMAINS.items() for m in ms}
SIGNAL_ETABLISSEMENT_SEUIL = 0.5  # >50% d'élèves sous 10 dans une matière = signal établissement


def compute_domain_trends(aggregates: pd.DataFrame) -> dict:
    """Par élève et par domaine : moyenne des pentes intra-semestre (tendance_matiere)
    sur les matières suivies du domaine. NaN si aucune pente disponible."""
    df = aggregates.copy()
    df["domaine"] = df["matiere"].map(MATIERE_TO_DOMAIN)
    grouped = df.groupby(["student_pseudo", "domaine"])["tendance_matiere"].mean()
    trends = {}
    for (pseudo, domaine), val in grouped.items():
        trends.setdefault(pseudo, {})[domaine] = val
    return trends


def per_niveau_dispersion_seuil(profile: pd.DataFrame) -> dict:
    return profile.groupby("niveau")["dispersion_intermatiere"].quantile(0.75).to_dict()


def build_school_signals(profile: pd.DataFrame) -> dict:
    signals = {"par_matiere": {}, "signaux_etablissement": [], "par_niveau_risque": {}, "global": {}}
    for m, fr in MATIERES_FR.items():
        col = f"moy_{m}"
        if col not in profile.columns:
            continue
        followed = profile[col].dropna()
        if followed.empty:
            continue
        pct_sous_10 = float((followed < SEUIL_DIFFICULTE).mean())
        entry = {
            "matiere": fr,
            "n_suivi": int(followed.shape[0]),
            "moyenne": round(float(followed.mean()), 2),
            "pct_sous_10": round(100 * pct_sous_10, 1),
            "pct_sous_8": round(100 * float((followed < SEUIL_SEVERE).mean()), 1),
        }
        signals["par_matiere"][fr] = entry
        if pct_sous_10 > SIGNAL_ETABLISSEMENT_SEUIL:
            signals["signaux_etablissement"].append(
                {
                    "matiere": fr,
                    "message": f"{fr} : {entry['pct_sous_10']}% des élèves suivis sont sous 10/20 "
                    f"({entry['pct_sous_8']}% sous 8/20) — faiblesse à l'échelle de l'établissement.",
                    "pct_sous_10": entry["pct_sous_10"],
                }
            )
    signals["signaux_etablissement"].sort(key=lambda s: s["pct_sous_10"], reverse=True)
    for niveau, g in profile.groupby("niveau"):
        signals["par_niveau_risque"][niveau] = {
            "n": int(len(g)),
            "pct_a_risque": round(100 * float(g["a_risque"].mean()), 1),
        }
    signals["global"] = {
        "n_eleves": int(len(profile)),
        "pct_a_risque": round(100 * float(profile["a_risque"].mean()), 1),
    }
    return signals


def run() -> tuple[pd.DataFrame, dict]:
    profile = pd.read_csv(PROFILE_PATH)
    clusters = pd.read_csv(CLUSTERS_PATH)[["student_pseudo", "cluster_label"]]
    explanations = pd.read_csv(EXPLANATIONS_PATH)[
        ["student_pseudo", "probabilite_risque", "moyenne_generale_predite"]
    ]
    aggregates = pd.read_csv(AGGREGATES_PATH)

    merged = profile.merge(clusters, on="student_pseudo", how="left").merge(
        explanations, on="student_pseudo", how="left"
    )

    domain_trends = compute_domain_trends(aggregates)
    dispersion_seuils = per_niveau_dispersion_seuil(profile)

    rec_rows = []
    by_student = {}
    for _, row in merged.iterrows():
        pseudo = row["student_pseudo"]
        trends = domain_trends.get(pseudo, {})
        seuil = dispersion_seuils.get(row["niveau"], np.inf)
        recs = generate_recommendations(row, seuil, trends)

        risk_status = "à risque" if bool(row["a_risque"]) else "non à risque"
        profil = f"{row.get('cluster_label', 'n/a')}, {risk_status}"
        tendance_prev = (
            round(float(row["moyenne_generale_predite"]), 2)
            if pd.notna(row.get("moyenne_generale_predite"))
            else None
        )

        student_entry = {
            "niveau": row["niveau"],
            "classe": row["classe"],
            "profil": profil,
            "probabilite_risque": (
                round(float(row["probabilite_risque"]), 4)
                if pd.notna(row.get("probabilite_risque"))
                else None
            ),
            "tendance_previsionnelle": {
                "moyenne_generale_predite": tendance_prev,
                "note": "Estimation du modèle Ridge à partir des premiers contrôles (C1/C2) — indicatif, non observé.",
            },
            "recommandations": [],
        }
        for rec in recs:
            row_out = {
                "student_pseudo": pseudo,
                "niveau": row["niveau"],
                "classe": row["classe"],
                "priorite": rec["priorite"],
                "type": rec["type"],
                "justification": rec["justification"],
                "action": rec["action"],
                "matieres_concernees": " | ".join(MATIERES_FR.get(m, m) for m in rec["matieres_concernees"]),
                "profil": profil,
                "tendance_previsionnelle_moyenne_predite": tendance_prev,
            }
            rec_rows.append(row_out)
            student_entry["recommandations"].append(
                {k: rec[k] for k in ("priorite", "type", "justification", "action")}
                | {"matieres_concernees": [MATIERES_FR.get(m, m) for m in rec["matieres_concernees"]]}
            )
        if student_entry["recommandations"]:
            by_student[pseudo] = student_entry

    rec_df = pd.DataFrame(rec_rows)
    rec_df.to_csv(REC_CSV_PATH, index=False, encoding="utf-8-sig")
    with open(REC_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(by_student, f, ensure_ascii=False, indent=2)

    signals = build_school_signals(profile)
    with open(SIGNALS_PATH, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    return rec_df, signals


def _print_summary(rec_df: pd.DataFrame, signals: dict) -> None:
    print("=== Etape 9 : resume recommandations ===")
    print(f"Recommandations générées : {len(rec_df)}")
    print(f"Élèves avec >=1 recommandation : {rec_df['student_pseudo'].nunique()}")
    print("Par priorité :")
    print(f"  {rec_df['priorite'].value_counts().sort_index().to_dict()}")
    print("Par type :")
    for t, c in rec_df["type"].value_counts().items():
        print(f"  {t}: {c}")
    print("\nSignaux établissement (>50% sous 10) :")
    for s in signals["signaux_etablissement"]:
        print(f"  - {s['message']}")
    print("\nRisque par niveau :")
    for niv, r in signals["par_niveau_risque"].items():
        print(f"  {niv}: {r['pct_a_risque']}% (n={r['n']})")
    print(f"\nEcrit : {REC_CSV_PATH}")
    print(f"Ecrit : {REC_JSON_PATH}")
    print(f"Ecrit : {SIGNALS_PATH}")


if __name__ == "__main__":
    rec_df, signals = run()
    _print_summary(rec_df, signals)
