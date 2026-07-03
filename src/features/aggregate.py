"""Étape D — agrégats par matière.

`moyenne_matiere` = moyenne des composantes réellement disponibles pour CE fichier
(colonne présente dans le schéma d'en-tête ET valeur non vide), jamais une moyenne
supposant 4 contrôles. `tendance_matiere` = pente C1->C3(->C4) uniquement quand au
moins 3 de ces points de contrôle séquentiels existent (Activités est exclu de la
tendance : ce n'est pas un point de contrôle chronologique comparable aux Ci).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MOYENNE_COMPONENTS = ["c1", "c2", "c3", "c4", "activites"]
TENDANCE_COMPONENTS = ["c1", "c2", "c3", "c4"]  # séquence chronologique du semestre


def _available_mask(row: pd.Series, components: list[str]) -> list[bool]:
    return [
        bool(row.get(f"{c}_colonne_existe", False)) and pd.notna(row.get(c))
        for c in components
    ]


def compute_moyenne_matiere(row: pd.Series) -> tuple[float, int]:
    mask = _available_mask(row, MOYENNE_COMPONENTS)
    values = [row[c] for c, m in zip(MOYENNE_COMPONENTS, mask) if m]
    if not values:
        return np.nan, 0
    return float(np.mean(values)), len(values)


def compute_tendance_matiere(row: pd.Series) -> float | None:
    mask = _available_mask(row, TENDANCE_COMPONENTS)
    points = [(i + 1, row[c]) for i, (c, m) in enumerate(zip(TENDANCE_COMPONENTS, mask)) if m]
    if len(points) < 3:
        return None
    x = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def add_subject_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    moyenne_n = out.apply(compute_moyenne_matiere, axis=1, result_type="expand")
    out["moyenne_matiere"] = moyenne_n[0]
    out["n_composantes"] = moyenne_n[1].astype(int)
    out["tendance_matiere"] = out.apply(compute_tendance_matiere, axis=1)
    return out
