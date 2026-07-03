"""Étape F — séparation train/test par élève, stratifiée sur la cible de risque.

La table large a une ligne par élève : le split au niveau des lignes est donc déjà
un split par élève, sans fuite (aucune donnée d'un même élève des deux côtés).
Le split est stratifié sur le label binaire « à risque » pour préserver la prévalence
dans les deux ensembles. Aucune standardisation ici : les transformations seront
ajustées sur le train seulement à l'étape modèle. Le test reste intact jusqu'au
rapport final ; la sélection de modèle se fait par validation croisée sur le train.
"""
from __future__ import annotations

import pandas as pd
from sklearn.model_selection import train_test_split

from models.targets import TARGET_RISK

RANDOM_STATE = 42
TEST_SIZE = 0.2


def make_split(
    df: pd.DataFrame,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
) -> pd.DataFrame:
    """Renvoie df avec une colonne `split` ∈ {train, test}, stratifiée sur a_risque."""
    train_idx, test_idx = train_test_split(
        df.index,
        test_size=test_size,
        random_state=random_state,
        stratify=df[TARGET_RISK],
    )
    out = df.copy()
    out["split"] = "train"
    out.loc[test_idx, "split"] = "test"
    return out


def split_report(df: pd.DataFrame) -> dict:
    rep = {}
    for split_name in ("train", "test"):
        sub = df[df["split"] == split_name]
        rep[split_name] = {
            "n": int(len(sub)),
            "n_a_risque": int(sub[TARGET_RISK].sum()),
            "prevalence_risque": round(float(sub[TARGET_RISK].mean()), 4),
        }
    return rep
