-- Migration 002 — bascule vers l'architecture privée/authentifiée.
-- À exécuter une fois dans le SQL Editor du projet Supabase EXISTANT
-- (schema.sql seul ne suffit pas : "create table if not exists" ne modifie
-- pas les tables déjà créées, et "create policy" échoue si le nom existe déjà).
--
-- Idempotent : peut être relancé sans erreur si une étape a déjà été appliquée.

-- 1. Colonnes d'identité réelle sur students (remplace tranche_age par age exact).
alter table students add column if not exists nom_complet text;
alter table students add column if not exists age int;
alter table students drop column if exists tranche_age;

-- 2. Allowlist + comptes admin + trigger d'auto-inscription contrôlée.
create table if not exists admin_allowlist (
    email text primary key
);

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

-- 3. Remplace les politiques de lecture publique par un accès admin-only.
drop policy if exists "lecture_publique" on datasets;
drop policy if exists "lecture_publique" on subjects;
drop policy if exists "lecture_publique" on students;
drop policy if exists "lecture_publique" on grades;
drop policy if exists "lecture_publique" on model_runs;
drop policy if exists "lecture_publique" on clusters;
drop policy if exists "lecture_publique" on predictions;
drop policy if exists "lecture_publique" on recommendations;

drop policy if exists "lecture_admin" on datasets;
drop policy if exists "lecture_admin" on subjects;
drop policy if exists "lecture_admin" on students;
drop policy if exists "lecture_admin" on grades;
drop policy if exists "lecture_admin" on model_runs;
drop policy if exists "lecture_admin" on clusters;
drop policy if exists "lecture_admin" on predictions;
drop policy if exists "lecture_admin" on recommendations;

create policy "lecture_admin" on datasets for select using (is_admin());
create policy "lecture_admin" on subjects for select using (is_admin());
create policy "lecture_admin" on students for select using (is_admin());
create policy "lecture_admin" on grades for select using (is_admin());
create policy "lecture_admin" on model_runs for select using (is_admin());
create policy "lecture_admin" on clusters for select using (is_admin());
create policy "lecture_admin" on predictions for select using (is_admin());
create policy "lecture_admin" on recommendations for select using (is_admin());

-- 4. Ajoutez vos emails d'administration ici (ou via Table Editor) :
-- insert into admin_allowlist (email) values ('directeur@exemple.ma') on conflict do nothing;
