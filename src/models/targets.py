"""Étape F — définition des cibles, sans fuite.

Cible classification « à risque » (définition C, validée sur données réelles) :
    à risque ⇔ moyenne_generale < PASSING_GRADE
             OU (nb_matieres_sous_10 / nb_matieres_suivies) ≥ PROPORTION_THRESHOLD

- PASSING_GRADE = 10/20 : barre pédagogique fixe (note de passage marocaine), non arbitraire.
- PROPORTION_THRESHOLD : seuil unique documenté et paramétrable (défaut 0.5).
  La proportion (et non le compte brut) évite le biais structurel contre les élèves
  à profil partiel (ex. classes 1APIC sans Maths/PC), qui ne peuvent pas atteindre un
  compte absolu élevé faute de matières.

Cible régression : moyenne_generale courante.

FUITE — colonnes interdites comme features (elles déterminent mécaniquement la cible
ou en dérivent) : moyenne_generale, moyennes par matière/domaine, nb_matieres_sous_10,
matiere_min/max, dispersion_intermatiere, ET remarque_encodee (jugement enseignant
dérivé des mêmes notes). La liste admissible de features est fixée à l'étape modèle.
"""
from __future__ import annotations

import pandas as pd

PASSING_GRADE = 10.0
PROPORTION_THRESHOLD = 0.5

TARGET_RISK = "a_risque"
TARGET_REGRESSION = "moyenne_generale"

# Colonnes à ne jamais passer en feature (fuite directe vers la cible).
LEAKAGE_COLUMNS = [
    "moyenne_generale",
    "moyenne_scientifique",
    "moyenne_linguistique",
    "moyenne_sciences_humaines",
    "nb_matieres_sous_10",
    "matiere_min",
    "matiere_max",
    "matiere_min_nom",
    "matiere_max_nom",
    "dispersion_intermatiere",
    "remarque_encodee",
    TARGET_RISK,
]


def add_risk_label(
    df: pd.DataFrame,
    passing_grade: float = PASSING_GRADE,
    proportion_threshold: float = PROPORTION_THRESHOLD,
) -> pd.DataFrame:
    out = df.copy()
    below_avg = out[TARGET_REGRESSION] < passing_grade
    proportion_below = out["nb_matieres_sous_10"] / out["nb_matieres_suivies"]
    polarise = proportion_below >= proportion_threshold
    out[TARGET_RISK] = (below_avg | polarise).astype(int)
    return out


def risk_config(
    passing_grade: float = PASSING_GRADE, proportion_threshold: float = PROPORTION_THRESHOLD
) -> dict:
    return {
        "definition": "C",
        "regle": "moyenne_generale < passing_grade OU (nb_matieres_sous_10 / nb_matieres_suivies) >= proportion_threshold",
        "passing_grade": passing_grade,
        "proportion_threshold": proportion_threshold,
        "cible_regression": TARGET_REGRESSION,
        "colonnes_fuite_exclues": LEAKAGE_COLUMNS,
    }
