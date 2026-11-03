# Gestion des documents d’achat

Frontend React destiné à consulter les bons de commande ERP, numériser les BL et factures, et gérer les réceptions Urium.

## Développement

Prérequis : Node.js 20.19+ ou 22.12+.

```powershell
cd frontend
npm install
npm run dev
```

Le mode développement utilise le backend réel par défaut. Pour prévisualiser les profils de démonstration sans backend, définir explicitement `VITE_USE_MOCKS=true` ; le menu « Profil de démonstration » permet alors de parcourir les neuf profils. Les données de démonstration sont remises à zéro au rechargement du serveur.

Pour utiliser l’API réelle, définir `VITE_USE_MOCKS=false` dans `.env.local` (ou laisser la valeur par défaut) ; Vite transmet alors `/api` à `API_PROXY_TARGET` (par défaut `http://localhost:8000`). Le client utilise des chemins relatifs pour conserver la session et le cookie CSRF sur la même origine. Pour une configuration Docker, `API_PROXY_TARGET` vise le service backend, par exemple `http://backend:8000`.

## Vérification

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

## Structure

- `src/app` : shell, routes, contexte utilisateur et pages.
- `src/api` : client HTTP et traitement des erreurs d’API.
- `src/components` : composants réutilisables à extraire au fil des écrans.
- `src/i18n/fr.ts` : libellés français communs et états.
- `src/mocks` : réponses MSW, profils et jeux de données pour les deux ERP.
- `src/test` : tests de permissions pour les neuf profils et de validation de BR.

Le contrat commun utilisé par l’interface et le backend est :

- `GET /api/me` : utilisateur, entreprise, permissions, types scannables et options.
- `POST /api/auth/login` et `POST /api/auth/logout` : session Django ; les écritures transmettent le jeton CSRF.
- `POST /api/auth/changer-mot-de-passe/` : vérifie l’ancien mot de passe, applique les validateurs Django et conserve la session.
- `GET /api/bc` et `GET /api/bc/{id}` : commandes normalisées pour l’interface, avec l’identifiant local numérique et la référence ERP.
- `GET /api/scans`, `POST /api/scans`, `GET/PATCH/DELETE /api/scans/{id}` et `POST /api/scans/{id}/resynchroniser` : documents normalisés. La création multipart utilise `ids_bc` (tableau JSON d’identifiants), `type`, `numero_document` et `fichier`.
- `GET /api/tableau-de-bord` et `GET /api/journal` : indicateurs calculés depuis les données locales et journal filtré par période.
- `GET /api/etat-services` : vérifie en direct l’authentification ERP et l’accès au dossier racine Drive.
- `GET/POST /api/utilisateurs`, `PATCH /api/utilisateurs/{id}` : gestion des comptes de l’entreprise et des rôles disponibles. Les créations et réinitialisations renvoient un mot de passe temporaire visible une seule fois dans la réponse.
- `POST /api/bc/{id}/br`, `GET/PATCH /api/br/{id}`, `POST /api/br/{id}/valider`, `POST /api/br/{id}/annuler` et `GET /api/br/{id}/pdf` : cycle de vie Urium, validation avec numérotation atomique, PDF archivé sur Drive et annulation auditée.

Les contrôles d’accès de l’interface sont dérivés de `GET /api/me.permissions` avec `useCan` et `<Can permission="...">`. Le backend vérifie lui-même les permissions et répond avec les statuts HTTP 401/403 ; le masquage de l’interface n’est pas une protection serveur. Les chemins historiques Django `/api/auth/...` et `/api/documents/...` restent disponibles.

Pour les commandes Odoo, `completude` représente la présence d’un BL et d’une facture (50 % chacun). Pour Urium, il représente la part des quantités commandées déjà réceptionnées.

Pour ajouter un rôle, compléter la réponse `/api/me` dans `src/mocks/data.ts` avec ses permissions et ses types scannables, puis ajouter un cas de test. L’interface ne dépend pas du nom du rôle. Pour ajouter un écran, créer sa route dans `src/app/App.tsx`, protéger la route par permission et fournir les états chargement, erreur, vide et hors ligne.

## Fonctionnalités de démonstration

- Recherche et dossier BC, liste de documents, journal, profil et administration des utilisateurs.
- Ajout de scans avec choix multiple de BC, validation du numéro et du type selon `/api/me`, captures d’images compressées à 2 000 px et regroupées en PDF.
- Réception Urium avec quantités limitées au reste à recevoir, brouillon, confirmation, réauthentification optionnelle et annulation avec motif.
- Navigation adaptée au bureau et au mobile, bandeau hors ligne, erreurs explicites et export CSV pour les utilisateurs ayant accès à tous les scans.

MSW reste disponible uniquement pour les démonstrations et tests ; les pages d’administration, du tableau de bord, du journal et des réceptions utilisent les API backend en mode réel. La validation et le téléchargement PDF nécessitent une configuration Google Drive opérationnelle. L’adaptateur Urium n’invente plus de commandes de démonstration : il signale un connecteur indisponible tant que son mode d’accès ERP n’est pas défini.

## Services externes et déploiement

Les fichiers `.env.example.odoo_co` et `.env.example.urium_co` ne contiennent que des valeurs d’exemple. Après les avoir copiés vers `.env.odoo_co` ou `.env.urium_co`, remplacer les valeurs fictives et lancer Compose avec le fichier correspondant, par exemple `docker compose --env-file .env.urium_co up -d`. `COMPOSE_ENV_FILE` permet à Compose de transmettre ce même fichier aux conteneurs.

La procédure complète de préparation, de contrôle de configuration, de sauvegarde et de démarrage est décrite dans [DEPLOYMENT.md](../DEPLOYMENT.md).

Pour Google Drive, `GOOGLE_KEY_FILE_SOURCE` désigne le fichier JSON du compte de service sur l’hôte Docker ; le fichier est monté en lecture seule et devient `/run/secrets/google_key.json` dans les conteneurs (`GOOGLE_KEY_FILE`). Ne pas placer le JSON, les clés ERP ou les mots de passe dans le dépôt ou dans les fichiers d’exemple ; les fournir par le mécanisme de secrets du déploiement.

Le connecteur Urium REST n’est pas implémentable sans son contrat non secret : URL de base, endpoints et méthodes de recherche/détail, authentification attendue, exemples JSON des commandes et lignes, pagination/erreurs, et décision sur l’export des BR validés. Aucune connexion réelle Urium ou Google Drive n’a été testée ici.
