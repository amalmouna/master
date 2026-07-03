"""Étape B — nettoyage automatique de la table longue issue de l'ingestion.

Règles (voir docs/PROMPT.md section 3, étape B) :
- notes hors [0, 20] -> NaN + anomalie (jamais d'écrasement silencieux) ;
- doublons (même élève, même classe, même matière) -> quarantaine, pas de moyenne aveugle ;
- distinction composante-non-saisie / matière-hors-curriculum / fichier-absent, gérée ici
  pour le rapport de qualité et la matrice de couverture (le calcul des moyennes disponibles
  se fait à l'étape D, pas ici).
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

NOTE_COLUMNS = ["c1", "c2", "c3", "c4", "activites"]


def _strip_multi_space(s: str) -> str:
    s = s.replace("\t", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean_text_field(v):
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    v = unicodedata.normalize("NFC", v)
    return _strip_multi_space(v)


def parse_note(v):
    """Convertit une note en float ; gère virgule décimale ; renvoie NaN si non numérique."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        v2 = v.strip().replace(",", ".")
        try:
            return float(v2)
        except ValueError:
            return np.nan
    return np.nan


def build_long_dataframe(all_records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(all_records)
    for col in ["student_code", "nom_complet", "matiere", "classe", "niveau", "remarque"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_text_field)
    for col in NOTE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(parse_note)
    return df


def apply_bounds_check(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Toute note hors [0, 20] devient NaN ; journalisée comme anomalie, jamais corrigée en silence."""
    anomalies = []
    df = df.copy()
    for col in NOTE_COLUMNS:
        if col not in df.columns:
            continue
        mask = df[col].notna() & ((df[col] < 0) | (df[col] > 20))
        for idx in df.index[mask]:
            anomalies.append(
                {
                    "type": "NOTE_HORS_BORNES",
                    "student_code": df.at[idx, "student_code"],
                    "classe": df.at[idx, "classe"],
                    "matiere": df.at[idx, "matiere"],
                    "composante": col,
                    "valeur": df.at[idx, col],
                    "source_file": df.at[idx, "source_file"],
                }
            )
        df.loc[mask, col] = np.nan
    return df, anomalies


def detect_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Même élève + même classe + même matière en double -> quarantaine (pas de moyenne aveugle).
    Le même élève dans des matières différentes est normal (clé de jointure du profil)."""
    key_cols = ["student_code", "classe", "matiere"]
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    duplicates_log = []
    if dup_mask.any():
        dup_rows = df[dup_mask]
        for keys, group in dup_rows.groupby(key_cols):
            duplicates_log.append(
                {
                    "type": "DOUBLON_ELEVE_MATIERE",
                    "student_code": keys[0],
                    "classe": keys[1],
                    "matiere": keys[2],
                    "n_occurrences": len(group),
                    "source_files": group["source_file"].tolist(),
                }
            )
    df_clean = df[~dup_mask].copy()
    return df_clean, duplicates_log


def build_curriculum_map(df: pd.DataFrame) -> dict[str, set[str]]:
    """Carte de curriculum dérivée des données : une matière est réputée au programme
    d'un niveau si au moins une classe de ce niveau dispose d'un fichier pour cette
    matière. Une matière totalement absente d'un niveau est traitée comme hors
    curriculum pour ce niveau (hypothèse à documenter, cf. limites)."""
    curriculum = {}
    for niveau, group in df.groupby("niveau"):
        curriculum[niveau] = set(group["matiere"].dropna().unique())
    return curriculum


def build_coverage_matrix(
    df: pd.DataFrame,
    all_niveaux: list[str],
    all_classes: list[str],
    all_matieres: list[str],
) -> pd.DataFrame:
    curriculum = build_curriculum_map(df)
    classe_to_niveau = df.drop_duplicates("classe").set_index("classe")["niveau"].to_dict()
    present_pairs = set(zip(df["classe"], df["matiere"]))

    rows = []
    for classe in all_classes:
        niveau = classe_to_niveau.get(classe)
        for matiere in all_matieres:
            if (classe, matiere) in present_pairs:
                statut = "present"
            elif niveau is not None and matiere not in curriculum.get(niveau, set()):
                statut = "non_au_programme"
            else:
                statut = "manquant"
            rows.append({"classe": classe, "niveau": niveau, "matiere": matiere, "statut": statut})
    return pd.DataFrame(rows)
