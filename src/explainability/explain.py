"""Étape 8 — explicabilité des modèles retenus (Logistic Regression, Ridge).

Global : importance des variables via coefficients standardisés + SHAP (valeur
absolue moyenne). Local : contribution SHAP par élève, traduite en langage
pédagogique (jamais de nom de feature brut ni de poids numérique dans le texte).
SHAP utilisé en mode linéaire exact (les deux modèles retenus sont linéaires),
sans coût d'approximation ni de dépendance lourde.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from explainability.phrases import phrase_for_feature

TOP_K = 3

# Pour chaque tâche, signe de contribution SHAP correspondant à la formulation
# "risque" (faible niveau / facteur défavorable). Classification : une
# contribution positive pousse vers la classe "à risque". Régression : une
# contribution négative tire la moyenne prédite vers le bas (même sens
# pédagogique que "risque", d'où l'utilisation des mêmes formulations).
RISK_SIGN = {"classification": 1, "regression": -1}


def get_feature_names(pipeline: Pipeline) -> list[str]:
    raw_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    return [n.split("__", 1)[1] if "__" in n else n for n in raw_names]


def _transform(pipeline: Pipeline, X: pd.DataFrame) -> np.ndarray:
    return pipeline.named_steps["preprocess"].transform(X)


def build_explainer(pipeline: Pipeline, X_background: pd.DataFrame) -> shap.Explainer:
    X_bg = _transform(pipeline, X_background)
    model = pipeline.named_steps["model"]
    return shap.LinearExplainer(model, X_bg)


def global_importance(pipeline: Pipeline, X_background: pd.DataFrame, task: str) -> pd.DataFrame:
    feature_names = get_feature_names(pipeline)
    explainer = build_explainer(pipeline, X_background)
    X_bg_transformed = _transform(pipeline, X_background)
    shap_values = explainer.shap_values(X_bg_transformed)

    model = pipeline.named_steps["model"]
    coefs = model.coef_[0] if task == "classification" else model.coef_

    df = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient_standardise": coefs,
            "shap_abs_moyen": np.abs(shap_values).mean(axis=0),
        }
    ).sort_values("shap_abs_moyen", ascending=False)
    return df.reset_index(drop=True)


def _describe_context(row: pd.Series) -> str:
    return f"élève de {row['niveau']}, classe {row['classe']}"


def local_explanation(
    pipeline: Pipeline,
    X_background: pd.DataFrame,
    X_row: pd.DataFrame,
    task: str,
    top_k: int = TOP_K,
) -> dict:
    """La formulation (« à risque » vs « non à risque ») suit la DÉCISION RÉELLE
    du modèle, jamais la composition du top-k pris isolément ni le signe brut de
    la somme SHAP par rapport au fond : en classification, la somme SHAP est
    relative à la prévalence du fond (~34.5%), donc un élève peut être « plus à
    risque que la moyenne du fond » en log-odds tout en restant sous le seuil de
    décision à 0.5 — c'est predict() qui fait foi, pas ce signe relatif.
    En régression, il n'y a pas de seuil de décision : la phrase reste relative
    au fond (« tiré vers le bas » que la moyenne typique), ce qui correspond
    exactement à la sémantique de la valeur de base SHAP."""
    feature_names = get_feature_names(pipeline)
    explainer = build_explainer(pipeline, X_background)
    X_row_transformed = _transform(pipeline, X_row)
    shap_values = explainer.shap_values(X_row_transformed)[0]
    risk_sign = RISK_SIGN[task]

    if task == "classification":
        overall_is_risque = bool(pipeline.predict(X_row)[0])
    else:
        total_shap = float(np.sum(shap_values))
        overall_is_risque = (total_shap * risk_sign) > 0

    contributions = []
    for name, value in zip(feature_names, shap_values):
        direction = "risque" if (value * risk_sign) > 0 else "protecteur"
        phrase = phrase_for_feature(name, direction)
        if phrase is not None:
            contributions.append({"feature": name, "shap": float(value), "direction": direction, "phrase": phrase})

    matching = [c for c in contributions if (c["direction"] == "risque") == overall_is_risque]
    matching.sort(key=lambda c: abs(c["shap"]), reverse=True)
    top = matching[:top_k]
    top_phrases = [c["phrase"] for c in top]

    context = _describe_context(X_row.iloc[0])
    if task == "classification":
        texte = (
            f"Risque lié surtout à {_join_fr(top_phrases)} ({context})."
            if overall_is_risque
            else f"Profil non à risque, porté par {_join_fr(top_phrases)} ({context})."
        )
    else:  # regression
        texte = (
            f"Moyenne prédite tirée vers le bas par {_join_fr(top_phrases)} ({context})."
            if overall_is_risque
            else f"Moyenne prédite soutenue par {_join_fr(top_phrases)} ({context})."
        )

    return {
        "texte": texte,
        "sens_global": "risque" if overall_is_risque else "protecteur",
        "facteurs_retenus": top,
    }


def _join_fr(phrases: list[str]) -> str:
    if not phrases:
        return "aucun facteur dominant identifié"
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " et " + phrases[-1]
