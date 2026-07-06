"""Backend FastAPI — import Massar authentifié (admin uniquement), score-only.

Lance le pipeline déjà entraîné (src/score_import.run_import) sur un nouvel
import, puis écrit le résultat dans Supabase pour l'academic_year fourni
(src/persistence/push_scored_import.push_scored_import). Ne réentraîne rien.

Les fichiers .xlsx uploadés sont écrits dans un dossier temporaire, jamais
persistés au-delà de la requête (suppression garantie via `finally`, même en
cas d'erreur) — cf. contrainte du projet : aucun fichier brut nominatif ne
doit survivre à l'import. Aucun nom/ID élève n'est journalisé : les logs ne
contiennent que des compteurs et des noms de fichiers.

Lancer localement (depuis la RACINE du dépôt, pas depuis backend/ — le sel de
pseudonymisation par défaut, data/artifacts/.salt, est résolu relativement au
cwd du process si MASSAR_SALT n'est pas fourni) :
    python -m uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_admin

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SRC_DIR)

# Chemin absolu : run_import() ne doit pas dépendre du cwd du process uvicorn
# (data/artifacts/models, relatif au dépôt, pas au dossier de lancement du serveur).
MODELS_DIR = os.path.join(REPO_ROOT, "data", "artifacts", "models")

# .env.local du backend d'abord (SUPABASE_ANON_KEY propre au backend), puis
# celui de la racine du dépôt en repli (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY
# partagés avec le loader CLI) — sans écraser une variable déjà définie.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))
load_dotenv(os.path.join(REPO_ROOT, ".env.local"))

from score_import import run_import  # noqa: E402 (après sys.path.insert, nécessaire)
from persistence.push_scored_import import push_scored_import  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend.import")

app = FastAPI(title="Import Massar — backend score-only")

# CORS : verrouillé au(x) seul(s) origine(s) du frontend Vercel, jamais "*"
# (endpoint admin qui écrit des données réelles). FRONTEND_ORIGIN — une ou
# plusieurs origines séparées par des virgules (ex. domaine de prod +
# domaines de preview Vercel) — jamais codé en dur ici : à définir dans
# backend/.env.local en local, dans les variables d'environnement Render en
# production (voir DEPLOY_BACKEND.md). Si absent, aucune origine n'est
# autorisée (échec fermé) plutôt qu'un repli permissif.
_frontend_origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGIN", "").split(",") if o.strip()]
if not _frontend_origins:
    logging.getLogger("backend.import").warning(
        "FRONTEND_ORIGIN non défini : aucune origine autorisée en CORS (échec fermé)."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/import")
async def import_endpoint(
    academic_year: str = Form(...),
    files: list[UploadFile] = File(...),
    user_id: str = Depends(require_admin),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier reçu.")

    tmp_dir = tempfile.mkdtemp(prefix="massar_import_")
    try:
        n_saved = 0
        for f in files:
            if not f.filename or not f.filename.lower().endswith(".xlsx"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Fichier rejeté (extension .xlsx attendue) : {f.filename!r}",
                )
            dest = os.path.join(tmp_dir, os.path.basename(f.filename))
            content = await f.read()
            with open(dest, "wb") as out:
                out.write(content)
            n_saved += 1

        logger.info("Import démarré : %d fichier(s) reçu(s), academic_year=%s", n_saved, academic_year)

        try:
            result = run_import(tmp_dir, academic_year, models_dir=MODELS_DIR)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            push_result = push_scored_import(result, label=f"Import {academic_year}")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        summary = {
            "dataset_id": push_result["dataset_id"],
            "academic_year": academic_year,
            "students_imported": result["n_students"],
            "n_a_risque_observe": result["n_a_risque_observe"],
            "n_a_risque_predit": result["n_a_risque_predit"],
            "coverage_counts": result["coverage_counts"],
            "n_files_discovered": result["n_files_discovered"],
            "n_files_quarantined": result["n_files_quarantined"],
            "quarantined_files": [q["source_file"] for q in result["quarantined_files"]],
        }
        logger.info(
            "Import terminé : dataset_id=%s, %d élève(s), %d en quarantaine",
            push_result["dataset_id"], result["n_students"], result["n_files_quarantined"],
        )
        return summary
    except HTTPException:
        raise
    except Exception as exc:  # garde-fou : jamais un crash brut, toujours une erreur claire
        logger.exception("Échec import (academic_year=%s)", academic_year)
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de l'import : {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
