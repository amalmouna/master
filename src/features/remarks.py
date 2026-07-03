"""Encodage ordinal de la remarque enseignant.

Le prompt initial supposait 4 valeurs canoniques (FR uniquement). Les 75 fichiers
réels utilisent en fait 14 formulations distinctes réparties sur 3 langues
(français, arabe, anglais), qui se regroupent en **5** niveaux sémantiques, pas 4 :
un palier supplémentaire ("Très insuffisant / très faible") existe sous "Travail
faible". Feature secondaire : bon prédicteur mais dérivée des mêmes notes, donc
exclue de toute cible (cf. docs/PROMPT.md section 1.5 et 7).
"""
from __future__ import annotations

# 0 = le plus faible, 4 = le plus fort.
REMARK_ORDINAL_MAP = {
    # Palier 4 - excellent
    "Excellent travail, continue ainsi": 4,
    "Excellent work, keep it up": 4,
    "عمل ممتاز، واصل": 4,
    # Palier 3 - très bien
    "Très bien, encore des efforts": 3,
    "Very good work, keep up the effort": 3,
    "جيد جدًا، مزيدا من الجهد": 3,
    # Palier 2 - bon
    "Bon travail, peut s'améliorer": 2,
    "Good work, but it can be improved": 2,
    "عمل جيد، اجتهد أكثر": 2,
    # Palier 1 - travail faible
    "Travail faible, fais attention": 1,
    "Weak work, try to be more careful": 1,
    "عمل ضعيف، اجتهد أكثر": 1,
    # Palier 0 - très insuffisant
    "Très insuffisant, besoin d'aide": 0,
    "ضعيف جدًا، اجتهد أكثر": 0,
}


def encode_remarque(text) -> int | None:
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    return REMARK_ORDINAL_MAP.get(text)  # None si formulation inconnue -> à journaliser
