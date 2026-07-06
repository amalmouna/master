"""Vérification du token Supabase du header Authorization + rôle admin.

Utilise UNIQUEMENT le token du caller (jamais le service_role) pour ces deux
appels, afin que auth.uid() se résolve côté Supabase depuis le JWT réel de
l'utilisateur : c'est ce qui permet à is_admin() (fonction SECURITY DEFINER,
cf. supabase/schema.sql) de répondre pour le bon compte, sans que ce service
n'ait besoin de connaître par avance qui est admin."""
from __future__ import annotations

import os

import requests
from fastapi import Header, HTTPException

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_ANON_KEY_ENV = "SUPABASE_ANON_KEY"


def _supabase_url() -> str:
    """Normalise l'URL de base : accepte "https://x.supabase.co" ou une URL
    incluant déjà "/rest/v1" (copiée depuis certains écrans du dashboard),
    sans jamais doubler le segment de chemin — même normalisation que
    persistence.supabase_client.SupabaseRestClient."""
    url = os.environ.get(SUPABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"{SUPABASE_URL_ENV} manquant dans l'environnement (voir backend/.env.example).")
    base = url.rstrip("/")
    if base.endswith("/rest/v1"):
        base = base[: -len("/rest/v1")]
    return base


def _anon_key() -> str:
    key = os.environ.get(SUPABASE_ANON_KEY_ENV)
    if not key:
        raise RuntimeError(f"{SUPABASE_ANON_KEY_ENV} manquant dans l'environnement (voir backend/.env.example).")
    return key


async def require_admin(authorization: str | None = Header(default=None)) -> str:
    """Dépendance FastAPI : lève 401 si le token est absent/invalide, 403 si
    l'utilisateur n'a pas le rôle admin (table user_roles). Renvoie
    l'user_id Supabase si l'accès est autorisé."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="En-tête Authorization: Bearer <token> requis.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vide.")

    url = _supabase_url()
    headers = {"apikey": _anon_key(), "Authorization": f"Bearer {token}"}

    try:
        user_resp = requests.get(f"{url}/auth/v1/user", headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Impossible de contacter Supabase Auth : {exc}") from exc
    if user_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré.")
    user_id = user_resp.json().get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token invalide (identifiant utilisateur absent).")

    try:
        role_resp = requests.post(
            f"{url}/rest/v1/rpc/is_admin",
            headers={**headers, "Content-Type": "application/json"},
            json={},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Impossible de vérifier le rôle : {exc}") from exc
    if role_resp.status_code != 200 or role_resp.json() is not True:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")

    return user_id
