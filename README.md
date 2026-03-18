# api8inf349 - Projet de session Partie 2

Application Web Flask pour le traitement de commandes e-commerce.
PostgreSQL + Redis + RQ (paiement asynchrone).

## Prerequis

- Python 3.6+ (3.11 recommande)
- PostgreSQL 12
- Redis 5
- Docker et Docker Compose (optionnel)

## Installation rapide avec Docker

```bash
# Lancer PostgreSQL et Redis
docker-compose up -d

# Construire l'image de l'application
docker build -t api8inf349 .

# Lancer le container de l'app
docker run -d --name api-app \
  -e REDIS_URL=redis://host.docker.internal \
  -e DB_HOST=host.docker.internal -e DB_USER=user \
  -e DB_PASSWORD=pass -e DB_PORT=5432 -e DB_NAME=api8inf349 \
  -p 5000:5000 api8inf349

# init db avec docker
docker exec -it api-app flask init-db
```

## Installation manuelle

```bash
pip install -r requirements.txt
```

## Variables d'environnement

| Variable    | Description                      | Exemple               |
|-------------|----------------------------------|-----------------------|
| DB_HOST     | Hote PostgreSQL                  | localhost             |
| DB_USER     | Utilisateur PostgreSQL           | user                  |
| DB_PASSWORD | Mot de passe PostgreSQL          | pass                  |
| DB_PORT     | Port PostgreSQL                  | 5432                  |
| DB_NAME     | Nom de la base de donnees        | api8inf349            |
| REDIS_URL   | URL de connexion Redis           | redis://localhost     |
| FLASK_APP   | Module Flask                     | api8inf349            |
| FLASK_DEBUG | Mode debug                       | True                  |

## Initialisation de la base de donnees

```bash
export FLASK_APP=api8inf349 FLASK_DEBUG=True
export REDIS_URL=redis://localhost
export DB_HOST=localhost DB_USER=user DB_PASSWORD=pass DB_PORT=5432 DB_NAME=api8inf349

flask init-db
```

## Lancement de l'application

```bash
flask run
```

## Lancement du worker RQ (paiement en arriere-plan)

```bash
flask worker
```

## Interface HTML

Accessible a http://127.0.0.1:5000/html

## Tests

```bash
pip install pytest pytest-flask
python -m pytest tests/ -v
```

## Architecture

```
api8inf349/
  __init__.py         # Application Factory, init-db, worker CLI
  models.py           # Modeles Peewee (PostgreSQL via DatabaseProxy)
  routes.py           # Endpoints API REST + routes HTML
  services.py         # Logique metier, paiement async, cache Redis
  templates/
    index.html        # Page produits + panier
    order.html        # Page commande + formulaires
tests/
  conftest.py         # Fixtures pytest (SQLite pour tests)
  test_app.py         # Tests unitaires, fonctionnels, integration
Dockerfile            # Image Docker de l'application
docker-compose.yml    # PostgreSQL 12 + Redis 5
CODES-PERMANENTS      # Codes permanents des membres
requirements.txt
```

## Changements Partie 2

- **PostgreSQL** : remplacement de SQLite (connexion via variables d'env)
- **Redis** : cache des commandes payees + backend pour RQ
- **RQ Worker** : paiement asynchrone en arriere-plan (flask worker)
- **Multi-produits** : POST /order accepte 'products' (liste) en plus de 'product'
- **Resilience** : commandes payees mises en cache Redis, servies sans Postgres
- **Statut 202** : commande en cours de paiement
- **Statut 409** : tentative de modification pendant le paiement
- **Erreurs persistees** : les erreurs du service distant sont stockees dans Transaction
- **Frontend HTML** : pages pour lister produits, creer commandes, payer
- **Docker** : Dockerfile + docker-compose.yml
