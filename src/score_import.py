"""Score-only : applique le pipeline entraîné à un nouvel import, SANS jamais
réentraîner quoi que ce soit — parse -> nettoie -> anonymise -> agrège ->
profile, puis charge les modèles déjà ajustés (data/artifacts/models/) pour
produire risque, moyenne prédite, cluster et recommandations.

Usage :
    python src/score_import.py --raw-dir CHEMIN --academic-year 2025/2026

Ne touche JAMAIS aux artefacts d'entraînement (data/artifacts/*.csv) : c'est
une fonction pure qui prend un dossier de fichiers Massar et renvoie un
dictionnaire de résultats en mémoire — aucune écriture disque par défaut.
La persistance (Supabase, etc.) est laissée au futur backend web (hors
périmètre ici, cf. consigne).

--- Sel de pseudonymisation (student_pseudo) ---
Lu depuis la variable d'environnement MASSAR_SALT si définie, sinon depuis
data/artifacts/.salt (généré au premier run si absent) — cf.
anonymization.anonymize.get_or_create_salt, inchangé par ce module. Pour
qu'un même élève garde le même student_pseudo d'un import à l'autre (et donc
reste reconnaissable dans la base au fil des semestres), le service qui
appelle run_import() doit fournir la MÊME valeur MASSAR_SALT à chaque
invocation (ex. secret d'environnement du backend), plutôt que de compter
sur le fichier .salt local qui n'a de sens que pour des runs sur la même
machine/le même disque.

--- Affectation aux clusters sur un nouvel import (sans réentraînement) ---
Les modèles de clustering sauvegardés (data/artifacts/models/clustering_<niveau>.joblib)
contiennent : le StandardScaler ajusté, la PCA ajustée, et les CENTROÏDES
(moyenne des points par cluster dans l'espace standardisé). Un nouvel élève
est affecté au centroïde le plus proche (distance euclidienne), UN SEUL
mécanisme pour les deux algorithmes retenus à l'entraînement (kmeans pour
1APIC, agglomerative pour 2APIC/3APIC) :
- Pour kmeans, ce mécanisme est EXACT : par construction, les centroïdes de
  KMeans sont la moyenne des points de chaque cluster à convergence, donc
  "plus proche centroïde" est rigoureusement équivalent à `model.predict()`.
  Vérifié empiriquement : 0 écart sur les 198 élèves d'entraînement 1APIC.
- Pour agglomerative, qui n'a pas de `.predict()`, c'est le mécanisme de
  repli standard pour affecter un nouveau point à un clustering hiérarchique.
  C'est une APPROXIMATION, pas une réplique exacte : l'agglomératif ne
  découpe pas l'espace en régions de Voronoi autour de centroïdes, donc
  quelques points proches d'une frontière peuvent être affectés différemment
  de l'assignation hiérarchique d'origine. Vérifié empiriquement en
  réappliquant le mécanisme aux données d'entraînement elles-mêmes : ~5%
  d'écart pour 2APIC (7/147) et ~7% pour 3APIC (9/136). C'est le meilleur
  compromis disponible (il n'existe pas de méthode exacte pour scorer un
  nouveau point sur un clustering agglomératif déjà ajusté), documenté ici
  plutôt que présenté comme un score-only exact.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from anonymization.anonymize import anonymize_dataframe, assert_no_pii, build_identity_mapping
from cleaning.clean import apply_bounds_check, build_coverage_matrix, build_long_dataframe, detect_duplicates
from features.aggregate import add_subject_aggregates
from features.profile import build_student_profile
from ingestion.discover import discover_xlsx
from ingestion.parse_massar import parse_file
from models.clustering import FEATURES_BY_NIVEAU, assign_to_nearest_centroid
from models.early_features import EARLY_FEATURE_COLUMNS, build_early_profile
from models.targets import add_risk_label
from recommendation.rules import MATIERES_FR, compute_domain_trends, generate_recommendations

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARTIFACTS_DIR = "data/artifacts"
MODELS_DIR = os.path.join(ARTIFACTS_DIR, "models")
RECOMMENDATION_THRESHOLDS_PATH = os.path.join(MODELS_DIR, "recommendation_thresholds.json")

# Modèles retenus (cf. décisions §6/§7) : Logistic Regression et Ridge, jamais
# les alternatives random_forest/random_forest_regressor également sauvegardées.
RETAINED_CLASSIFIER = "logistic_regression"
RETAINED_REGRESSOR = "ridge"

BLOCKING_ISSUE_CODES = {"FILE_UNREADABLE", "HEADER_NOT_FOUND", "NO_STUDENT_ROWS", "MATIERE_HORS_PERIMETRE"}


def _reference_date(academic_year: str) -> date:
    """'2025/2026' -> 1er septembre 2025 (même convention que pipeline_run.py)."""
    parts = academic_year.split("/")
    if len(parts) != 2 or not parts[0].isdigit():
        raise ValueError(
            f"academic_year doit être au format 'AAAA/AAAA' (ex. '2025/2026'), reçu : {academic_year!r}"
        )
    return date(int(parts[0]), 9, 1)


def _load_recommendation_thresholds(models_dir: str) -> dict:
    path = os.path.join(models_dir, "recommendation_thresholds.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _ingest_and_clean(raw_dir: str) -> tuple[pd.DataFrame, int, list[dict], list[dict], list[dict]]:
    """Étapes A+B : parse tous les .xlsx puis nettoie. Renvoie (table longue
    nettoyée avec PII, nb fichiers découverts, fichiers en quarantaine,
    anomalies de bornes, doublons)."""
    files = discover_xlsx(raw_dir)
    parsed_ok, quarantined = [], []
    for f in files:
        parsed = parse_file(f)
        if not parsed.ok or any(i["code"] in BLOCKING_ISSUE_CODES for i in parsed.issues):
            quarantined.append({"source_file": os.path.basename(f), "issues": parsed.issues})
        else:
            parsed_ok.append(parsed)

    all_records = [rec for p in parsed_ok for rec in p.records]
    if not all_records:
        raise ValueError(
            f"Aucun enregistrement élève exploitable dans {raw_dir!r} "
            f"({len(files)} fichier(s) découvert(s), {len(quarantined)} en quarantaine)."
        )

    df = build_long_dataframe(all_records)
    df, bounds_anomalies = apply_bounds_check(df)
    df, duplicate_anomalies = detect_duplicates(df)

    return df, len(files), quarantined, bounds_anomalies, duplicate_anomalies


def _score_risk_and_regression(profile: pd.DataFrame, df_agg: pd.DataFrame, models_dir: str) -> pd.DataFrame:
    """Applique les modèles déjà ajustés (aucun .fit()) aux features précoces
    (C1/C2 uniquement, cf. models.early_features — même frontière anti-fuite
    qu'à l'entraînement)."""
    early = build_early_profile(df_agg)
    identity_cols = profile[["student_pseudo", "niveau", "classe", "nb_matieres_suivies"]]
    X = identity_cols.merge(early, on="student_pseudo", how="left")
    X = X.set_index("student_pseudo").reindex(columns=EARLY_FEATURE_COLUMNS)

    clf = joblib.load(os.path.join(models_dir, f"{RETAINED_CLASSIFIER}.joblib"))
    reg = joblib.load(os.path.join(models_dir, f"{RETAINED_REGRESSOR}.joblib"))

    out = profile.set_index("student_pseudo").copy()
    out["a_risque_predit"] = pd.Series(clf.predict(X), index=X.index).astype(bool)
    out["probabilite_risque"] = pd.Series(clf.predict_proba(X)[:, 1], index=X.index)
    out["moyenne_generale_predite"] = pd.Series(reg.predict(X), index=X.index)
    return out.reset_index()


def _assign_clusters(profile: pd.DataFrame, models_dir: str) -> tuple[pd.DataFrame, dict]:
    """Affectation au centroïde le plus proche, par niveau (cf. note de module
    en tête de fichier pour la justification et les limites de cette approche)."""
    frames = []
    exclusions: dict[str, int] = {}
    for niveau, feature_cols in FEATURES_BY_NIVEAU.items():
        bundle_path = os.path.join(models_dir, f"clustering_{niveau}.joblib")
        df_niveau = profile[profile["niveau"] == niveau]
        if not os.path.exists(bundle_path):
            exclusions[niveau] = len(df_niveau)
            continue
        bundle = joblib.load(bundle_path)
        df_ok = df_niveau.dropna(subset=feature_cols).reset_index(drop=True)
        exclusions[niveau] = len(df_niveau) - len(df_ok)
        if len(df_ok) == 0:
            continue
        frames.append(assign_to_nearest_centroid(bundle, df_ok))

    if frames:
        clusters = pd.concat(frames, ignore_index=True)
    else:
        clusters = pd.DataFrame(columns=["student_pseudo", "niveau", "cluster_id", "cluster_label", "pca_1", "pca_2"])
    return clusters, exclusions


def _build_recommendations(profile: pd.DataFrame, df_agg: pd.DataFrame, models_dir: str) -> list[dict]:
    domain_trends = compute_domain_trends(df_agg)
    dispersion_seuils = _load_recommendation_thresholds(models_dir)
    seuils_source = "persisted"
    if not dispersion_seuils:
        # Repli si jamais aucun entraînement complet n'a encore tourné (ne
        # devrait pas arriver en usage normal : run_import suppose des
        # modèles déjà entraînés). Recalculer sur un petit nouvel import
        # serait statistiquement fragile — signalé explicitement.
        dispersion_seuils = profile.groupby("niveau")["dispersion_intermatiere"].quantile(0.75).to_dict()
        seuils_source = "recomputed_fallback"

    recommendations = []
    for _, row in profile.iterrows():
        trends = domain_trends.get(row["student_pseudo"], {})
        seuil = dispersion_seuils.get(row["niveau"], np.inf)
        for rec in generate_recommendations(row, seuil, trends):
            recommendations.append(
                {
                    "student_pseudo": row["student_pseudo"],
                    "niveau": row["niveau"],
                    "classe": row["classe"],
                    "priorite": rec["priorite"],
                    "type": rec["type"],
                    "justification": rec["justification"],
                    "action": rec["action"],
                    "matieres_concernees": [MATIERES_FR.get(m, m) for m in rec["matieres_concernees"]],
                }
            )
    return recommendations, seuils_source


def run_import(raw_dir: str, academic_year: str, models_dir: str = MODELS_DIR) -> dict:
    """Score-only : de raw_dir à risque/moyenne prédite/cluster/recommandations,
    sans jamais appeler .fit() sur quoi que ce soit. Renvoie un dict de
    résultats en mémoire (aucune écriture disque)."""
    reference_date = _reference_date(academic_year)

    # --- A + B : ingestion, nettoyage ---
    df, n_files_discovered, quarantined, bounds_anomalies, duplicate_anomalies = _ingest_and_clean(raw_dir)

    # --- C : anonymisation (sel partagé — cf. note de module) ---
    df_pseudo = anonymize_dataframe(df, reference_date)
    assert_no_pii(df_pseudo)
    identity_mapping = build_identity_mapping(df, reference_date)

    # --- D : agrégats par matière ---
    df_agg = add_subject_aggregates(df_pseudo)

    # --- Couverture (classe x matière), même notion qu'à l'étape B du
    # pipeline d'entraînement (data_quality_report.json) — calculée ici sur
    # les colonnes niveau/classe/matiere, qui survivent intactes à
    # l'anonymisation (seules les colonnes PII sont retirées).
    all_niveaux = sorted(df_agg["niveau"].dropna().unique().tolist())
    all_classes = sorted(df_agg["classe"].dropna().unique().tolist())
    all_matieres = list(MATIERES_FR.keys())
    coverage = build_coverage_matrix(df_agg, all_niveaux, all_classes, all_matieres)
    coverage_counts = coverage["statut"].value_counts().to_dict()

    # --- E : profil élève (table large) ---
    profile, profile_issues = build_student_profile(df_agg)

    # Cible "à risque" OBSERVÉE : règle déterministe (targets.py), pas un
    # modèle — toujours recalculée exactement pareil, aucune persistance requise.
    profile = add_risk_label(profile)

    # --- Score-only : classification + régression (modèles déjà ajustés) ---
    profile = _score_risk_and_regression(profile, df_agg, models_dir)

    # --- Score-only : clustering (centroïde le plus proche) ---
    clusters, cluster_exclusions = _assign_clusters(profile, models_dir)
    profile = profile.merge(
        clusters[["student_pseudo", "cluster_id", "cluster_label", "pca_1", "pca_2"]],
        on="student_pseudo",
        how="left",
    )

    # --- Recommandations (règles + risque observé + cluster + tendances) ---
    recommendations, dispersion_seuils_source = _build_recommendations(profile, df_agg, models_dir)

    return {
        "academic_year": academic_year,
        "reference_date": reference_date.isoformat(),
        "n_files_discovered": n_files_discovered,
        "n_files_parsed_ok": n_files_discovered - len(quarantined),
        "n_files_quarantined": len(quarantined),
        "n_students": len(profile),
        "n_a_risque_observe": int(profile["a_risque"].sum()),
        "n_a_risque_predit": int(profile["a_risque_predit"].sum()),
        "n_recommendations": len(recommendations),
        "cluster_exclusions": cluster_exclusions,
        "dispersion_seuils_source": dispersion_seuils_source,
        "quarantined_files": quarantined,
        "n_anomalies_bornes": len(bounds_anomalies),
        "n_doublons": len(duplicate_anomalies),
        "profile_issues": profile_issues,
        "coverage_counts": coverage_counts,
        "niveaux": all_niveaux,
        "classes": all_classes,
        "matieres": all_matieres,
        # Données en mémoire pour un futur backend / tests — jamais écrites sur
        # disque par cette fonction.
        "profile": profile,
        "identity_mapping": identity_mapping,
        "notes_long_pseudo": df_pseudo,
        "notes_long_aggregated": df_agg,
        "coverage": coverage,
        "recommendations": recommendations,
    }


def _print_summary(result: dict) -> None:
    print("=== Score-only : résumé de l'import ===")
    print(f"Année scolaire            : {result['academic_year']} (référence {result['reference_date']})")
    print(f"Fichiers découverts       : {result['n_files_discovered']}")
    print(f"Fichiers en quarantaine   : {result['n_files_quarantined']}")
    print(f"Élèves                    : {result['n_students']}")
    print(f"À risque (observé)        : {result['n_a_risque_observe']}")
    print(f"À risque (prédit modèle)  : {result['n_a_risque_predit']}")
    print(f"Recommandations générées  : {result['n_recommendations']} (seuils dispersion : {result['dispersion_seuils_source']})")
    print(f"Anomalies notes hors bornes : {result['n_anomalies_bornes']}")
    print(f"Doublons élève/classe/matière : {result['n_doublons']}")
    print(f"Couverture (classe x matière) : {result['coverage_counts']}")
    print("Exclusions clustering (valeurs manquantes/modèle absent) par niveau :")
    for niveau, n in result["cluster_exclusions"].items():
        print(f"  {niveau}: {n}")
    if result["quarantined_files"]:
        print("Fichiers en quarantaine (détail) :")
        for q in result["quarantined_files"]:
            print(f"  - {q['source_file']}: {[i['code'] for i in q['issues']]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--academic-year", required=True, help="Format 'AAAA/AAAA', ex. 2025/2026")
    args = parser.parse_args()
    result = run_import(args.raw_dir, args.academic_year)
    _print_summary(result)
