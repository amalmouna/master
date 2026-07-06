-- Étape 10 — schéma Supabase, architecture privée/authentifiée, accès par rôle.
--
-- Pour un projet Supabase déjà existant, ce fichier seul ne suffit pas
-- ("create table if not exists" ne modifie pas les tables déjà créées) :
-- appliquez dans l'ordre migration_002_auth_and_identity.sql puis
-- migration_003_role_based_access.sql. Ce fichier est la référence pour un
-- projet neuf, ou pour comprendre l'état final attendu.
--
-- CHANGEMENT DE POLITIQUE (voir docs/AUTH_SETUP.md) : ce schéma contient le
-- NOM RÉEL des élèves (students.nom_complet) et leur âge exact — dérogation
-- documentée à la règle par défaut du projet ("aucune donnée nominative ne
-- doit exister au-delà de l'anonymisation"), décidée par le porteur du
-- projet en échange d'un verrouillage strict : accès par rôle, filtré par
-- classe pour les comptes non-admin. Le code national (student_code) reste
-- hors base dans tous les cas — seul le hash stable (student_pseudo) sert de
-- clé technique. Le pipeline Python (étapes D-9) continue de fonctionner
-- exclusivement sur les données pseudonymisées SANS nom ; seule la couche de
-- persistance reçoit l'identité réelle, via
-- src/anonymization/anonymize.py::build_identity_mapping.
--
-- Accès : deux rôles applicatifs (table user_roles) — admin (tout voit, gère
-- les comptes) et scoped_user (voit uniquement les classes listées dans
-- user_classes). Aucune inscription publique : tous les comptes sont créés
-- par un admin (dashboard pour le premier, écran in-app pour les suivants).
-- Aucune table scolaire n'est lisible par le rôle anon.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Rôles et périmètre de classes.
-- ---------------------------------------------------------------------------
create table if not exists user_roles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    role text not null check (role in ('admin', 'scoped_user')),
    created_at timestamptz not null default now()
);

create table if not exists user_classes (
    user_id uuid not null references auth.users(id) on delete cascade,
    classe text not null,
    primary key (user_id, classe)
);

alter table user_roles enable row level security;
alter table user_classes enable row level security;
-- Aucune politique anon/authenticated : accès exclusif via service_role
-- (écran de gestion des utilisateurs, côté serveur) ou via les fonctions
-- security definer ci-dessous.

create or replace function is_admin()
returns boolean
language sql security definer set search_path = public stable
as $$
  select exists (select 1 from user_roles where user_id = auth.uid() and role = 'admin');
$$;

create or replace function get_user_classes()
returns text[]
language sql security definer set search_path = public stable
as $$
  select coalesce(array_agg(classe), '{}'::text[]) from user_classes where user_id = auth.uid();
$$;

create or replace function is_app_user()
returns boolean
language sql security definer set search_path = public stable
as $$
  select exists (select 1 from user_roles where user_id = auth.uid());
$$;

-- ---------------------------------------------------------------------------
-- datasets : un import = un semestre. Traçabilité (§2.8).
-- ---------------------------------------------------------------------------
create table if not exists datasets (
    id uuid primary key,
    label text not null,
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
    risk_config jsonb,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- subjects : référentiel statique des 7 matières + domaine.
-- ---------------------------------------------------------------------------
create table if not exists subjects (
    code text primary key,
    nom_fr text not null,
    domaine text not null check (domaine in ('scientifique', 'linguistique', 'sciences_humaines'))
);

-- ---------------------------------------------------------------------------
-- students : un élève par dataset (mono-semestre, cf. §1.1). Identité réelle
-- (voir bandeau en tête de fichier) — accès filtré par classe (RLS ci-dessous).
-- ---------------------------------------------------------------------------
create table if not exists students (
    id uuid primary key,
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_pseudo text not null,
    nom_complet text,
    age int,
    niveau text not null,
    classe text not null,
    nb_matieres_suivies int,
    moyenne_generale numeric,
    dispersion_intermatiere numeric,
    tendance_globale numeric,
    a_risque boolean not null default false,
    remarque_encodee numeric,
    unique (dataset_id, student_pseudo)
);
create index if not exists idx_students_dataset on students(dataset_id);
create index if not exists idx_students_niveau on students(niveau);
create index if not exists idx_students_classe on students(classe);
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
    c1_colonne_existe boolean not null default false,
    c2_colonne_existe boolean not null default false,
    c3_colonne_existe boolean not null default false,
    c4_colonne_existe boolean not null default false,
    activites_colonne_existe boolean not null default false,
    moyenne_matiere numeric,
    n_composantes smallint,
    tendance_matiere numeric,
    remarque_fr text,
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
    algo text not null,
    niveau text,
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
-- Row Level Security — tables scolaires, filtrées par classe pour scoped_user.
-- ---------------------------------------------------------------------------
alter table datasets enable row level security;
alter table subjects enable row level security;
alter table students enable row level security;
alter table grades enable row level security;
alter table model_runs enable row level security;
alter table clusters enable row level security;
alter table predictions enable row level security;
alter table recommendations enable row level security;

create policy "lecture_filtree" on datasets for select using (is_app_user());
create policy "lecture_filtree" on subjects for select using (is_app_user());
create policy "lecture_filtree" on model_runs for select using (is_admin());

create policy "lecture_filtree" on students for select
  using (is_admin() or classe = any(get_user_classes()));

create policy "lecture_filtree" on grades for select
  using (
    is_admin()
    or exists (select 1 from students s where s.id = grades.student_id and s.classe = any(get_user_classes()))
  );

create policy "lecture_filtree" on clusters for select
  using (
    is_admin()
    or exists (select 1 from students s where s.id = clusters.student_id and s.classe = any(get_user_classes()))
  );

create policy "lecture_filtree" on predictions for select
  using (
    is_admin()
    or exists (select 1 from students s where s.id = predictions.student_id and s.classe = any(get_user_classes()))
  );

create policy "lecture_filtree" on recommendations for select
  using (
    is_admin()
    or exists (select 1 from students s where s.id = recommendations.student_id and s.classe = any(get_user_classes()))
  );
