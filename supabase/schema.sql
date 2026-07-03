-- Étape 10 — schéma Supabase minimal, données pseudonymisées uniquement.
--
-- Portée : couche de données seulement (pas de front-end, pas d'auth utilisateur
-- pour l'instant — une table `profiles` liée à Supabase Auth sera ajoutée quand
-- la gestion multi-utilisateurs sera nécessaire). Aucune colonne de ce schéma ne
-- doit jamais recevoir de donnée nominative : student_pseudo est la seule clé
-- élève, jamais student_code/nom/id_interne (cf. src/anonymization/anonymize.py).
--
-- RLS : activé sur toutes les tables scolaires. Politique de lecture ouverte
-- (anon + authenticated) car les données sont déjà pseudonymisées — aucune fuite
-- possible via une lecture publique. Aucune politique d'écriture pour anon/
-- authenticated : seul le rôle service_role (qui contourne RLS nativement côté
-- Supabase) peut écrire, via le loader Python et sa clé hors dépôt. À resserrer
-- (politiques par établissement/rôle) si l'outil devient multi-établissement.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- datasets : un import = un semestre. Traçabilité (§2.8).
-- ---------------------------------------------------------------------------
create table if not exists datasets (
    id uuid primary key,
    label text not null,                -- ex. "2025-2026 Semestre 1"
    annee_scolaire text,
    semestre text,
    date_import timestamptz not null default now(),
    n_eleves int,
    n_enregistrements int,
    statut text not null default 'charge' check (statut in ('charge', 'archive')),
    -- Résumé SANS PII : compteurs et matrice de couverture uniquement. Ne jamais
    -- stocker ici les listes brutes d'anomalies/doublons de data_quality_report.json,
    -- qui référencent des student_code en clair avant anonymisation (étape B, avant C).
    quality_summary jsonb,
    risk_config jsonb,                  -- seuils de la définition de cible (targets.risk_config())
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- subjects : référentiel statique des 7 matières + domaine.
-- ---------------------------------------------------------------------------
create table if not exists subjects (
    code text primary key,              -- ex. "MATHEMATIQUES"
    nom_fr text not null,
    domaine text not null check (domaine in ('scientifique', 'linguistique', 'sciences_humaines'))
);

-- ---------------------------------------------------------------------------
-- students : un élève pseudonymisé par dataset (mono-semestre, cf. §1.1).
-- ---------------------------------------------------------------------------
create table if not exists students (
    id uuid primary key,
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_pseudo text not null,       -- hash HMAC tronqué, jamais réversible ici
    niveau text not null,
    classe text not null,
    tranche_age text,
    nb_matieres_suivies int,
    moyenne_generale numeric,
    dispersion_intermatiere numeric,
    tendance_globale numeric,
    a_risque boolean not null default false,
    remarque_encodee numeric,           -- moyenne ordinale (0-4), descriptif uniquement
    unique (dataset_id, student_pseudo)
);
create index if not exists idx_students_dataset on students(dataset_id);
create index if not exists idx_students_niveau on students(niveau);
create index if not exists idx_students_a_risque on students(a_risque);

-- ---------------------------------------------------------------------------
-- grades : une ligne par (élève x matière), composantes disponibles uniquement.
-- ---------------------------------------------------------------------------
create table if not exists grades (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_id uuid not null references students(id) on delete cascade,
    subject_code text not null references subjects(code),
    c1 numeric, c2 numeric, c3 numeric, c4 numeric, activites numeric,
    -- Distingue "composante non saisie" de "composante hors schéma du fichier" (cf. étape A/B).
    c1_colonne_existe boolean not null default false,
    c2_colonne_existe boolean not null default false,
    c3_colonne_existe boolean not null default false,
    c4_colonne_existe boolean not null default false,
    activites_colonne_existe boolean not null default false,
    moyenne_matiere numeric,
    n_composantes smallint,
    tendance_matiere numeric,
    remarque_fr text,                   -- texte teacher, non nominatif
    unique (student_id, subject_code)
);
create index if not exists idx_grades_dataset on grades(dataset_id);
create index if not exists idx_grades_subject on grades(subject_code);

-- ---------------------------------------------------------------------------
-- model_runs : métadonnées d'entraînement (§2.8, §11 reproductibilité).
-- ---------------------------------------------------------------------------
create table if not exists model_runs (
    id uuid primary key,
    dataset_id uuid not null references datasets(id) on delete cascade,
    type text not null check (type in ('classification', 'regression', 'clustering')),
    algo text not null,                 -- ex. "logistic_regression", "ridge", "kmeans"
    niveau text,                        -- non nul uniquement pour un run de clustering (par niveau)
    params jsonb,
    metrics jsonb,
    feature_columns jsonb,
    random_state int,
    created_at timestamptz not null default now()
);
create index if not exists idx_model_runs_dataset on model_runs(dataset_id);

-- ---------------------------------------------------------------------------
-- clusters : un élève -> un cluster (par niveau, cf. src/models/clustering.py).
-- ---------------------------------------------------------------------------
create table if not exists clusters (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_id uuid not null references students(id) on delete cascade,
    model_run_id uuid references model_runs(id),
    cluster_id smallint not null,
    cluster_label text not null,
    pca_1 numeric,
    pca_2 numeric,
    unique (student_id)
);
create index if not exists idx_clusters_dataset on clusters(dataset_id);

-- ---------------------------------------------------------------------------
-- predictions : sorties des modèles retenus (Logistic Regression, Ridge).
-- ---------------------------------------------------------------------------
create table if not exists predictions (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_id uuid not null references students(id) on delete cascade,
    model_run_classification_id uuid references model_runs(id),
    model_run_regression_id uuid references model_runs(id),
    a_risque_predit boolean,
    probabilite_risque numeric,
    moyenne_generale_predite numeric,
    explication_risque_fr text,
    explication_moyenne_fr text,
    unique (student_id)
);
create index if not exists idx_predictions_dataset on predictions(dataset_id);

-- ---------------------------------------------------------------------------
-- recommendations : sorties du moteur de règles (§9). Plusieurs par élève.
-- ---------------------------------------------------------------------------
create table if not exists recommendations (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_id uuid not null references students(id) on delete cascade,
    priorite smallint not null check (priorite between 1 and 3),
    type text not null,
    justification text not null,
    action text not null,
    matieres_concernees text[] not null default '{}',
    profil text,
    tendance_previsionnelle_moyenne_predite numeric,
    created_at timestamptz not null default now()
);
create index if not exists idx_recommendations_dataset on recommendations(dataset_id);
create index if not exists idx_recommendations_priorite on recommendations(priorite);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table datasets enable row level security;
alter table subjects enable row level security;
alter table students enable row level security;
alter table grades enable row level security;
alter table model_runs enable row level security;
alter table clusters enable row level security;
alter table predictions enable row level security;
alter table recommendations enable row level security;

-- Lecture ouverte (anon + authenticated) : données déjà pseudonymisées, aucune
-- fuite possible. Aucune politique d'écriture pour ces rôles ; seul service_role
-- (loader Python) écrit, en contournant RLS nativement.
create policy "lecture_publique" on datasets for select using (true);
create policy "lecture_publique" on subjects for select using (true);
create policy "lecture_publique" on students for select using (true);
create policy "lecture_publique" on grades for select using (true);
create policy "lecture_publique" on model_runs for select using (true);
create policy "lecture_publique" on clusters for select using (true);
create policy "lecture_publique" on predictions for select using (true);
create policy "lecture_publique" on recommendations for select using (true);
