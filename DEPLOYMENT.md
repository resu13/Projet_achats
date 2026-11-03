# Préparer un déploiement

Les fichiers `.env.example.odoo_co` et `.env.example.urium_co` sont des modèles vides, pas des configurations utilisables. Il faut une instance et un fichier d’environnement par entreprise. Ne jamais copier des secrets dans Git, le chat ou les journaux.

## Valeurs et fichiers à fournir

Copier le modèle adapté vers `.env.odoo_co` ou `.env.urium_co`, puis renseigner :

- Une `SECRET_KEY` unique (au moins 50 caractères) et `DB_PASSWORD` (au moins 20 caractères), générées et conservées dans le coffre de secrets du déploiement. Par exemple, générer localement avec `python -c "import secrets; print(secrets.token_urlsafe(64))"` ; faire deux générations différentes.
- `ALLOWED_HOSTS` avec les seuls noms DNS de production ; le nom doit aussi figurer dans le certificat TLS.
- Les paramètres entreprise (`ENTREPRISE`, `ERP_TYPE`, `NOM_ENTREPRISE`) et le vrai `DRIVE_FOLDER_ID`.
- Conserver un `COMPOSE_PROJECT_NAME` unique par entreprise pour isoler les volumes PostgreSQL, Redis et médias.
- Le JSON du compte de service Google, partagé en accès minimal sur le dossier Drive choisi. Définir `GOOGLE_KEY_FILE_SOURCE` vers son chemin hôte, hors dépôt.
- Le certificat TLS et sa clé privée sans chiffrement interactif, dans `TLS_CERT_FILE_SOURCE` et `TLS_KEY_FILE_SOURCE`. Leur paire doit correspondre. Les sources sont montées en lecture seule dans Nginx.
- Pour Odoo : URL, base, utilisateur technique dédié à permissions minimales et clé API, fournis par le coffre de secrets.

Pour Urium, le déploiement web peut être préparé, mais les fonctions dépendant des BC ERP ne sont pas opérationnelles tant que le contrat REST (URL, routes, authentification, formats) n’est pas défini et implémenté. L’export des BR n’est pas prévu selon le périmètre actuel.

## Contrôle avant démarrage

Depuis la racine du projet, sur l’hôte Docker :

```sh
scripts/check-deployment.sh .env.odoo_co
docker compose --env-file .env.odoo_co run --rm migrate python manage.py check --deploy
docker compose --env-file .env.odoo_co run --rm migrate python manage.py showmigrations --plan
```

Le script vérifie les valeurs de production, la présence du compte de service, la validité de la paire TLS et ses noms DNS, la configuration Compose et les paramètres Odoo. Il ne contacte pas les services distants. Ne pas lancer le démarrage/migration de production avant d’avoir terminé et vérifié la sauvegarde.

## Sauvegarde, démarrage et contrôles

Faire une sauvegarde avant chaque déploiement, et automatiser l’exécution régulière sur l’hôte :

```sh
scripts/backup-postgres.sh .env.odoo_co
docker compose --env-file .env.odoo_co up -d --build
docker compose --env-file .env.odoo_co ps
docker compose --env-file .env.odoo_co logs --since 15m backend migrate celery nginx
docker compose --env-file .env.odoo_co exec nginx nginx -t
docker compose --env-file .env.odoo_co exec backend python manage.py migrate --check
```

Le script sauvegarde PostgreSQL au format custom et archive aussi le volume média (logo/configuration entreprise), puis vérifie la lisibilité des deux archives ; les artefacts sont enregistrés sous `backups/` avec des permissions restrictives et ne sont pas versionnés. Définir une rétention chiffrée et une copie hors hôte selon le RPO/RTO attendu. Tester périodiquement une restauration dans une base isolée et vérifier également la récupération des documents Drive ; un dump non restauré n’est pas une preuve de reprise.

Les journaux applicatifs et Nginx vont vers Docker avec rotation (10 Mo, cinq fichiers par conteneur). Nginx omet les paramètres de requête des lignes d’accès ; ne pas activer de journalisation des corps HTTP ou des secrets. Centraliser les journaux avec une rétention et un contrôle d’accès définis par l’exploitation.

`check --deploy` peut signaler que HSTS n’inclut pas les sous-domaines et n’est pas préchargé. C’est volontaire par défaut : activer ces options seulement après avoir vérifié que tous les sous-domaines concernés sont exclusivement accessibles en HTTPS.

Compose exécute les migrations et `collectstatic` dans un service ponctuel avant de démarrer le backend ; une migration en échec bloque le service. Le backend a un contrôle de disponibilité HTTP. Les services externes restent à tester après démarrage via `GET /api/etat-services`, puis par un téléversement et une resynchronisation contrôlés sur un environnement de recette.

Le montage TLS attend des fichiers présents avant `docker compose up`. HSTS est limité à l’hôte ; n’activer `includeSubDomains`/`preload` que lorsque tous les sous-domaines concernés servent HTTPS.
