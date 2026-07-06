-- Migration 004 — imports multi-années additifs.
-- À exécuter dans le SQL Editor du projet Supabase existant. Idempotent.
--
-- Contexte : chaque import crée déjà un nouveau `datasets.id` (jamais un
-- remplacement) et `datasets.annee_scolaire` existe déjà — l'historisation
-- par import n'est pas nouvelle. Ce qui manquait : (1) l'année scolaire
-- directement sur `students` (évite une jointure pour toute requête/RLS
-- future qui voudrait filtrer par année), (2) un garde-fou base de données
-- contre un doublon (élève, année) si le même import est chargé deux fois,
-- (3) un index pour retrouver l'historique d'un élève (même student_pseudo)
-- à travers les années sans scanner toute la table.
--
-- PRÉALABLE MANUEL DÉJÀ FAIT (pas par cette migration) : deux lignes
-- `datasets` obsolètes pour 2025/2026 (un orphelin à 0 élève, un doublon
-- pré-identité sans noms réels) ont été supprimées avant cette migration —
-- sans ce nettoyage, l'étape 3 ci-dessous échoue sur un vrai doublon
-- (élève, année) déjà présent en base, pas seulement un cas hypothétique.
-- Si vous rechargez cette base ailleurs et voyez plusieurs `datasets` pour
-- la même (annee_scolaire, semestre), nettoyez-les D'ABORD (voir requête de
-- diagnostic en bas de fichier) : cette migration ne supprime aucune donnée
-- elle-même.

-- ---------------------------------------------------------------------------
-- 1. Colonne academic_year sur students (nullable d'abord, pour pouvoir
--    backfill avant de contraindre).
-- ---------------------------------------------------------------------------
alter table students add column if not exists academic_year text;

-- ---------------------------------------------------------------------------
-- 2. Backfill depuis datasets.annee_scolaire pour les lignes déjà chargées.
--    Idempotent : ne touche que les lignes encore NULL.
-- ---------------------------------------------------------------------------
update students s
set academic_year = d.annee_scolaire
from datasets d
where d.id = s.dataset_id
  and s.academic_year is null
  and d.annee_scolaire is not null;

-- ---------------------------------------------------------------------------
-- 3. Contraintes. NOT NULL + format 'AAAA/AAAA' (même convention que le
--    pipeline Python, cf. src/score_import.py::_reference_date) + garde-fou
--    anti-doublon (élève, année) : un même student_pseudo ne peut apparaître
--    qu'une fois par academic_year, quel que soit le dataset_id d'origine.
--    (Granularité volontairement "par année", pas "par année + semestre" —
--    si vous chargez un second semestre dans la même année scolaire plus
--    tard, cette contrainte le refusera : ce sera une migration de suivi,
--    pas quelque chose à deviner maintenant.)
-- ---------------------------------------------------------------------------
alter table students alter column academic_year set not null;

alter table students drop constraint if exists students_academic_year_format;
alter table students add constraint students_academic_year_format
  check (academic_year ~ '^\d{4}/\d{4}$');

alter table students drop constraint if exists students_pseudo_academic_year_unique;
alter table students add constraint students_pseudo_academic_year_unique
  unique (student_pseudo, academic_year);

-- ---------------------------------------------------------------------------
-- 4. Index pour retrouver l'historique d'un élève à travers les années.
--    L'unique ci-dessus crée déjà un index sur (student_pseudo, academic_year),
--    mais avec academic_year en tête il ne sert pas "tous les enregistrements
--    de ce student_pseudo, toutes années" — d'où cet index dédié.
-- ---------------------------------------------------------------------------
create index if not exists idx_students_pseudo_history on students(student_pseudo);
create index if not exists idx_students_academic_year on students(academic_year);

-- ---------------------------------------------------------------------------
-- 5. RLS — AUCUN changement de politique nécessaire, documenté ici plutôt que
--    silencieusement omis. Les politiques "lecture_filtree" sur students/
--    grades/clusters/predictions/recommendations filtrent déjà par
--    `s.classe = any(get_user_classes())`, une comparaison par ligne qui ne
--    dépend ni du dataset_id ni de l'academic_year : elle continue de
--    fonctionner à l'identique quand plusieurs lignes existent pour le même
--    code de classe à travers plusieurs années (cf. requête de vérification
--    n°3 plus bas). Un scoped_user assigné à "2APIC-4" voit CETTE classe pour
--    TOUTES les années où elle apparaît — comportement demandé explicitement
--    ("across all years they're assigned"), pas une restriction par année.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Requête de diagnostic (à lancer AVANT cette migration si vous n'êtes pas
-- sûr·e que votre base est propre) : détecte les doublons (élève, année)
-- déjà présents, qui feraient échouer l'étape 3.
-- ---------------------------------------------------------------------------
-- select student_pseudo, academic_year, count(*), array_agg(dataset_id)
-- from students
-- group by student_pseudo, academic_year
-- having count(*) > 1;
