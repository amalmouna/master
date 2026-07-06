# Déploiement du backend d'import (Render) — étapes exactes

Ce document ne couvre que la mise en ligne du backend FastAPI (`backend/`).
**Aucun déploiement n'a été effectué** — ceci est la liste des actions à
faire vous-même dans le dashboard Render, dans l'ordre. `render.yaml` décrit
la configuration mais ne déploie rien tant que vous ne créez pas
explicitement l'instance de blueprint.

**Prérequis** : le frontend Next.js doit avoir une URL de production connue
(même provisoire) avant l'étape 3 — CORS est verrouillé à cette origine
exacte, pas à `*`.

## 1. Créer le service sur Render

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**.
2. Connecter ce dépôt Git, branche `main`. Render détecte `render.yaml` à la
   racine et propose de créer le service `massar-import-backend` décrit
   dedans (type web, Python, `rootDir: backend`). Le champ `region` a été
   volontairement laissé en commentaire dans `render.yaml` (aucune
   information du projet ne justifie un choix par défaut) — Render vous
   demandera d'en choisir une à la création ; prenez la plus proche de votre
   projet Supabase.
3. Le champ de blueprint utilisé (`runtime: python`) correspond au schéma
   Render actuel au moment de l'écriture de ce fichier ; si l'interface
   Render vous signale un champ inconnu/obsolète à l'import, c'est que leur
   schéma a changé depuis — remplacez simplement par ce que Render propose
   pour "service web Python", le reste de `render.yaml` (build/start
   command, `rootDir`, `envVars`) reste valable.
4. **Apply** — Render crée le service mais le premier déploiement échouera
   tant que les secrets (étape 2) ne sont pas renseignés ; c'est normal, ne
   pas s'inquiéter d'un premier échec de build/démarrage à ce stade.

## 2. Variables d'environnement (secrets)

**Service → Environment**, une par une (aucune n'est dans `render.yaml`,
volontairement — `sync: false` les laisse vides tant que vous ne les
saisissez pas ici) :

| Nom | Valeur | Portée |
|---|---|---|
| `SUPABASE_URL` | URL du projet Supabase (`https://xxxx.supabase.co`) | Serveur uniquement |
| `SUPABASE_ANON_KEY` | Clé `anon` — utilisée UNIQUEMENT pour vérifier le token de l'appelant (jamais pour écrire) | Serveur uniquement |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé `service_role` — écrit les résultats de l'import, contourne RLS | **Secret, jamais côté client** |
| `MASSAR_SALT` | Le sel déjà utilisé en local (`data/artifacts/.salt` — ouvrez-le et copiez son contenu tel quel) | **Secret** — sans ça, le premier redeploy change le sel et un même élève changerait de `student_pseudo` d'une année à l'autre |
| `FRONTEND_ORIGIN` | URL exacte de votre frontend Vercel, ex. `https://votre-projet.vercel.app` (plusieurs origines séparées par des virgules si vous ajoutez un domaine de preview) | Non secret, mais doit être exact — pas de `*` |

Les clés `anon`/`service_role` : dashboard Supabase → **Project Settings → API**.

Après avoir renseigné les 5, **Manual Deploy → Deploy latest commit** pour
relancer un build avec les secrets disponibles.

## 3. Vérifier que CORS est bien verrouillé

`backend/app/main.py` refuse toute origine si `FRONTEND_ORIGIN` est absent
(échec fermé — pas de repli permissif). Si vous voyez dans les logs Render :

```
FRONTEND_ORIGIN non défini : aucune origine autorisée en CORS (échec fermé).
```

→ le service tourne mais **aucun navigateur ne pourra l'appeler**, ce qui est
le comportement voulu tant que l'étape 2 n'est pas complète — pas un bug.

## 4. Vérification post-déploiement

Une fois le déploiement "Live" dans le dashboard, notez l'URL Render (ex.
`https://massar-import-backend.onrender.com`) et testez :

```bash
curl -s https://massar-import-backend.onrender.com/health
# attendu : {"status":"ok"}
```

Si `/health` répond mais que le premier `/import` réel échoue avec une
erreur `FileNotFoundError` sur un `.joblib` : vérifiez que
`data/artifacts/models/*.joblib` a bien été commité (cf. exception ciblée
dans `.gitignore`) et poussé — sans ça, Render clone un `data/artifacts/`
vide.

Testez ensuite l'authentification (sans lancer de vrai import) :

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://massar-import-backend.onrender.com/import -F "academic_year=test"
# attendu : 401 (pas de header Authorization)
```

Ne testez le chemin `/import` complet (avec un vrai token admin et de vrais
fichiers) qu'une fois prêt à écrire réellement dans Supabase — cet endpoint
n'a pas de mode `--dry-run`.

## 5. Risque RAM du tier gratuit (512 Mo) — à surveiller

Le tier `free` de Render plafonne à **512 Mo de RAM par instance**. Le
pipeline (`pandas`, `numpy`, `scikit-learn`, `openpyxl`, plusieurs `.xlsx`
chargés en mémoire pendant un import) a un coût mémoire réel, sans qu'on
puisse le chiffrer précisément sans le mesurer en conditions réelles sur
Render (l'empreinte locale n'est pas un indicateur fiable de l'environnement
contraint de Render).

**Signal exact indiquant qu'il faut passer au tier payant** — l'un de ces
deux, observés ensemble ou séparément :

1. **Dans les logs Render** : une ligne explicite du type
   `Ran out of memory (used over 512Mi)` ou le service qui redémarre seul
   juste après un appel à `/import`, sans qu'aucune ligne
   `Échec import (academic_year=...)` (notre propre gestion d'erreur,
   loggée avant toute exception) n'apparaisse avant le redémarrage — signe
   que le process a été tué (OOM kill) plutôt que d'avoir levé une exception
   Python normale.
2. **Côté client** : la requête `/import` se termine par une erreur de
   connexion brute (timeout, "connection reset", ou un `502`/`503` renvoyé
   par le proxy Render lui-même) **au lieu d'** une réponse JSON avec un
   `detail` — nos propres erreurs (400/409/500) renvoient toujours un JSON
   structuré ; leur absence totale signifie que le process n'a pas survécu
   assez longtemps pour répondre.

Si vous observez l'un des deux sur un import de taille réelle (75 fichiers,
~480 élèves), passez au tier payant le moins cher avec plus de RAM plutôt que
d'essayer d'optimiser le pipeline sous contrainte — le tier gratuit est fait
pour valider que le déploiement fonctionne, pas pour l'usage réel en
production sur ce projet.
