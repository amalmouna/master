-- Étape 10 — schéma Supabase, architecture privée/authentifiée.
--
-- CHANGEMENT DE POLITIQUE (voir docs/AUTH_SETUP.md pour le contexte complet) :
-- ce schéma contient désormais le NOM RÉEL des élèves (colonne
-- students.nom_complet) et leur âge exact. C'est une dérogation explicite et
-- documentée à la règle par défaut du projet ("aucune donnée nominative ne
-- doit exister au-delà de l'anonymisation"), décidée par le porteur du
-- projet en échange d'un verrouillage strict de l'accès : plus aucune
-- lecture anonyme n'est autorisée (RLS admin-only ci-dessous), et le code
-- national (student_code) reste hors base dans tous les cas — seul le hash
-- stable (student_pseudo) sert de clé technique. Le pipeline Python (étapes
-- D-9 : agrégats, modèles, clustering, recommandations) continue de
-- fonctionner exclusivement sur les données pseudonymisées SANS nom ; seule
-- la couche de persistance (ce schéma + le loader) reçoit l'identité réelle,
-- au moment du chargement, via src/anonymization/anonymize.py::build_identity_mapping.
--
-- RLS : lecture réservée aux utilisateurs authentifiés listés dans `admins`
-- (voir la fonction is_admin() plus bas). Aucune table scolaire n'est
-- lisible par le rôle anon. Écriture réservée à service_role (loader Python),
-- qui contourne RLS nativement côté Supabase — jamais utilisé côté frontend.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Administration des accès (Supabase Auth)
-- ---------------------------------------------------------------------------

-- Allowlist des emails autorisés à devenir administrateur. À remplir avec les
-- vraies adresses de l'administration (cf. docs/AUTH_SETUP.md) :
--   insert into admin_allowlist (email) values ('directeur@exemple.ma');
create table if not exists admin_allowlist (
    email text primary key
);

-- Comptes administrateurs effectifs, liés à auth.users. Rempli automatiquement
-- par le trigger ci-dessous quand un compte Supabase Auth est créé (via
-- invitation dashboard, jamais via inscription publique — désactivée) avec un
-- email présent dans admin_allowlist. Un compte créé avec un email absent de
-- la liste n'obtient AUCUN accès (pas de ligne ici -> is_admin() = false).
create table if not exists admins (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    created_at timestamptz not null default now()
);

create or replace function handle_new_admin_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if exists (select 1 from admin_allowlist where email = new.email) then
    insert into admins (id, email) values (new.id, new.email)
    on conflict (id) do nothing;
  end if;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_admin_user();

-- Fonction utilisée par toutes les politiques RLS ci-dessous. security definer
-- pour pouvoir lire `admins` même si son propre RLS interdit la lecture directe.
create or replace function is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from admins where id = auth.uid());
$$;

alter table admin_allowlist enable row level security;
alter table admins enable row level security;
-- Aucune politique select/insert/update/delete pour anon/authenticated sur ces
-- deux tables : accès exclusivement via service_role (dashboard/SQL editor)
-- ou via is_admin(), qui contourne RLS grâce à security definer.

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
-- students : un élève par dataset (mono-semestre, cf. §1.1). Identité réelle
-- (voir bandeau en tête de fichier) — accès verrouillé par RLS admin-only.
-- ---------------------------------------------------------------------------
create table if not exists students (
    id uuid primary key,
    dataset_id uuid not null references datasets(id) on delete cascade,
    student_pseudo text not null,       -- hash HMAC stable — clé technique, jamais le code national
    nom_complet text,                   -- nom réel (dérogation documentée ci-dessus)
    age int,                            -- âge exact au 1er septembre, jamais la date de naissance
    niveau text not null,
    classe text not null,
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
-- Row Level Security — tables scolaires
-- ---------------------------------------------------------------------------
alter table datasets enable row level security;
alter table subjects enable row level security;
alter table students enable row level security;
alter table grades enable row level security;
alter table model_runs enable row level security;
alter table clusters enable row level security;
alter table predictions enable row level security;
alter table recommendations enable row level security;

-- Lecture réservée aux administrateurs authentifiés (is_admin()). anon exclu
-- explicitement : aucune policy ne le mentionne, et RLS est fail-closed par
-- défaut (aucune ligne visible sans policy correspondante).
create policy "lecture_admin" on datasets for select using (is_admin());
create policy "lecture_admin" on subjects for select using (is_admin());
create policy "lecture_admin" on students for select using (is_admin());
create policy "lecture_admin" on grades for select using (is_admin());
create policy "lecture_admin" on model_runs for select using (is_admin());
create policy "lecture_admin" on clusters for select using (is_admin());
create policy "lecture_admin" on predictions for select using (is_admin());
create policy "lecture_admin" on recommendations for select using (is_admin());
