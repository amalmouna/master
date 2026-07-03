"""Étape 8 — traduction des features précoces en formulations pédagogiques FR.

Chaque feature continue a deux formulations, selon le signe de sa contribution :
`risque` quand elle pousse vers un risque plus élevé / une moyenne plus basse,
`protecteur` dans le sens inverse. Les features catégorielles (niveau, classe)
sont neutres (contexte, pas un facteur "faible/fort")."""
from __future__ import annotations

MATIERES_FR = {
    "MATHEMATIQUES": "Mathématiques",
    "PHYSIQUE CHIMIE": "Physique-Chimie",
    "SC. DE LA VIE ET DE LA TERRE": "SVT",
    "LANGUE ARABE": "Arabe",
    "LANGUE FRANCAISE": "Français",
    "LANGUE ANGLAISE": "Anglais",
    "HISTOIRE GEOGRAPHIE": "Histoire-Géographie",
}
DOMAINES_FR = {
    "scientifique": "les matières scientifiques (Maths/PC/SVT)",
    "linguistique": "les langues (Arabe/Français/Anglais)",
    "sciences_humaines": "l'Histoire-Géographie",
}


def _matiere_template(matiere: str) -> dict:
    fr = MATIERES_FR.get(matiere, matiere)
    return {
        "risque": f"une moyenne précoce faible en {fr}",
        "protecteur": f"une bonne moyenne précoce en {fr}",
    }


def _domaine_template(domaine: str) -> dict:
    fr = DOMAINES_FR.get(domaine, domaine)
    return {
        "risque": f"un niveau précoce faible en {fr}",
        "protecteur": f"un bon niveau précoce en {fr}",
    }


CONTINUOUS_TEMPLATES = {
    "early_generale": {
        "risque": "un niveau général faible dès les premiers contrôles",
        "protecteur": "un bon niveau général dès les premiers contrôles",
    },
    "early_dispersion": {
        "risque": "une forte irrégularité entre les matières dès les premiers contrôles",
        "protecteur": "une bonne régularité entre les matières dès les premiers contrôles",
    },
    "early_tendance_globale": {
        "risque": "une baisse de niveau entre le premier et le deuxième contrôle",
        "protecteur": "une progression entre le premier et le deuxième contrôle",
    },
    "nb_matieres_suivies": {
        "risque": "un nombre réduit de matières suivies",
        "protecteur": "un profil multidisciplinaire complet",
    },
}


def phrase_for_feature(feature_name: str, direction: str) -> str | None:
    """direction ∈ {'risque', 'protecteur'}. Renvoie None pour une feature
    catégorielle (niveau/classe) : traitée séparément comme contexte, pas comme
    facteur explicatif graduel."""
    if feature_name.startswith("early_moy_"):
        matiere = feature_name.replace("early_moy_", "")
        return _matiere_template(matiere)[direction]
    if feature_name.startswith("early_") and feature_name.replace("early_", "") in {
        "scientifique",
        "linguistique",
        "sciences_humaines",
    }:
        domaine = feature_name.replace("early_", "")
        return _domaine_template(domaine)[direction]
    if feature_name in CONTINUOUS_TEMPLATES:
        return CONTINUOUS_TEMPLATES[feature_name][direction]
    return None
