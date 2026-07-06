"""score_import.run_import (score-only, aucun réentraînement) doit reproduire
exactement les pseudonymes et labels de risque observés des artefacts
d'entraînement commités, quand exécuté sur les mêmes données brutes. Une
divergence signalerait soit une instabilité du sel de pseudonymisation, soit
un écart de featurisation entre le pipeline d'entraînement et le score-only."""
import os

import pandas as pd
import pytest

from score_import import run_import

# Les fichiers Massar réels ne sont pas versionnés (PII) et ne vivent que dans
# le dépôt principal, pas dans ce worktree — cf. tout le fil de conversation
# du projet. Skip explicite plutôt qu'échec dans un environnement qui ne les a pas.
REAL_RAW_DIR = r"C:\Users\mouna\Documents\master\data\raw"


@pytest.mark.skipif(
    not os.path.isdir(REAL_RAW_DIR),
    reason=f"Données brutes réelles absentes ({REAL_RAW_DIR!r}) dans cet environnement.",
)
def test_run_import_reproduces_committed_pseudonyms_and_risk_labels():
    result = run_import(REAL_RAW_DIR, "2025/2026")

    committed = pd.read_csv("data/artifacts/student_profile_labeled.csv").set_index("student_pseudo")
    scored = result["profile"].set_index("student_pseudo")

    assert result["n_students"] == len(committed)

    assert set(scored.index) == set(committed.index), (
        "Les pseudonymes générés en score-only diffèrent de ceux des artefacts "
        "commités — le sel de pseudonymisation n'est pas stable entre les deux runs."
    )

    risk_scored = scored.loc[committed.index, "a_risque"].astype(int)
    risk_committed = committed["a_risque"].astype(int)
    mismatches = risk_scored[risk_scored != risk_committed]
    assert len(mismatches) == 0, (
        f"{len(mismatches)} élève(s) avec un label de risque observé (définition C) "
        f"différent de celui des artefacts d'entraînement : {list(mismatches.index[:5])}"
    )


@pytest.mark.skipif(
    not os.path.isdir(REAL_RAW_DIR),
    reason=f"Données brutes réelles absentes ({REAL_RAW_DIR!r}) dans cet environnement.",
)
def test_run_import_scores_without_retraining_artifacts():
    """Le score-only ne doit produire aucun effet de bord sur les artefacts
    d'entraînement — c'est une fonction pure (raw_dir, academic_year) -> dict."""
    import hashlib

    def _hash_file(path: str) -> str:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    watched = [
        "data/artifacts/student_profile_labeled.csv",
        "data/artifacts/notes_long_pseudo.csv",
        "data/artifacts/clusters.csv",
    ]
    before = {p: _hash_file(p) for p in watched}
    run_import(REAL_RAW_DIR, "2025/2026")
    after = {p: _hash_file(p) for p in watched}

    assert before == after, "run_import a modifié un artefact d'entraînement — il doit rester purement en mémoire."
