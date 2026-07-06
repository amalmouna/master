# Déploiement Vercel — étapes exactes

Ce document ne couvre que la mise en ligne du frontend Next.js. Aucun
déploiement n'a été effectué — ceci est la liste des actions à faire
vous-même dans le dashboard Vercel, dans l'ordre.

**Prérequis** (déjà faits, cf. `docs/AUTH_SETUP.md`) : migrations Supabase
002 et 003 appliquées, votre compte admin rattaché à `user_roles`, accès par
classe vérifié en direct. Ne déployez pas avant que ces trois points soient
confirmés — un déploiement public avec une RLS mal configurée expose des
données réelles.

## 1. Créer le projet Vercel

1. [vercel.com/new](https://vercel.com/new) → **Import Git Repository** →
   sélectionner ce dépôt.
2. **Root Directory** : cliquer *Edit* et choisir `frontend`. Le projet est
   un monorepo (pipeline Python à la racine, app Next.js dans `frontend/`) —
   sans ce réglage, Vercel cherche un `package.json` à la racine et échoue.
3. **Framework Preset** : Next.js (détecté automatiquement une fois le Root
   Directory correct). Build Command / Output Directory : laisser les
   valeurs par défaut (`next build`, gérées automatiquement).
4. Ne pas cliquer *Deploy* tout de suite — configurer les variables
   d'environnement et la version de Node d'abord (étapes 2-3 ci-dessous),
   sinon le premier déploiement échouera ou tournera avec la mauvaise config.

## 2. Variables d'environnement

**Project Settings → Environment Variables**, une par une, pour les
environnements Production + Preview (Development si vous utilisez `vercel dev`) :

| Nom | Valeur | Portée |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | URL du projet Supabase (`https://xxxx.supabase.co`) | Publique — visible dans le bundle client, c'est normal |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Clé `anon` du projet | Publique — visible dans le bundle client, c'est normal (RLS protège les données, pas cette clé) |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé `service_role` du projet | **Serveur uniquement** — jamais préfixée `NEXT_PUBLIC_`. Cochez l'option *Sensitive* si Vercel la propose sur votre plan. Nécessaire à l'écran Utilisateurs (`lib/supabase/admin.ts`), qui s'exécute exclusivement côté serveur (route/Server Action Next.js) — jamais envoyée au navigateur, vérifié directement sur le build compilé (voir note de vérification en bas de ce document). |

Les deux clés `anon` et `service_role` se trouvent dans le dashboard
Supabase : **Project Settings → API**.

## 3. Version de Node

**Project Settings → General → Node.js Version** → sélectionner **20.x**
(minimum requis par Next.js 16 ; le projet a aussi `"engines": {"node": ">=20.9.0"}`
dans `frontend/package.json`, mais c'est ce réglage-ci qui pilote réellement
le runtime de build/exécution sur Vercel).

## 4. Déployer

**Deployments → Deploy** (ou push sur la branche liée). Premier déploiement :
vérifiez dans les logs de build qu'il n'y a aucune erreur liée aux variables
d'environnement manquantes (`lib/supabase/*.ts` lève une erreur explicite au
démarrage si `NEXT_PUBLIC_SUPABASE_URL`/`ANON_KEY` sont absentes).

## 5. Protection d'accès (optionnelle, en plus de l'auth applicative)

**Project Settings → Deployment Protection** : mot de passe partagé ou SSO
Vercel au niveau edge, avant même d'atteindre l'application. Utile en
complément de l'authentification Supabase déjà en place (§ AUTH_SETUP.md),
pas un substitut.

## 6. Vérification post-déploiement (à faire vous-même une fois en ligne)

- Ouvrir l'URL de déploiement sans être connecté → doit rediriger vers `/login`.
- Se connecter avec le compte admin → toutes les classes visibles.
- (Optionnel) répéter le test d'accès par rôle de `docs/AUTH_SETUP.md` contre
  l'URL de production plutôt que `localhost`.

---

**Note de vérification (déjà faite en local, à reproduire si vous modifiez
`lib/supabase/admin.ts`)** : `npm run build` puis
`grep -rl "<valeur de la clé service_role>" .next/static` doit ne renvoyer
aucun fichier — la clé ne peut être injectée dans le bundle client que si
elle est nommée `NEXT_PUBLIC_*`, ce qui n'est pas le cas ici.
