"""Étape 9 — moteur de recommandations pédagogiques.

Combine règles pédagogiques explicites + sorties des modèles (statut de risque)
+ profil de cluster. Deux principes non négociables :
- Les recommandations ne portent QUE sur des matières réellement suivies par
  l'élève : chaque règle de domaine est gardée par `notna` de la moyenne de
  domaine, et `matieres_concernees` est filtré sur les matières suivies ET faibles
  — jamais la liste canonique du domaine. Un élève de 1APIC sans curriculum
  scientifique ne reçoit aucune recommandation de sciences.
- Les justifications s'appuient sur des moyennes OBSERVÉES uniquement. La
  prédiction Ridge est exposée à part (`tendance_previsionnelle`), jamais
  présentée comme un fait dans le texte de recommandation.

Hors périmètre (travaux futurs) : recommandations d'enrichissement pour les
élèves excellents/en progression.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEUIL_FRAGILE = 12.0
SEUIL_DIFFICULTE = 10.0
SEUIL_SEVERE = 8.0
TREND_FORT = 1.0
IMBALANCE_MIN = 3.0

DOMAINS = {
    "scientifique": ["MATHEMATIQUES", "PHYSIQUE CHIMIE", "SC. DE LA VIE ET DE LA TERRE"],
    "linguistique": ["LANGUE ARABE", "LANGUE FRANCAISE", "LANGUE ANGLAISE"],
    "sciences_humaines": ["HISTOIRE GEOGRAPHIE"],
}
DOMAIN_AVG_COL = {
    "scientifique": "moyenne_scientifique",
    "linguistique": "moyenne_linguistique",
    "sciences_humaines": "moyenne_sciences_humaines",
}
DOMAIN_FR = {
    "scientifique": "les matières scientifiques",
    "linguistique": "les langues",
    "sciences_humaines": "l'Histoire-Géographie",
}
MATIERES_FR = {
    "MATHEMATIQUES": "Mathématiques",
    "PHYSIQUE CHIMIE": "Physique-Chimie",
    "SC. DE LA VIE ET DE LA TERRE": "SVT",
    "LANGUE ARABE": "Arabe",
    "LANGUE FRANCAISE": "Français",
    "LANGUE ANGLAISE": "Anglais",
    "HISTOIRE GEOGRAPHIE": "Histoire-Géographie",
}

ACTIONS = {
    "soutien_scientifique": "Soutien scientifique ciblé (heures de remédiation, exercices guidés) sur les matières concernées.",
    "renforcement_linguistique": "Renforcement linguistique (compréhension et expression) sur les langues concernées.",
    "accompagnement_hist_geo": "Accompagnement méthodologique en Histoire-Géographie.",
    "suivi_personnalise": "Suivi personnalisé pour stabiliser les résultats entre les matières.",
    "orientation_equilibre": "Accompagnement adapté valorisant le point fort et soutenant le domaine faible (piste d'orientation).",
    "plan_remediation_prioritaire": "Plan de remédiation prioritaire pluridisciplinaire avec suivi rapproché.",
}


def _fr_list(matieres: list[str]) -> str:
    noms = [MATIERES_FR.get(m, m) for m in matieres]
    if len(noms) <= 1:
        return noms[0] if noms else ""
    return ", ".join(noms[:-1]) + " et " + noms[-1]


def base_severity(m: float) -> int | None:
    if m < SEUIL_SEVERE:
        return 1
    if m < SEUIL_DIFFICULTE:
        return 2
    if m < SEUIL_FRAGILE:
        return 3
    return None


def adjust_priority(base: int, a_risque: bool, trend: float | None) -> int:
    p = base
    if a_risque:
        p = max(1, p - 1)
    if trend is not None and not np.isnan(trend):
        if trend <= -TREND_FORT:
            p = max(1, p - 1)
        elif trend >= TREND_FORT:
            p = min(3, p + 1)
    return p


def _trend_clause(trend: float | None) -> str:
    if trend is None or np.isnan(trend):
        return ""
    if trend <= -TREND_FORT:
        return ", en baisse depuis le début du semestre"
    if trend >= TREND_FORT:
        return ", en progression depuis le début du semestre"
    return ""


def _weak_subjects(row: pd.Series, domaine: str, seuil: float = SEUIL_FRAGILE) -> list[str]:
    """Matières du domaine réellement suivies (moy notna) ET faibles (< seuil)."""
    out = []
    for m in DOMAINS[domaine]:
        col = f"moy_{m}"
        val = row.get(col)
        if pd.notna(val) and val < seuil:
            out.append(m)
    return out


def _domain_rule(row: pd.Series, domaine: str, rec_type: str, domain_trend: float | None) -> dict | None:
    avg_col = DOMAIN_AVG_COL[domaine]
    avg = row.get(avg_col)
    if pd.isna(avg) or avg >= SEUIL_FRAGILE:
        return None
    matieres = _weak_subjects(row, domaine)
    if not matieres:
        return None
    base = base_severity(avg)
    if base is None:
        return None
    priorite = adjust_priority(base, bool(row["a_risque"]), domain_trend)
    if len(DOMAINS[domaine]) == 1:
        # Domaine mono-matière : la moyenne de domaine EST la moyenne de la matière.
        justification = (
            f"Moyenne de {avg:.1f}/20 en {MATIERES_FR[DOMAINS[domaine][0]]}"
            f"{_trend_clause(domain_trend)}."
        )
    else:
        # Domaine multi-matières : séparer la moyenne de domaine des matières
        # faibles, sinon la moyenne pourrait être lue comme celle des matières citées.
        justification = (
            f"Moyenne de {avg:.1f}/20 dans {DOMAIN_FR[domaine]}{_trend_clause(domain_trend)} ; "
            f"matière(s) à renforcer : {_fr_list(matieres)}."
        )
    return {
        "type": rec_type,
        "priorite": priorite,
        "justification": justification,
        "action": ACTIONS[rec_type],
        "matieres_concernees": matieres,
    }


def rule_scientifique(row, trends):
    return _domain_rule(row, "scientifique", "soutien_scientifique", trends.get("scientifique"))


def rule_linguistique(row, trends):
    return _domain_rule(row, "linguistique", "renforcement_linguistique", trends.get("linguistique"))


def rule_sciences_humaines(row, trends):
    return _domain_rule(row, "sciences_humaines", "accompagnement_hist_geo", trends.get("sciences_humaines"))


def rule_dispersion(row, trends, dispersion_seuil: float) -> dict | None:
    disp = row.get("dispersion_intermatiere")
    mn = row.get("matiere_min")
    if pd.isna(disp) or disp < dispersion_seuil or pd.isna(mn) or mn >= SEUIL_DIFFICULTE:
        return None
    matiere_min_nom = row.get("matiere_min_nom")
    matieres = [matiere_min_nom] if pd.notna(matiere_min_nom) else []
    base = base_severity(mn) or 3
    priorite = adjust_priority(base, bool(row["a_risque"]), row.get("tendance_globale"))
    justification = (
        f"Résultats irréguliers entre les matières (écart-type {disp:.1f}), "
        f"avec un point faible en {_fr_list(matieres)} ({mn:.1f}/20)."
    )
    return {
        "type": "suivi_personnalise",
        "priorite": priorite,
        "justification": justification,
        "action": ACTIONS["suivi_personnalise"],
        "matieres_concernees": matieres,
    }


def rule_desequilibre(row, trends) -> dict | None:
    ling = row.get("moyenne_linguistique")
    sci = row.get("moyenne_scientifique")
    if pd.isna(ling) or pd.isna(sci):
        return None
    gap = ling - sci
    if abs(gap) < IMBALANCE_MIN:
        return None
    if sci < SEUIL_DIFFICULTE <= SEUIL_FRAGILE and ling >= SEUIL_FRAGILE:
        faible, fort, faible_avg = "scientifique", "linguistique", sci
    elif ling < SEUIL_DIFFICULTE and sci >= SEUIL_FRAGILE:
        faible, fort, faible_avg = "linguistique", "scientifique", ling
    else:
        return None
    matieres = _weak_subjects(row, faible)
    if not matieres:
        return None
    base = base_severity(faible_avg) or 2
    priorite = adjust_priority(base, bool(row["a_risque"]), trends.get(faible))
    justification = (
        f"Fort déséquilibre entre {DOMAIN_FR[fort]} ({row.get(DOMAIN_AVG_COL[fort]):.1f}/20) "
        f"et {DOMAIN_FR[faible]} ({faible_avg:.1f}/20)."
    )
    return {
        "type": "orientation_equilibre",
        "priorite": priorite,
        "justification": justification,
        "action": ACTIONS["orientation_equilibre"],
        "matieres_concernees": matieres,
    }


def rule_plan_prioritaire(row) -> dict | None:
    if not bool(row["a_risque"]) or row.get("nb_matieres_sous_10", 0) < 3:
        return None
    matieres = [
        m for m in MATIERES_FR
        if pd.notna(row.get(f"moy_{m}")) and row.get(f"moy_{m}") < SEUIL_DIFFICULTE
    ]
    justification = (
        f"Élève en difficulté sur {int(row['nb_matieres_sous_10'])} matières "
        f"(moyenne générale {row['moyenne_generale']:.1f}/20)."
    )
    return {
        "type": "plan_remediation_prioritaire",
        "priorite": 1,
        "justification": justification,
        "action": ACTIONS["plan_remediation_prioritaire"],
        "matieres_concernees": matieres,
    }


def generate_recommendations(row: pd.Series, dispersion_seuil: float, trends: dict) -> list[dict]:
    recs = []
    for rule in (rule_scientifique, rule_linguistique, rule_sciences_humaines, rule_desequilibre):
        r = rule(row, trends)
        if r:
            recs.append(r)
    r = rule_dispersion(row, trends, dispersion_seuil)
    if r:
        recs.append(r)
    r = rule_plan_prioritaire(row)
    if r:
        recs.append(r)
    recs.sort(key=lambda x: x["priorite"])
    return recs
