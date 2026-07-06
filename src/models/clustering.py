"""Étape 5 — clustering des profils.

Décision de portée (validée) : le clustering est descriptif, non supervisé, sans
cible à faire fuiter. Il utilise donc les moyennes de domaine du semestre en cours
(table large de l'étape E), pas des signaux « précoces » — cette dernière contrainte
ne vaut que pour les cibles supervisées (risque / moyenne_generale, cf. targets.py).

Clustering réalisé **par niveau**, pas globalement : le domaine scientifique est
absent pour ~51% des élèves de 1APIC (Maths et PC non présents, cf. rapport de
qualité), et non_au_programme structurel (Anglais, SVT) diffère par niveau. Mélanger
les niveaux dans un même espace standardisé comparerait des profils incomparables ;
et imputer une compétence scientifique pour des élèves sans aucune note de science
fabriquerait une donnée. Le domaine scientifique est donc exclu des features de
clustering pour 1APIC (cf. `FEATURES_BY_NIVEAU`), inclus pour 2APIC/3APIC (0% manquant).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

RANDOM_STATE = 42
K_RANGE = range(2, 7)
MIN_CLUSTER_FRACTION = 0.05
MIN_CLUSTER_SIZE_FLOOR = 5

FEATURES_BY_NIVEAU = {
    "1APIC": ["moyenne_linguistique", "moyenne_sciences_humaines", "dispersion_intermatiere", "tendance_globale"],
    "2APIC": ["moyenne_scientifique", "moyenne_linguistique", "moyenne_sciences_humaines", "dispersion_intermatiere", "tendance_globale"],
    "3APIC": ["moyenne_scientifique", "moyenne_linguistique", "moyenne_sciences_humaines", "dispersion_intermatiere", "tendance_globale"],
}

DOMAIN_LABELS_FR = {
    "scientifique": "scientifique",
    "linguistique": "linguistique",
    "sciences_humaines": "sciences humaines",
}


def _min_cluster_size(n: int) -> int:
    return max(MIN_CLUSTER_SIZE_FLOOR, int(np.ceil(MIN_CLUSTER_FRACTION * n)))


def _candidate_clusterings(X: np.ndarray, n: int) -> list[dict]:
    candidates = []
    min_size = _min_cluster_size(n)
    for algo_name, make_model in [
        ("kmeans", lambda k: KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)),
        ("agglomerative", lambda k: AgglomerativeClustering(n_clusters=k)),
    ]:
        for k in K_RANGE:
            if k >= n:
                continue
            model = make_model(k)
            labels = model.fit_predict(X)
            sizes = np.bincount(labels)
            if len(sizes) < 2 or sizes.min() < min_size:
                continue
            sil = silhouette_score(X, labels)
            candidates.append(
                {
                    "algo": algo_name,
                    "k": k,
                    "silhouette": round(float(sil), 4),
                    "sizes": sizes.tolist(),
                    "labels": labels,
                }
            )
    return candidates


def _select_best(candidates: list[dict]) -> dict:
    """Meilleur silhouette ; à égalité proche (<=0.01), préfère le k le plus petit
    puis kmeans (reproductible, déterministe avec random_state) — résultat stable et
    défendable plutôt que le plus complexe, conformément à docs/PROMPT.md section 5."""
    best_sil = max(c["silhouette"] for c in candidates)
    near_best = [c for c in candidates if best_sil - c["silhouette"] <= 0.01]
    near_best.sort(key=lambda c: (c["k"], c["algo"] != "kmeans"))
    return near_best[0]


def _domain_z_scores(cluster_means: pd.Series, population_mean: pd.Series, population_std: pd.Series, domains: list[str]) -> dict:
    z = {}
    for d in domains:
        col = f"moyenne_{d}"
        std = population_std[col] if population_std[col] > 1e-9 else 1.0
        z[d] = (cluster_means[col] - population_mean[col]) / std
    return z


def name_cluster(cluster_means: pd.Series, population_mean: pd.Series, population_std: pd.Series, feature_cols: list[str]) -> str:
    domains = [c.replace("moyenne_", "") for c in feature_cols if c.startswith("moyenne_") and c != "moyenne_generale"]

    def z(col):
        std = population_std[col] if population_std[col] > 1e-9 else 1.0
        return (cluster_means[col] - population_mean[col]) / std

    z_dispersion = z("dispersion_intermatiere")
    z_domains = _domain_z_scores(cluster_means, population_mean, population_std, domains)
    z_niveau_moyenne = float(np.mean(list(z_domains.values())))

    if z_dispersion > 0.75:
        return "irrégulier"
    if z_niveau_moyenne > 0.5 and z_dispersion <= 0.25:
        return "performant"
    if len(domains) >= 2:
        best_d = max(z_domains, key=z_domains.get)
        worst_d = min(z_domains, key=z_domains.get)
        if (z_domains[best_d] - z_domains[worst_d]) > 0.6 and z_domains[worst_d] < -0.3:
            return f"{DOMAIN_LABELS_FR[worst_d]} fragile"
    if z_niveau_moyenne < -0.5:
        return "équilibré fragile"
    return "équilibré"


def cluster_niveau(df_niveau: pd.DataFrame, feature_cols: list[str]) -> dict:
    X_raw = df_niveau[feature_cols].to_numpy(dtype=float)
    scaler = StandardScaler().fit(X_raw)
    X = scaler.transform(X_raw)

    candidates = _candidate_clusterings(X, len(df_niveau))
    if not candidates:
        raise ValueError(f"Aucune configuration de clustering valide (n={len(df_niveau)})")
    best = _select_best(candidates)
    labels = best["labels"]

    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    coords = pca.fit_transform(X)

    # Centroïdes = moyenne des points (espace standardisé) par cluster final.
    # Identique par construction à KMeans.cluster_centers_ pour l'algo kmeans
    # (c'est la définition même de l'objectif k-means à convergence) ; c'est
    # aussi le mécanisme de repli standard pour affecter un nouveau point à un
    # clustering agglomératif, qui n'a pas de .predict(). Un seul mécanisme
    # pour les deux algos, pas de branche spéciale par algo (cf. score_import.py).
    cluster_ids = sorted(set(labels))
    centroids = np.array([X[labels == cid].mean(axis=0) for cid in cluster_ids])

    pop_mean = df_niveau[feature_cols].mean()
    pop_std = df_niveau[feature_cols].std(ddof=0)
    cluster_names = {}
    for cid in cluster_ids:
        mask = labels == cid
        cmeans = df_niveau.loc[mask, feature_cols].mean()
        cluster_names[int(cid)] = name_cluster(cmeans, pop_mean, pop_std, feature_cols)

    return {
        "algo": best["algo"],
        "k": best["k"],
        "silhouette": best["silhouette"],
        "sizes": best["sizes"],
        "labels": labels,
        "pca_coords": coords,
        "pca_explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "cluster_names": cluster_names,
        "candidates_evaluated": [
            {k: v for k, v in c.items() if k != "labels"} for c in candidates
        ],
        "scaler": scaler,
        "pca_model": pca,
        "centroids": centroids,
        "cluster_ids": cluster_ids,
    }


def run_clustering(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    assignments = []
    report = {}
    models_by_niveau = {}
    for niveau, feature_cols in FEATURES_BY_NIVEAU.items():
        df_niveau = df[df["niveau"] == niveau].dropna(subset=feature_cols).reset_index(drop=True)
        n_excluded = (df["niveau"] == niveau).sum() - len(df_niveau)
        result = cluster_niveau(df_niveau, feature_cols)
        for i, row in df_niveau.iterrows():
            assignments.append(
                {
                    "student_pseudo": row["student_pseudo"],
                    "niveau": niveau,
                    "cluster_id": int(result["labels"][i]),
                    "cluster_label": result["cluster_names"][int(result["labels"][i])],
                    "pca_1": float(result["pca_coords"][i, 0]),
                    "pca_2": float(result["pca_coords"][i, 1]),
                }
            )
        report[niveau] = {
            "features": feature_cols,
            "n_eleves_clusterises": len(df_niveau),
            "n_eleves_exclus_valeurs_manquantes": int(n_excluded),
            "algo_retenu": result["algo"],
            "k_retenu": result["k"],
            "silhouette_retenu": result["silhouette"],
            "tailles_clusters": result["sizes"],
            "noms_clusters": result["cluster_names"],
            "variance_expliquee_pca_2d": result["pca_explained_variance_ratio"],
            "candidats_evalues": result["candidates_evaluated"],
        }
        # Bundle persistable pour l'affectation de nouveaux élèves sans
        # réentraînement (cf. src/score_import.py) : scaler + centroïdes +
        # PCA déjà ajustés, plus la table cluster_id -> nom déjà calculée
        # (recalculer les noms sur un nouvel import, potentiellement petit,
        # donnerait des z-scores instables par rapport à une population
        # d'entraînement de référence).
        models_by_niveau[niveau] = {
            "feature_cols": feature_cols,
            "scaler": result["scaler"],
            "pca": result["pca_model"],
            "centroids": result["centroids"],
            "cluster_ids": result["cluster_ids"],
            "cluster_names": result["cluster_names"],
            "algo": result["algo"],
            "k": result["k"],
        }
    return pd.DataFrame(assignments), report, models_by_niveau


def assign_to_nearest_centroid(bundle: dict, df_niveau: pd.DataFrame) -> pd.DataFrame:
    """Affecte de nouveaux élèves (score-only, aucun réentraînement) aux clusters
    d'un bundle persisté (cf. run_clustering). Même mécanisme pour kmeans et
    agglomerative : plus proche centroïde dans l'espace standardisé du modèle
    d'origine — exact pour kmeans (équivalent à .predict()), seul choix
    possible pour agglomerative (pas de .predict()). df_niveau doit déjà être
    filtré sur le niveau du bundle et ne contenir aucune valeur manquante sur
    feature_cols (cf. score_import.py pour la gestion des exclusions)."""
    feature_cols = bundle["feature_cols"]
    X_raw = df_niveau[feature_cols].to_numpy(dtype=float)
    X = bundle["scaler"].transform(X_raw)

    centroids = bundle["centroids"]
    cluster_ids = bundle["cluster_ids"]
    # distance euclidienne à chaque centroïde -> indice du plus proche
    dists = np.linalg.norm(X[:, None, :] - centroids[None, :, :], axis=2)
    nearest_idx = dists.argmin(axis=1)

    coords = bundle["pca"].transform(X)

    out = df_niveau[["student_pseudo"]].copy()
    out["niveau"] = df_niveau["niveau"].values
    out["cluster_id"] = [cluster_ids[i] for i in nearest_idx]
    out["cluster_label"] = [bundle["cluster_names"][cluster_ids[i]] for i in nearest_idx]
    out["pca_1"] = coords[:, 0]
    out["pca_2"] = coords[:, 1]
    return out
