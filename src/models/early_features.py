"""Étapes 6-7 — construction des features « précoces » (sans fuite), partagée
entre la classification à risque et la régression de moyenne_generale.

Frontière de fuite (cf. targets.py) : la cible `a_risque` et `moyenne_generale`
sont des fonctions de `moyenne_matiere`, qui moyenne TOUTES les composantes
disponibles par fichier (C1..C4, Activités). Utiliser `moyenne_matiere`, les
moyennes de domaine, `dispersion_intermatiere` ou `tendance_globale` (étape D/E)
comme features reviendrait à prédire la cible à partir d'elle-même.

Ce module reconstruit donc des features à partir des SEULES composantes C1 et C2
(quasi universellement saisies dès le début du semestre, cf. rapport de qualité
étape A/B), en ignorant complètement C3, C4 et Activités — qui sont soit du même
ordre temporel que la cible, soit partiellement utilisés dans sa définition.
Ce ne sont pas de simples alias des features de l'étape E : `early_moy_<matiere>`
(moyenne de C1,C2) diffère structurellement de `moyenne_matiere` (moyenne de
toutes les composantes présentes) dès que C3/C4/Activités existent pour ce fichier.

Structurelles et non dérivées des notes (donc jamais des fuites) : `niveau`,
`classe`, `nb_matieres_suivies` (compte de matières suivies, déterminé par le
programme/les fichiers disponibles, pas par les notes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DOMAINES = {
    "scientifique": ["MATHEMATIQUES", "PHYSIQUE CHIMIE", "SC. DE LA VIE ET DE LA TERRE"],
    "linguistique": ["LANGUE ARABE", "LANGUE FRANCAISE", "LANGUE ANGLAISE"],
    "sciences_humaines": ["HISTOIRE GEOGRAPHIE"],
}

EARLY_NUMERIC_FEATURES = [
    "early_moy_MATHEMATIQUES",
    "early_moy_PHYSIQUE CHIMIE",
    "early_moy_SC. DE LA VIE ET DE LA TERRE",
    "early_moy_LANGUE ARABE",
    "early_moy_LANGUE FRANCAISE",
    "early_moy_LANGUE ANGLAISE",
    "early_moy_HISTOIRE GEOGRAPHIE",
    "early_scientifique",
    "early_linguistique",
    "early_sciences_humaines",
    "early_generale",
    "early_dispersion",
    "early_tendance_globale",
    "nb_matieres_suivies",
]
EARLY_CATEGORICAL_FEATURES = ["niveau", "classe"]
EARLY_FEATURE_COLUMNS = EARLY_NUMERIC_FEATURES + EARLY_CATEGORICAL_FEATURES


def build_early_long(df_long: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (élève, matière) : moyenne et delta calculés sur C1,C2 uniquement."""
    out = df_long.copy()
    out["early_moyenne"] = out[["c1", "c2"]].mean(axis=1, skipna=True)
    out["early_delta"] = out["c2"] - out["c1"]
    return out


def build_early_profile(df_long: pd.DataFrame) -> pd.DataFrame:
    early_long = build_early_long(df_long)

    wide_moy = early_long.pivot_table(
        index="student_pseudo", columns="matiere", values="early_moyenne", aggfunc="first"
    )
    wide_moy.columns = [f"early_moy_{c}" for c in wide_moy.columns]

    wide_delta = early_long.pivot_table(
        index="student_pseudo", columns="matiere", values="early_delta", aggfunc="first"
    )

    profile = wide_moy.copy()
    subject_cols = list(wide_moy.columns)

    for domaine, matieres in DOMAINES.items():
        cols = [f"early_moy_{m}" for m in matieres if f"early_moy_{m}" in subject_cols]
        profile[f"early_{domaine}"] = profile[cols].mean(axis=1, skipna=True) if cols else np.nan

    profile["early_generale"] = profile[subject_cols].mean(axis=1, skipna=True)
    profile["early_dispersion"] = profile[subject_cols].std(axis=1, skipna=True, ddof=1)
    profile["early_tendance_globale"] = wide_delta.mean(axis=1, skipna=True)

    return profile.reset_index()


def assemble_dataset(df_long: pd.DataFrame, profile_labeled: pd.DataFrame) -> pd.DataFrame:
    """Assemble les features précoces avec identité/cible/split UNIQUEMENT
    (niveau, classe, nb_matieres_suivies, a_risque, split) — aucune moyenne de
    matière/domaine, aucune dispersion, aucune tendance de l'étape E n'est reprise."""
    early = build_early_profile(df_long)
    safe_cols = ["student_pseudo", "niveau", "classe", "nb_matieres_suivies", "a_risque", "split"]
    identity = profile_labeled[safe_cols]
    dataset = identity.merge(early, on="student_pseudo", how="left")
    return dataset


def assemble_regression_dataset(
    df_long: pd.DataFrame, profile_labeled: pd.DataFrame, clusters: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Comme assemble_dataset, mais pour la régression : ajoute `moyenne_generale`
    (la CIBLE, jamais une feature) et le profil de cluster de l'étape 5 (pour
    l'analyse d'erreur par profil), sans réintroduire de moyenne/domaine/dispersion
    de l'étape E dans les features."""
    early = build_early_profile(df_long)
    safe_cols = [
        "student_pseudo",
        "niveau",
        "classe",
        "nb_matieres_suivies",
        "moyenne_generale",
        "split",
    ]
    identity = profile_labeled[safe_cols]
    dataset = identity.merge(early, on="student_pseudo", how="left")
    if clusters is not None:
        dataset = dataset.merge(
            clusters[["student_pseudo", "cluster_label"]], on="student_pseudo", how="left"
        )
    return dataset
