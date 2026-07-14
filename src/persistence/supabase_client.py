"""Client REST minimal pour Supabase (PostgREST), sans dépendance au SDK officiel
(qui embarque httpx/gotrue/realtime/storage3 pour un simple loader batch — hors
propos ici). Utilise exclusivement le rôle service_role, lu depuis l'environnement,
jamais codé en dur (cf. .env.example)."""
from __future__ import annotations

import os

import requests

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"


class SupabaseRestClient:
    def __init__(self, url: str | None = None, service_role_key: str | None = None):
        url = url or os.environ.get(SUPABASE_URL_ENV)
        key = service_role_key or os.environ.get(SUPABASE_SERVICE_ROLE_KEY_ENV)
        if not url or not key:
            raise RuntimeError(
                f"Variables d'environnement manquantes : {SUPABASE_URL_ENV} et "
                f"{SUPABASE_SERVICE_ROLE_KEY_ENV} doivent être définies (jamais codées en dur). "
                f"Voir .env.example."
            )
        # Normalise : accepte l'URL de base ("https://x.supabase.co") ou une URL
        # incluant déjà "/rest/v1" (copiée depuis certains écrans du dashboard
        # Supabase) sans jamais doubler le segment de chemin.
        base = url.rstrip("/")
        if base.endswith("/rest/v1"):
            base = base[: -len("/rest/v1")]
        self.url = base
        self._session = requests.Session()
        self._session.headers.update(
            {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
        )

    def insert(
        self,
        table: str,
        rows: list[dict],
        chunk_size: int = 500,
        upsert_on_conflict: str | None = None,
    ) -> int:
        """Insère `rows` par lots. Si upsert_on_conflict est fourni, utilise la
        résolution de conflit PostgREST (upsert) sur la contrainte nommée."""
        if not rows:
            return 0
        endpoint = f"{self.url}/rest/v1/{table}"
        params = {}
        prefer = "return=minimal"
        if upsert_on_conflict:
            prefer = f"resolution=merge-duplicates,{prefer}"
            params["on_conflict"] = upsert_on_conflict

        inserted = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            resp = self._session.post(
                endpoint, params=params, headers={"Prefer": prefer}, json=chunk
            )
            if resp.status_code >= 300:
                raise RuntimeError(
                    f"Échec insertion '{table}' (lignes {i}-{i + len(chunk)}) : "
                    f"{resp.status_code} {resp.text[:500]}"
                )
            inserted += len(chunk)
        return inserted

    def select(self, table: str, params: dict[str, str]) -> list[dict]:
        """Lecture générique (ex. retrouver un model_runs existant à
        réutiliser pour un import score-only, cf. push_scored_import.py)."""
        endpoint = f"{self.url}/rest/v1/{table}"
        resp = self._session.get(endpoint, params=params)
        if resp.status_code >= 300:
            raise RuntimeError(f"Échec lecture '{table}' : {resp.status_code} {resp.text[:500]}")
        return resp.json()

    def delete(self, table: str, filters: dict[str, str]) -> None:
        """Suppression générique (ex. purger les anciennes `recommendations`
        d'un élève avant d'insérer le nouveau jeu recalculé — cette table n'a
        pas de contrainte unique permettant un upsert, contrairement à
        students/grades/clusters/predictions)."""
        endpoint = f"{self.url}/rest/v1/{table}"
        resp = self._session.delete(endpoint, params=filters, headers={"Prefer": "return=minimal"})
        if resp.status_code >= 300:
            raise RuntimeError(f"Échec suppression '{table}' : {resp.status_code} {resp.text[:500]}")

    def count(self, table: str, filters: dict[str, str] | None = None) -> int:
        """Compte les lignes visibles (via le header Content-Range PostgREST),
        filtrées par ex. {'dataset_id': 'eq.<uuid>'}."""
        endpoint = f"{self.url}/rest/v1/{table}"
        params = {"select": "*"}  # "id" n'existe pas sur toutes les tables (ex. subjects, clé "code")
        if filters:
            params.update(filters)
        resp = self._session.get(
            endpoint, params=params, headers={"Prefer": "count=exact", "Range": "0-0"}
        )
        resp.raise_for_status()
        content_range = resp.headers.get("Content-Range", "")
        if "/" not in content_range:
            raise RuntimeError(f"En-tête Content-Range absent/invalide pour '{table}': {content_range!r}")
        return int(content_range.rsplit("/", 1)[-1])
