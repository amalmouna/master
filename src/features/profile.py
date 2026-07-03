"""Étape E — table large : un profil multidisciplinaire par élève.

Règle non négociable : toute moyenne (matière, domaine, générale) se calcule
uniquement sur les matières que l'élève suit réellement. Une matière absente du
programme de son niveau n'est jamais imputée à 0 ni comptée contre lui — elle est
simplement absente du calcul (skipna).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features.remarks import encode_remarque

DOMAINES = {
    "scientifique": ["MATHEMATIQUES", "PHYSIQUE CHIMIE", "SC. DE LA VIE ET DE LA TERRE"],
    "linguistique": ["LANGUE ARABE", "LANGUE FRANCAISE", "LANGUE ANGLAISE"],
    "sciences_humaines": ["HISTOIRE GEOGRAPHIE"],
}

IDENTITY_COLS = ["student_pseudo", "niveau", "classe", "tranche_age"]


def _check_identity_consistency(df: pd.DataFrame) -> list[dict]:
    """Un élève doit avoir un niveau/classe unique sur tout son semestre.
    Journalise les incohérences plutôt que de les résoudre à l'aveugle."""
    issues = []
    grouped = df.groupby("student_pseudo")[["niveau", "classe"]].nunique()
    inconsistent = grouped[(grouped["niveau"] > 1) | (grouped["classe"] > 1)]
    for student_pseudo in inconsistent.index:
        issues.append(
            {
                "type": "IDENTITE_INCOHERENTE",
                "student_pseudo": student_pseudo,
                "detail": "niveau/classe multiples pour le même élève",
            }
        )
    return issues


def _first_non_null(series: pd.Series):
    non_null = series.dropna()
    return non_null.iloc[0] if len(non_null) else None


def build_student_profile(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    issues = _check_identity_consistency(df)

    identity = (
        df.groupby("student_pseudo")
        .agg(
            niveau=("niveau", _first_non_null),
            classe=("classe", _first_non_null),
            tranche_age=("tranche_age", _first_non_null),
        )
        .reset_index()
    )

    moyennes_wide = df.pivot_table(
        index="student_pseudo", columns="matiere", values="moyenne_matiere", aggfunc="first"
    )
    moyennes_wide.columns = [f"moy_{c}" for c in moyennes_wide.columns]

    tendances_wide = df.pivot_table(
        index="student_pseudo", columns="matiere", values="tendance_matiere", aggfunc="first"
    )

    profile = identity.set_index("student_pseudo").join(moyennes_wide, how="left")

    subject_cols = list(moyennes_wide.columns)

    for domaine, matieres in DOMAINES.items():
        cols = [f"moy_{m}" for m in matieres if f"moy_{m}" in subject_cols]
        profile[f"moyenne_{domaine}"] = profile[cols].mean(axis=1, skipna=True) if cols else np.nan

    profile["moyenne_generale"] = profile[subject_cols].mean(axis=1, skipna=True)
    profile["nb_matieres_suivies"] = profile[subject_cols].notna().sum(axis=1)
    profile["nb_matieres_sous_10"] = (profile[subject_cols] < 10).sum(axis=1)
    profile["matiere_min"] = profile[subject_cols].min(axis=1, skipna=True)
    profile["matiere_max"] = profile[subject_cols].max(axis=1, skipna=True)
    profile["matiere_min_nom"] = profile[subject_cols].idxmin(axis=1, skipna=True).str.replace("moy_", "", regex=False)
    profile["matiere_max_nom"] = profile[subject_cols].idxmax(axis=1, skipna=True).str.replace("moy_", "", regex=False)
    profile["dispersion_intermatiere"] = profile[subject_cols].std(axis=1, skipna=True, ddof=1)

    profile["tendance_globale"] = tendances_wide.mean(axis=1, skipna=True)

    remarque_encodee = df.copy()
    remarque_encodee["remarque_ordinale"] = remarque_encodee["remarque"].apply(encode_remarque)
    unrecognized = remarque_encodee[
        remarque_encodee["remarque"].notna() & remarque_encodee["remarque_ordinale"].isna()
    ]
    for _, row in unrecognized.iterrows():
        issues.append(
            {
                "type": "REMARQUE_NON_RECONNUE",
                "student_pseudo": row["student_pseudo"],
                "detail": str(row["remarque"]),
            }
        )
    remarque_par_eleve = remarque_encodee.groupby("student_pseudo")["remarque_ordinale"].mean()
    profile["remarque_encodee"] = remarque_par_eleve

    profile = profile.reset_index()
    return profile, issues
