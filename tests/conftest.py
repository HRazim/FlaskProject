import json
import pytest
from unittest.mock import MagicMock, patch
from peewee import SqliteDatabase

from api8inf349.models import (
    database_proxy, Product, Order, OrderProduct,
    ShippingInformation, CreditCard, Transaction
)


SAMPLE_PRODUCTS = [
    {
        'id': 1, 'name': 'Brown eggs',
        'description': 'Raw organic brown eggs in a basket',
        'price': 28.1, 'weight': 400, 'in_stock': True, 'image': '0.jpg'
    },
    {
        'id': 2, 'name': 'Sweet fresh strawberry',
        'description': 'Sweet fresh strawberry on the wooden table',
        'price': 29.45, 'weight': 299, 'in_stock': True, 'image': '1.jpg'
    },
    {
        'id': 3, 'name': 'Out of stock item',
        'description': 'This item is not available',
        'price': 50.0, 'weight': 1000, 'in_stock': False, 'image': '2.jpg'
    },
]


@pytest.fixture
def app(tmp_path):
    """Cree une application de test avec SQLite et Redis mocke."""
    db_path = str(tmp_path / 'test.db')
    test_db = SqliteDatabase(db_path)

    # Patch PostgresqlDatabase pour utiliser SQLite dans les tests
    with patch('api8inf349.PostgresqlDatabase', return_value=test_db):
        from api8inf349 import create_app
        app = create_app(test_config={
            'TESTING': True,
            'PRODUCTS_URL': 'http://test.local/products/',
            'PAYMENT_URL': 'http://test.local/pay/',
            'REDIS_URL': 'redis://localhost',
            'DB_HOST': 'localhost',
            'DB_USER': 'user',
            'DB_PASSWORD': 'pass',
            'DB_PORT': '5432',
            'DB_NAME': 'test',
        })

    # Initialiser avec SQLite pour les tests
    database_proxy.initialize(test_db)
    if database_proxy.is_closed():
        database_proxy.connect()

    database_proxy.create_tables([
        Product, Order, OrderProduct,
        ShippingInformation, CreditCard, Transaction
    ])

    for p in SAMPLE_PRODUCTS:
        Product.create(**p)

    # Mocker Redis et RQ
    app.redis = MagicMock()
    app.redis.get.return_value = None
    app.task_queue = MagicMock()

    if not database_proxy.is_closed():
        database_proxy.close()

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_order(client):
    response = client.post('/order',
        data=json.dumps({'product': {'id': 1, 'quantity': 2}}),
        content_type='application/json'
    )
    location = response.headers.get('Location', '')
    order_id = int(location.rstrip('/').split('/')[-1])
    return order_id


@pytest.fixture
def sample_order_with_shipping(client, sample_order):
    client.put(f'/order/{sample_order}',
        data=json.dumps({
            'order': {
                'email': 'test@example.com',
                'shipping_information': {
                    'country': 'Canada',
                    'address': '201, rue President-Kennedy',
                    'postal_code': 'G7X 3Y7',
                    'city': 'Chicoutimi',
                    'province': 'QC'
                }
            }
        }),
        content_type='application/json'
    )
    return sample_order
