"""Orchestrateur des étapes A (ingestion) -> B (nettoyage) -> C (anonymisation).

Usage : python src/pipeline_run.py [--raw-dir CHEMIN]
Écrit les artefacts dans data/processed/ (table nettoyée, PII locale, jamais committée)
et data/artifacts/ (table pseudonymisée + rapport de qualité + matrice de couverture).
Affiche un résumé court sur stdout (aucune donnée nominative, aucun texte arabe brut
pour rester lisible sur une console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

from anonymization.anonymize import anonymize_dataframe, assert_no_pii, build_identity_mapping
from cleaning.clean import (
    apply_bounds_check,
    build_coverage_matrix,
    build_long_dataframe,
    detect_duplicates,
)
from ingestion.discover import discover_xlsx
from ingestion.parse_massar import parse_file

REFERENCE_DATE = date(2025, 9, 1)  # 1er septembre de l'année scolaire 2025/2026
ALL_MATIERES = [
    "MATHEMATIQUES",
    "PHYSIQUE CHIMIE",
    "SC. DE LA VIE ET DE LA TERRE",
    "LANGUE ARABE",
    "LANGUE FRANCAISE",
    "LANGUE ANGLAISE",
    "HISTOIRE GEOGRAPHIE",
]


def run(raw_dir: str, processed_dir: str, artifacts_dir: str) -> dict:
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(artifacts_dir, exist_ok=True)

    files = discover_xlsx(raw_dir)
    parsed_ok, quarantined = [], []
    for f in files:
        parsed = parse_file(f)
        blocking = {"FILE_UNREADABLE", "HEADER_NOT_FOUND", "NO_STUDENT_ROWS"}
        if not parsed.ok or any(i["code"] in blocking for i in parsed.issues):
            quarantined.append(
                {"source_file": os.path.basename(f), "issues": parsed.issues}
            )
        else:
            parsed_ok.append(parsed)

    all_records = [rec for p in parsed_ok for rec in p.records]
    df = build_long_dataframe(all_records)
    df, bounds_anomalies = apply_bounds_check(df)
    df, duplicate_anomalies = detect_duplicates(df)

    all_classes = sorted(df["classe"].dropna().unique())
    all_niveaux = sorted(df["niveau"].dropna().unique())
    coverage = build_coverage_matrix(df, all_niveaux, all_classes, ALL_MATIERES)

    n_students = df["student_code"].nunique()
    cross_check_issues = [
        {"source_file": os.path.basename(p.source_file), "issues": p.issues}
        for p in parsed_ok
        if p.issues
    ]

    df_clean_path = os.path.join(processed_dir, "notes_long_clean.csv")
    df.to_csv(df_clean_path, index=False, encoding="utf-8-sig")

    df_pseudo = anonymize_dataframe(df, REFERENCE_DATE)
    assert_no_pii(df_pseudo)
    pseudo_path = os.path.join(artifacts_dir, "notes_long_pseudo.csv")
    df_pseudo.to_csv(pseudo_path, index=False, encoding="utf-8-sig")

    # ATTENTION : contient des noms réels. Fichier séparé, local, gitignored,
    # consommé UNIQUEMENT par le loader Supabase (architecture authentifiée) —
    # jamais par les étapes D-9, qui restent sur la table pseudonymisée ci-dessus.
    identity_mapping = build_identity_mapping(df, REFERENCE_DATE)
    identity_path = os.path.join(artifacts_dir, "identity_mapping.csv")
    identity_mapping.to_csv(identity_path, index=False, encoding="utf-8-sig")

    coverage_path = os.path.join(artifacts_dir, "coverage_matrix.csv")
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    quality_report = {
        "n_files_discovered": len(files),
        "n_files_parsed_ok": len(parsed_ok),
        "n_files_quarantined": len(quarantined),
        "n_students_uniques": int(n_students),
        "n_enregistrements": int(len(df)),
        "niveaux": all_niveaux,
        "classes": all_classes,
        "matieres": ALL_MATIERES,
        "coverage_counts": coverage["statut"].value_counts().to_dict(),
        "n_anomalies_bornes": len(bounds_anomalies),
        "n_doublons": len(duplicate_anomalies),
        "fichiers_quarantaine": quarantined,
        "recoupement_nom_contenu_issues": cross_check_issues,
        "anomalies_bornes": bounds_anomalies,
        "doublons": duplicate_anomalies,
        "remplissage_composantes_pct": {
            col: round(100 * df[col].notna().mean(), 1) if col in df.columns else None
            for col in ["c1", "c2", "c3", "c4", "activites"]
        },
        "composantes_disponibilite": {
            col: {
                "pct_enregistrements_avec_colonne": round(
                    100 * df[f"{col}_colonne_existe"].mean(), 1
                ),
                "pct_rempli_quand_colonne_existe": (
                    round(
                        100
                        * df.loc[df[f"{col}_colonne_existe"], col].notna().mean(),
                        1,
                    )
                    if df[f"{col}_colonne_existe"].any()
                    else None
                ),
            }
            for col in ["c1", "c2", "c3", "c4", "activites"]
        },
    }
    report_path = os.path.join(artifacts_dir, "data_quality_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, ensure_ascii=False, indent=2, default=str)

    quality_report["_paths"] = {
        "clean": df_clean_path,
        "pseudo": pseudo_path,
        "identity_mapping_CONTAINS_PII": identity_path,
        "coverage": coverage_path,
        "report": report_path,
    }
    return quality_report


def _print_summary(report: dict) -> None:
    print("=== Etape A-C : resume ===")
    print(f"Fichiers decouverts       : {report['n_files_discovered']}")
    print(f"Fichiers parses OK        : {report['n_files_parsed_ok']}")
    print(f"Fichiers en quarantaine   : {report['n_files_quarantined']}")
    print(f"Niveaux                   : {report['niveaux']}")
    print(f"Classes ({len(report['classes'])})            : {report['classes']}")
    print(f"Matieres attendues        : {report['matieres']}")
    print(f"Eleves uniques            : {report['n_students_uniques']}")
    print(f"Enregistrements (eleve x matiere) : {report['n_enregistrements']}")
    print(f"Couverture (classe x matiere)     : {report['coverage_counts']}")
    print(f"Anomalies notes hors [0,20]       : {report['n_anomalies_bornes']}")
    print(f"Doublons eleve+classe+matiere     : {report['n_doublons']}")
    print(f"Remplissage composantes (%, ensemble) : {report['remplissage_composantes_pct']}")
    print("Disponibilite par composante (colonne presente vs remplie) :")
    for col, stats in report["composantes_disponibilite"].items():
        print(f"  - {col}: colonne presente dans {stats['pct_enregistrements_avec_colonne']}% "
              f"des enregistrements ; remplie a {stats['pct_rempli_quand_colonne_existe']}% "
              f"quand la colonne existe")
    if report["fichiers_quarantaine"]:
        print("Fichiers en quarantaine (detail) :")
        for q in report["fichiers_quarantaine"]:
            codes = [i["code"] for i in q["issues"]]
            print(f"  - {q['source_file']}: {codes}")
    if report["recoupement_nom_contenu_issues"]:
        print("Ecarts nom de fichier / contenu :")
        for c in report["recoupement_nom_contenu_issues"]:
            codes = [i["code"] for i in c["issues"]]
            print(f"  - {c['source_file']}: {codes}")
    print(f"Artefacts ecrits dans : {report['_paths']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--artifacts-dir", default="data/artifacts")
    args = parser.parse_args()

    report = run(args.raw_dir, args.processed_dir, args.artifacts_dir)
    _print_summary(report)
