"""
api8inf349 - Application Web de commandes e-commerce (Partie 2)
Package principal avec Application Factory Pattern.
PostgreSQL + Redis + RQ worker.
"""

import os
import click
import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

from flask import Flask
from redis import Redis
from rq import Queue
from peewee import PostgresqlDatabase

from .models import database_proxy, Product, Order, OrderProduct, ShippingInformation, CreditCard, Transaction


def get_db_config(app_config):
    """Retourne la config PostgreSQL depuis les variables d'environnement."""
    return {
        'host': app_config.get('DB_HOST', os.environ.get('DB_HOST', 'localhost')),
        'user': app_config.get('DB_USER', os.environ.get('DB_USER', 'user')),
        'password': app_config.get('DB_PASSWORD', os.environ.get('DB_PASSWORD', 'pass')),
        'port': int(app_config.get('DB_PORT', os.environ.get('DB_PORT', '5432'))),
        'database': app_config.get('DB_NAME', os.environ.get('DB_NAME', 'api8inf349')),
    }


def create_app(test_config=None):
    """Application Factory."""
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        PRODUCTS_URL='http://dimensweb.uqac.ca/~jgnault/shops/products/',
        PAYMENT_URL='http://dimensweb.uqac.ca/~jgnault/shops/pay/',
        REDIS_URL=os.environ.get('REDIS_URL', 'redis://localhost'),
        DB_HOST=os.environ.get('DB_HOST', 'localhost'),
        DB_USER=os.environ.get('DB_USER', 'user'),
        DB_PASSWORD=os.environ.get('DB_PASSWORD', 'pass'),
        DB_PORT=os.environ.get('DB_PORT', '5432'),
        DB_NAME=os.environ.get('DB_NAME', 'api8inf349'),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if app.debug else logging.INFO)

    # Initialiser PostgreSQL via Peewee
    from peewee import PostgresqlDatabase
    db_conf = get_db_config(app.config)
    db = PostgresqlDatabase(
        db_conf['database'],
        host=db_conf['host'],
        port=db_conf['port'],
        user=db_conf['user'],
        password=db_conf['password'],
    )
    database_proxy.initialize(db)

    # Initialiser Redis
    redis_url = app.config['REDIS_URL']
    app.redis = Redis.from_url(redis_url)
    app.task_queue = Queue(connection=app.redis)

    @app.before_request
    def before_request():
        if database_proxy.is_closed():
            database_proxy.connect()

    @app.teardown_request
    def teardown_request(exception):
        if not database_proxy.is_closed():
            database_proxy.close()

    from .routes import bp
    app.register_blueprint(bp)

    @app.cli.command('init-db')
    def init_db_command():
        """Initialise les tables et recupere les produits."""
        init_db(app)
        click.echo('Base de donnees initialisee avec succes.')

    @app.cli.command('worker')
    def worker_command():
        """Lance le worker RQ pour traiter les paiements."""
        from rq import Worker
        worker = Worker([app.task_queue], connection=app.redis)
        worker.work()

    return app


def init_db(app):
    """Cree les tables et recupere les produits."""
    if database_proxy.is_closed():
        database_proxy.connect()
    try:
        database_proxy.create_tables([
            Product, Order, OrderProduct,
            ShippingInformation, CreditCard, Transaction
        ])
        app.logger.info('Tables creees avec succes.')
        _fetch_products(app)
    finally:
        if not database_proxy.is_closed():
            database_proxy.close()


def _fetch_products(app):
    """Recupere les produits depuis le service distant."""
    url = app.config['PRODUCTS_URL']
    app.logger.info(f'Recuperation des produits depuis {url}')
    try:
        req = Request(url, headers={'Accept': 'application/json'})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        products = data.get('products', [])
        app.logger.info(f'{len(products)} produits recuperes.')

        for p in products:
            # Clean the description of potential NUL characters
            clean_description = p.get('description', '').replace('\x00', '')

            Product.insert(
                id=p['id'],
                name=p['name'],
                description=clean_description,  # Use the cleaned version
                price=p['price'],
                weight=p.get('weight', 0),
                in_stock=p.get('in_stock', False),
                image=p.get('image', '')
            ).on_conflict(
                conflict_target=[Product.id],
                update={
                    Product.name: p['name'],
                    Product.description: clean_description,  # Use the cleaned version here too
                    Product.price: p['price'],
                    Product.weight: p.get('weight', 0),
                    Product.in_stock: p.get('in_stock', False),
                    Product.image: p.get('image', ''),
                }
            ).execute()

        app.logger.info('Produits persistes en base de donnees.')
    except URLError as e:
        app.logger.error(f'Erreur recuperation produits : {e}')
        raise
    except (json.JSONDecodeError, KeyError) as e:
        app.logger.error(f'Erreur parsing produits : {e}')
        raise
