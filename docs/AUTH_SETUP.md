# Architecture privée/authentifiée, accès par rôle — ce qu'il reste à faire

Ce document couvre l'accès au tableau de bord : authentification par email/
mot de passe, deux rôles (`admin`, `scoped_user`), périmètre par classe
appliqué en base (RLS), et gestion des comptes depuis l'application.

**Dérogation documentée** : ce projet a pour règle par défaut qu'aucune donnée
nominative ne dépasse l'étape d'anonymisation (`docs/PROMPT.md` §3C,
`CLAUDE.md`). L'architecture décrite ici y déroge délibérément (nom réel +
âge exact des élèves en base), à la demande du porteur du projet, en
contrepartie d'un accès verrouillé par authentification + rôle + classe. Le
code national (`student_code`) reste hors base dans tous les cas.

Rien n'est déployé. Les sections ci-dessous listent ce qui est fait
automatiquement, et ce qui **nécessite une action manuelle de votre part**
(accès REST via service_role uniquement, pas de connexion Postgres directe
ni au dashboard Supabase/Vercel de mon côté).

---

## 1. Déjà fait de votre côté (confirmé)

- Premier compte admin créé manuellement dans le dashboard (email + mot de
  passe, auto-confirmé).
- Provider email/mot de passe activé, inscription publique désactivée.
- `SUPABASE_SERVICE_ROLE_KEY` dans `.env.local` racine (pour le loader Python).
  **Note** : je l'ai dupliquée dans `frontend/.env.local` (même valeur,
  fichier gitignored) — Next.js ne lit ses variables d'environnement que
  depuis son propre dossier de projet (`frontend/`), jamais depuis la racine
  du dépôt. Sans cette copie, l'écran de gestion des utilisateurs n'aurait
  pas pu appeler l'API admin Supabase.

## 2. Déjà fait de mon côté (code)

- `supabase/migration_003_role_based_access.sql` — remplace le mécanisme
  d'allowlist/trigger (migration 002, jamais réellement exploité) par :
  - `user_roles` (`user_id`, `role` ∈ {`admin`, `scoped_user`}) ;
  - `user_classes` (`user_id`, `classe`) — une ligne par classe autorisée,
    uniquement pertinent pour `scoped_user` ;
  - fonctions `is_admin()`, `get_user_classes()`, `is_app_user()` (SECURITY
    DEFINER — contournent RLS en interne, n'exposent qu'un résultat calculé) ;
  - politiques RLS `lecture_filtree` sur `students/grades/clusters/predictions/recommendations`
    (filtrées par classe via jointure sur `students.classe`), et sur
    `datasets/subjects` (tout compte applicatif reconnu) et `model_runs`
    (admin uniquement).
- `supabase/schema.sql` mis à jour comme référence de l'état final consolidé
  (utile pour un projet neuf ; sur le projet existant, appliquez les
  migrations dans l'ordre : 002 puis 003).
- Frontend :
  - Connexion par email/mot de passe (`components/auth/LoginForm.tsx`,
    `supabase.auth.signInWithPassword`) — le lien magique et sa route de
    callback ont été retirés.
  - `lib/supabase/roles.ts::getCurrentUserRole()` — lit le rôle et les
    classes autorisées de l'utilisateur connecté via RPC (`is_admin()`,
    `get_user_classes()`), jamais par un SELECT direct sur `user_roles`/
    `user_classes` (ces tables n'ont aucune politique de lecture pour
    anon/authenticated : verrouillées même pour l'utilisateur concerné,
    seules les fonctions SECURITY DEFINER y ont accès).
  - `lib/supabase/admin.ts` — client `service_role`, marqué
    `import "server-only"` (le **build échoue** si ce module est jamais
    importé depuis un composant Client — garantie à la compilation, pas
    seulement une convention). Fournit `listManagedUsers`,
    `createManagedUser`, `deleteManagedUser`.
  - `app/(dashboard)/utilisateurs/` — écran de gestion (page + Server
    Actions `createUserAction`/`deleteUserAction`). **Chaque action
    revérifie `is_admin()` sur l'appelant** avant tout appel au client
    `service_role` — la page n'apparaît pas dans la navigation pour un
    `scoped_user`, mais ce n'est qu'un confort d'UI : l'action serait de
    toute façon bloquée si elle était appelée directement.
  - Navigation : le lien « Utilisateurs » n'apparaît que si `isAdmin` (passé
    depuis `app/(dashboard)/layout.tsx`, qui appelle `getCurrentUserRole()`).
  - Aucune page du dashboard ne change de code pour les `scoped_user` : les
    mêmes pages (Vue d'ensemble, Moyennes par matière, Élèves à risque,
    Profils, Fiche élève) affichent automatiquement moins de lignes, filtrées
    par RLS — pas de logique de filtrage dupliquée côté frontend.

## 3. Ce que VOUS devez faire dans le dashboard Supabase

### 3.1 Appliquer la migration SQL (obligatoire, je ne peux pas le faire)

**SQL Editor** → coller et exécuter `supabase/migration_003_role_based_access.sql`
en entier. Idempotent (peut être relancé sans erreur).

### 3.2 Rattacher votre compte admin existant

Le compte créé manuellement à l'étape 1 n'a pas de ligne `user_roles` (rien
ne l'y met automatiquement — il n'y a plus de trigger d'auto-inscription).
Dans **SQL Editor**, remplacez l'email puis exécutez :

```sql
insert into user_roles (user_id, role)
select id, 'admin' from auth.users where email = 'VOTRE_EMAIL_ADMIN'
on conflict (user_id) do update set role = 'admin';
```

### 3.3 Trois requêtes de vérification

```sql
-- 1. Colonnes/tables créées
select table_name, column_name from information_schema.columns
where (table_name = 'students' and column_name in ('nom_complet', 'age'))
   or table_name in ('user_roles', 'user_classes')
order by table_name, column_name;

-- 2. Politiques RLS remplacées (attendu : "lecture_filtree" partout, plus
--    aucune "lecture_admin"/"lecture_publique")
select tablename, policyname, cmd from pg_policies
where tablename in ('students','grades','clusters','predictions',
                     'recommendations','datasets','subjects','model_runs')
order by tablename;

-- 3. Votre compte admin est bien rattaché
select u.email, r.role, array_agg(c.classe) as classes
from user_roles r
join auth.users u on u.id = r.user_id
left join user_classes c on c.user_id = r.user_id
group by u.email, r.role;
```

## 4. Une fois 3.1-3.2 faites : gérer les comptes depuis l'application

Connectez-vous avec le compte admin (email/mot de passe créé à l'étape 1) →
menu **Utilisateurs** (visible uniquement pour un admin) :

- **Créer un utilisateur** : email, mot de passe (8 caractères minimum),
  rôle. Si « Accès limité », cochez les classes autorisées (liste dérivée en
  direct des classes réelles du dernier import — jamais une liste codée en
  dur). Le compte est créé via l'API admin Supabase (email confirmé
  automatiquement, pas d'email d'invitation envoyé) — communiquez le mot de
  passe à la personne par un canal séparé.
- **Supprimer un utilisateur** : bouton corbeille sur chaque ligne (sauf le
  compte actuellement connecté). Supprime le compte Auth ; `user_roles`/
  `user_classes` sont nettoyés automatiquement (contrainte `on delete cascade`).

## 5. Vercel (au moment du déploiement — pas encore)

- Variables d'environnement : `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`, et désormais aussi
  `SUPABASE_SERVICE_ROLE_KEY` (nécessaire à l'écran de gestion des
  utilisateurs, qui s'exécute côté serveur Next.js sur Vercel — ce n'est
  plus réservé au seul loader Python comme dans la version précédente de ce
  document). Marquez-la explicitement comme variable **sensible/serveur**
  dans les réglages Vercel si l'option existe.
- Protection d'accès optionnelle en plus de l'auth applicative : **Deployment
  Protection** (Project Settings) peut ajouter une couche supplémentaire au
  niveau du edge.
- Rappel : consigne explicite reçue de ne pas déployer pour l'instant.
