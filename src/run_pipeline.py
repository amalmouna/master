"""Orchestrateur bout-en-bout : Étapes A -> 9, de data/raw/ à tous les artefacts.

Usage : python src/run_pipeline.py [--raw-dir CHEMIN]
Doit être exécuté depuis la racine du dépôt : chaque étape lit/écrit dans
data/processed/ et data/artifacts/ avec des chemins relatifs fixes.

Déterminisme : tous les random_state sont fixés à 42 dans chaque étape
(split, clustering, CV, modèles). Le sel de pseudonymisation (étape C) est
persisté dans data/artifacts/.salt et réutilisé d'un run à l'autre — mêmes
pseudonymes à chaque régénération complète, tant que ce fichier n'est pas
supprimé. Chaque étape réécrit ses fichiers de sortie en place : relancer le
pipeline est idempotent (pas de purge nécessaire).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STAGES = [
    ("A-C : ingestion, nettoyage, anonymisation", "pipeline_run"),
    ("D : agrégats par matière", "features.run_stage_d"),
    ("E : profil élève (table large)", "features.run_stage_e"),
    ("F : cibles + split train/test", "models.run_stage_f"),
    ("5 : clustering des profils", "models.run_stage5_clustering"),
    ("6 : classification à risque", "models.run_stage6_classification"),
    ("7 : régression de moyenne_generale", "models.run_stage7_regression"),
    ("8 : explicabilité", "explainability.run_stage8_explainability"),
    ("9 : recommandations pédagogiques", "recommendation.run_stage9_recommendations"),
]


def main(raw_dir: str) -> None:
    t0 = time.time()
    for label, module_path in STAGES:
        t_stage = time.time()
        print(f"\n{'=' * 70}\n[{label}]\n{'=' * 70}")
        module = __import__(module_path, fromlist=["run"])
        if module_path == "pipeline_run":
            module.run(raw_dir, "data/processed", "data/artifacts")
        else:
            module.run()
        print(f"-- terminé en {time.time() - t_stage:.1f}s")
    print(f"\nPipeline complet (A -> 9) en {time.time() - t0:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw")
    args = parser.parse_args()
    main(args.raw_dir)
