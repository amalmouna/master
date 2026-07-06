# Architecture privée/authentifiée — ce qu'il reste à faire manuellement

Ce document couvre le changement de politique demandé : le tableau de bord
n'est plus public/pseudonymisé, il est privé et affiche les noms réels des
élèves, réservé aux comptes administration authentifiés.

**Dérogation documentée** : ce projet a pour règle par défaut qu'aucune donnée
nominative ne dépasse l'étape d'anonymisation (`docs/PROMPT.md` §3C,
`CLAUDE.md`). Cette architecture y déroge délibérément, à la demande du
porteur du projet, en contrepartie d'un verrouillage strict de l'accès
(authentification + allowlist + RLS admin-only ci-dessous). Le code national
(`student_code`) reste hors base dans tous les cas — seul le nom et l'âge
exact sont désormais persistés, jamais la date de naissance ni le code
national. Si vous voulez que `CLAUDE.md`/`docs/PROMPT.md` reflètent ce nouveau
choix, dites-le explicitement : je ne les modifie pas de mon propre chef.

Rien n'a été déployé. Les sections ci-dessous listent précisément ce qui a
été fait automatiquement, et ce qui **nécessite une action manuelle de votre
part** (je n'ai accès qu'à l'API REST via la clé service_role, pas à une
connexion Postgres directe ni au dashboard Supabase/Vercel).

---

## 1. Ce qui est déjà fait (code)

- `src/anonymization/anonymize.py::build_identity_mapping` — produit
  `data/artifacts/identity_mapping.csv` (nom réel + âge exact + niveau,
  indexé par `student_pseudo`), un artefact **séparé**, local, gitignored,
  consommé uniquement par le loader. Les étapes D-9 (agrégats, modèles,
  clustering, recommandations) continuent de tourner exclusivement sur la
  table longue pseudonymisée, sans nom, exactement comme avant.
- `src/persistence/load_to_supabase.py` — joint le nom/âge dans le payload
  `students`, lève une erreur explicite si un élève n'a pas de correspondance
  (pas de dégradation silencieuse). Vérifié en `--dry-run` : 481 lignes, noms
  présents, aucun code national ni id interne dans le payload.
- `supabase/schema.sql` (version à jour) et `supabase/migration_002_auth_and_identity.sql`
  (script à appliquer sur le projet existant) — colonnes `nom_complet`/`age`
  sur `students`, tables `admin_allowlist`/`admins`, trigger d'auto-inscription
  contrôlée, fonction `is_admin()`, politiques RLS `lecture_admin` remplaçant
  `lecture_publique`.
- Frontend : `proxy.ts` (équivalent middleware, renommé en Next.js 16) redirige
  toute requête non authentifiée vers `/login`, vérifié au niveau HTTP brut
  (307 avant tout rendu, pas seulement côté client). `app/(dashboard)/layout.tsx`
  revérifie la session côté serveur (`getUser()`, jamais `getSession()` — voir
  la note de sécurité dans `@supabase/ssr`). Page `/login` : lien magique par
  email, `shouldCreateUser: false` (aucune auto-inscription possible même si
  le lien magique est intercepté). Clé anon uniquement dans le frontend,
  vérifié par recherche de `service_role` dans le code (absent).

## 2. Ce que VOUS devez faire dans le dashboard Supabase

### 2.1 Appliquer la migration SQL (obligatoire, je ne peux pas le faire)

Je n'ai qu'un accès REST (clé service_role) au projet — pas de connexion
Postgres directe, donc pas d'exécution de `CREATE TABLE`/`CREATE TRIGGER`
possible depuis mon côté. Vous devez :

1. Ouvrir **SQL Editor** dans le dashboard Supabase du projet.
2. Coller et exécuter le contenu de `supabase/migration_002_auth_and_identity.sql`.
   Le script est idempotent (peut être relancé sans erreur).

### 2.2 Ajouter les emails administration à l'allowlist

Dans **SQL Editor** ou **Table Editor** (table `admin_allowlist`) :

```sql
insert into admin_allowlist (email) values
  ('email1@etablissement.ma'),
  ('email2@etablissement.ma')
on conflict do nothing;
```

Vous n'avez pas encore donné ces emails — j'ai laissé un exemple commenté
dans le script de migration. Sans cette étape, personne n'obtient l'accès
admin, même après connexion.

### 2.3 Désactiver l'inscription publique

**Authentication → Settings → Allow new users to sign up** → désactiver.
C'est la protection principale contre l'auto-inscription (le
`shouldCreateUser: false` côté frontend est une deuxième barrière, mais ne
remplace pas ce réglage : il empêche seulement le lien magique de créer un
compte, pas une inscription email/mot de passe si elle restait active).

### 2.4 Créer les comptes administration

**Authentication → Users → Invite user** (ou **Add user**), un par email de
l'allowlist. L'invitation crée le compte `auth.users` via l'API admin —
fonctionne indépendamment du réglage d'inscription publique. Le trigger SQL
(`on_auth_user_created`) ajoute automatiquement la ligne correspondante dans
`admins` SI l'email est dans `admin_allowlist` — sinon le compte existe mais
n'a aucun accès (RLS renvoie zéro ligne).

Ordre recommandé : 2.2 (allowlist) puis 2.4 (invitation) — si vous invitez
avant d'allowlister, le compte n'obtient l'accès admin qu'après avoir ajouté
son email à `admin_allowlist` ET recréé le compte, le trigger ne se rejoue
pas rétroactivement. Dans ce cas, insérez directement dans `admins` :
`insert into admins (id, email) select id, email from auth.users where email = '...';`

## 3. Ce que VOUS devez faire sur Vercel (au moment du déploiement — pas encore)

- Variables d'environnement (Project Settings → Environment Variables) :
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` — jamais
  `SUPABASE_SERVICE_ROLE_KEY` (réservé au loader Python, exécuté en local/CI,
  jamais sur Vercel).
- Protection d'accès optionnelle en plus de l'auth applicative : Vercel
  **Deployment Protection** (Project Settings → Deployment Protection) peut
  ajouter une couche supplémentaire (mot de passe partagé ou SSO Vercel) au
  niveau du edge, avant même d'atteindre l'application. Utile en complément,
  pas un substitut à l'authentification Supabase déjà en place.
- Rappel : consigne explicite reçue de ne pas déployer pour l'instant — cette
  section est informative, à appliquer quand vous serez prêt.

## 4. Une fois les étapes 2.1-2.4 faites : ce qu'il reste de mon côté

1. Relancer `python src/persistence/load_to_supabase.py` (charge un nouveau
   `dataset_id` avec noms/âges dans un `students` désormais admin-only).
2. Re-vérifier l'accès anonyme : commande ci-dessous, exécutée maintenant
   (avant migration) pour référence — elle renvoie actuellement des lignes
   (normal, l'ancienne politique `lecture_publique` est encore active) :

   ```
   GET {SUPABASE_URL}/rest/v1/students?select=id&limit=3   avec la clé anon
   -> 200, 3 lignes retournées (état actuel, migration pas encore appliquée)
   ```

   Après votre migration, la même requête doit renvoyer soit `200` avec un
   tableau vide `[]` (RLS filtre toutes les lignes), soit une erreur
   d'autorisation — dans les deux cas, zéro ligne. Je referai ce test dès que
   vous confirmez la migration appliquée.
