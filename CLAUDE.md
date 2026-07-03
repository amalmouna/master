# Projet PFE — Analyse prédictive et recommandation pédagogique

Spec complète : `docs/PROMPT.md`. Lis-la une fois, puis suis-la. Ne la re-résume pas à chaque tour.

## Données
- Exports Massar `.xlsx` dans `data/raw/` (1 fichier par classe × matière, 1 semestre).
- Structure exacte déjà documentée en Section 1 de `docs/PROMPT.md`. Ne ré-explore pas les 75 fichiers : valide le parser sur 2–3 fichiers seulement.
- `data/raw/` contient des données nominatives — jamais commité, jamais envoyé au frontend/Supabase.

## Contraintes non négociables
- Notes sur /20 ; toute valeur hors [0,20] → quarantaine, pas d'écrasement.
- Moyenne matière = moyenne des composantes **disponibles** (C1–C4, Activités) ; ne pas supposer 4 contrôles.
- Absences 100 % vides → pas d'analyse d'assiduité. Données mono-semestre → pas d'évolution pluriannuelle.
- Distinguer matière non au programme (curriculum) vs fichier manquant.
- Anonymisation (hash de l'ID national, suppression nom/ID interne, DOB→âge) **avant** toute persistance ou export.
- Pas de fuite train/test. Baseline avant modèle avancé.

## Méthode de travail (économie de contexte)
- Écris des scripts et exécute-les ; n'inspecte pas les données en les chargeant dans la conversation. Affiche seulement de courts résumés.
- Une étape à la fois (voir Section 3 : A→G, puis ML). Après chaque étape : ce qui est fait, fichiers, résultats, limite, prochaine étape.
- Un seul agent, pas de sous-agents parallèles. Plan mode avant tout changement structurant.
- Modèle : Sonnet par défaut ; Opus seulement pour un point de raisonnement difficile.

## Stack
Pipeline Python local → artefacts pseudonymisés → Supabase → frontend Next.js sur Vercel. Aucun serveur Python sur Vercel. Aucun secret dans le dépôt (`.env.example` seulement).
