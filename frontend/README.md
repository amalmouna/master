# Frontend — tableau de bord Next.js

Next.js 16 (App Router, Tailwind v4). Nécessite Node ≥ 20.9 (voir `engines`
dans `package.json` — Next.js 16 refuse de démarrer sur une version plus
ancienne).

## Développement local

```bash
npm install
cp .env.example .env.local   # renseigner NEXT_PUBLIC_SUPABASE_URL/ANON_KEY
                              # + SUPABASE_SERVICE_ROLE_KEY (écran Utilisateurs)
npm run dev
```

## Déploiement

Voir [`docs/DEPLOY.md`](../docs/DEPLOY.md) (variables d'environnement Vercel,
version de Node, étapes exactes dans le dashboard). Voir aussi
[`docs/AUTH_SETUP.md`](../docs/AUTH_SETUP.md) pour l'authentification/les rôles.
