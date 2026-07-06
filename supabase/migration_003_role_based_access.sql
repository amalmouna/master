-- Migration 003 — accès basé sur les rôles (admin / scoped_user par classe).
-- À exécuter dans le SQL Editor du projet Supabase existant. Idempotent.
--
-- Remplace le mécanisme d'allowlist par email + trigger d'auto-inscription
-- (migration 002) : désormais TOUS les comptes sont créés par un admin
-- (dashboard pour le premier, écran in-app pour les suivants) — il n'y a
-- plus d'auto-inscription à contrôler, donc plus besoin d'allowlist/trigger.
-- Le rôle et les classes autorisées sont des données explicites (tables
-- ci-dessous), assignées au moment de la création du compte, jamais déduites
-- d'un email.
--
-- Ordre important (corrigé) : toutes les politiques qui référencent
-- is_admin() doivent être supprimées AVANT toute tentative de modifier cette
-- fonction, sous peine de "cannot drop function is_admin() because other
-- objects depend on it". Et comme sa signature ne change pas (même nom,
-- aucun argument, renvoie boolean), on ne la DROP jamais : create or replace
-- suffit et ne casse aucune dépendance existante.

-- ---------------------------------------------------------------------------
-- 1. Supprimer TOUTES les anciennes politiques en premier, avant de toucher
--    à quoi que ce soit dont elles dépendent (is_admin(), etc.).
-- ---------------------------------------------------------------------------
drop policy if exists "lecture_admin" on datasets;
drop policy if exists "lecture_admin" on subjects;
drop policy if exists "lecture_admin" on students;
drop policy if exists "lecture_admin" on grades;
drop policy if exists "lecture_admin" on model_runs;
drop policy if exists "lecture_admin" on clusters;
drop policy if exists "lecture_admin" on predictions;
drop policy if exists "lecture_admin" on recommendations;
-- Au cas où la toute première politique (avant migration 002) serait encore là.
drop policy if exists "lecture_publique" on datasets;
drop policy if exists "lecture_publique" on subjects;
drop policy if exists "lecture_publique" on students;
drop policy if exists "lecture_publique" on grades;
drop policy if exists "lecture_publique" on model_runs;
drop policy if exists "lecture_publique" on clusters;
drop policy if exists "lecture_publique" on predictions;
drop policy if exists "lecture_publique" on recommendations;
-- Idempotence : si cette migration a déjà été (partiellement) appliquée.
drop policy if exists "lecture_filtree" on datasets;
drop policy if exists "lecture_filtree" on subjects;
drop policy if exists "lecture_filtree" on students;
drop policy if exists "lecture_filtree" on grades;
drop policy if exists "lecture_filtree" on model_runs;
drop policy if exists "lecture_filtree" on clusters;
drop policy if exists "lecture_filtree" on predictions;
drop policy if exists "lecture_filtree" on recommendations;

-- ---------------------------------------------------------------------------
-- 2. Nettoyage de l'ancien mécanisme (migration 002). Plus aucune politique
--    ne référence is_admin() à ce stade : la table admins et le trigger
--    peuvent être supprimés sans erreur de dépendance. is_admin() elle-même
--    n'est PAS supprimée (cf. note d'en-tête) — redéfinie en step 4.
-- ---------------------------------------------------------------------------
drop trigger if exists on_auth_user_created on auth.users;
drop function if exists handle_new_admin_user();
drop table if exists admin_allowlist;
drop table if exists admins;

-- ---------------------------------------------------------------------------
-- 3. Rôles et périmètre de classes.
-- ---------------------------------------------------------------------------
create table if not exists user_roles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    role text not null check (role in ('admin', 'scoped_user')),
    created_at timestamptz not null default now()
);

-- Une ligne par (utilisateur, classe autorisée). Uniquement pertinent pour
-- role = 'scoped_user' ; sans effet pour un admin (is_admin() prime, cf. plus
-- bas). classe = un des 14 codes réels (ex. "1APIC-1", "3APIC-4") — pas de
-- contrainte de valeur ici : le référentiel de classes vit dans `students`,
-- pas dans un enum figé, pour ne pas devoir migrer le schéma à chaque import.
create table if not exists user_classes (
    user_id uuid not null references auth.users(id) on delete cascade,
    classe text not null,
    primary key (user_id, classe)
);

alter table user_roles enable row level security;
alter table user_classes enable row level security;
-- Aucune politique select/insert/update/delete pour anon/authenticated : ces
-- deux tables ne sont manipulées QUE par le rôle service_role (écran de
-- gestion des utilisateurs, côté serveur) ou lues via les fonctions security
-- definer ci-dessous, qui contournent RLS.

-- ---------------------------------------------------------------------------
-- 4. Fonctions utilisées par les politiques RLS. create or replace
--    uniquement — jamais de drop (cf. note d'en-tête) : la signature ne
--    change pas, seul le corps est mis à jour (user_roles au lieu d'admins).
-- ---------------------------------------------------------------------------
create or replace function is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from user_roles where user_id = auth.uid() and role = 'admin');
$$;

create or replace function get_user_classes()
returns text[]
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(array_agg(classe), '{}'::text[]) from user_classes where user_id = auth.uid();
$$;

-- Vrai pour tout compte reconnu par l'application (admin OU scoped_user),
-- utilisé pour les tables sans notion de classe (datasets, subjects) : un
-- scoped_user peut voir ces métadonnées non nominatives, RLS sur `students`
-- limite déjà ce qui compte (les élèves eux-mêmes).
create or replace function is_app_user()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from user_roles where user_id = auth.uid());
$$;

-- ---------------------------------------------------------------------------
-- 5. Nouvelles politiques RLS — filtrées par classe pour scoped_user,
--    complètes pour admin. Les anciennes ont déjà été supprimées en step 1.
-- ---------------------------------------------------------------------------
create policy "lecture_filtree" on datasets for select using (is_app_user());
create policy "lecture_filtree" on subjects for select using (is_app_user());

-- model_runs : réservé aux admins (métadonnées d'entraînement, sans usage
-- pour un scoped_user dans le produit actuel).
create policy "lecture_filtree" on model_runs for select using (is_admin());

-- students : la classe de l'élève doit être dans le périmètre de l'appelant.
create policy "lecture_filtree" on students for select
  using (is_admin() or classe = any(get_user_classes()));

-- grades/clusters/predictions/recommendations : pas de colonne classe
-- directe, on la résout via une jointure sur students.
create policy "lecture_filtree" on grades for select
  using (
    is_admin()
    or exists (
      select 1 from students s
      where s.id = grades.student_id and s.classe = any(get_user_classes())
    )
  );

create policy "lecture_filtree" on clusters for select
  using (
    is_admin()
    or exists (
      select 1 from students s
      where s.id = clusters.student_id and s.classe = any(get_user_classes())
    )
  );

create policy "lecture_filtree" on predictions for select
  using (
    is_admin()
    or exists (
      select 1 from students s
      where s.id = predictions.student_id and s.classe = any(get_user_classes())
    )
  );

create policy "lecture_filtree" on recommendations for select
  using (
    is_admin()
    or exists (
      select 1 from students s
      where s.id = recommendations.student_id and s.classe = any(get_user_classes())
    )
  );

-- ---------------------------------------------------------------------------
-- 6. Rattacher le premier admin (créé manuellement dans le dashboard).
--    Remplacez l'email puis exécutez CETTE requête séparément :
-- ---------------------------------------------------------------------------
-- insert into user_roles (user_id, role)
-- select id, 'admin' from auth.users where email = 'VOTRE_EMAIL_ADMIN'
-- on conflict (user_id) do update set role = 'admin';
