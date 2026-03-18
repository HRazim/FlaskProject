import json
import pytest
from unittest.mock import patch, MagicMock
from api8inf349.services import calculate_shipping_price, calculate_tax_rate


# ============================================================
# Tests unitaires : calculs
# ============================================================

class TestCalculateShippingPrice:
    def test_light_package(self):
        assert calculate_shipping_price(100) == 5.0
        assert calculate_shipping_price(499) == 5.0

    def test_medium_package(self):
        assert calculate_shipping_price(500) == 10.0
        assert calculate_shipping_price(1999) == 10.0

    def test_heavy_package(self):
        assert calculate_shipping_price(2000) == 25.0
        assert calculate_shipping_price(5000) == 25.0

    def test_zero_weight(self):
        assert calculate_shipping_price(0) == 5.0


class TestCalculateTaxRate:
    def test_quebec(self):
        assert calculate_tax_rate('QC') == 0.15

    def test_ontario(self):
        assert calculate_tax_rate('ON') == 0.13

    def test_alberta(self):
        assert calculate_tax_rate('AB') == 0.05

    def test_bc(self):
        assert calculate_tax_rate('BC') == 0.12

    def test_nova_scotia(self):
        assert calculate_tax_rate('NS') == 0.14

    def test_unknown_province(self):
        assert calculate_tax_rate('XX') == 0.0


# ============================================================
# Tests fonctionnels : endpoints API
# ============================================================

class TestGetProducts:
    def test_returns_products(self, client):
        response = client.get('/')
        assert response.status_code == 200
        data = response.get_json()
        assert 'products' in data
        assert len(data['products']) == 3

    def test_product_fields(self, client):
        response = client.get('/')
        data = response.get_json()
        product = data['products'][0]
        for field in ['id', 'name', 'description', 'price', 'weight', 'in_stock', 'image']:
            assert field in product


class TestCreateOrderSingleProduct:
    """Tests retrocompatibles : creation avec un seul produit."""

    def test_create_order_success(self, client):
        response = client.post('/order',
            data=json.dumps({'product': {'id': 1, 'quantity': 2}}),
            content_type='application/json'
        )
        assert response.status_code == 302
        assert 'Location' in response.headers
        assert '/order/' in response.headers['Location']

    def test_missing_product(self, client):
        response = client.post('/order',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 422
        data = response.get_json()
        assert data['errors']['product']['code'] == 'missing-fields'

    def test_missing_product_id(self, client):
        response = client.post('/order',
            data=json.dumps({'product': {'quantity': 1}}),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_quantity_zero(self, client):
        response = client.post('/order',
            data=json.dumps({'product': {'id': 1, 'quantity': 0}}),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_out_of_stock(self, client):
        response = client.post('/order',
            data=json.dumps({'product': {'id': 3, 'quantity': 1}}),
            content_type='application/json'
        )
        assert response.status_code == 422
        data = response.get_json()
        assert data['errors']['product']['code'] == 'out-of-inventory'


class TestCreateOrderMultiProducts:
    """Tests partie 2 : creation avec plusieurs produits."""

    def test_multi_product_order(self, client):
        response = client.post('/order',
            data=json.dumps({
                'products': [
                    {'id': 1, 'quantity': 2},
                    {'id': 2, 'quantity': 1},
                ]
            }),
            content_type='application/json'
        )
        assert response.status_code == 302
        location = response.headers['Location']
        order_id = int(location.rstrip('/').split('/')[-1])

        # Verifier que les deux produits sont dans la commande
        resp = client.get(f'/order/{order_id}')
        data = resp.get_json()
        assert len(data['order']['products']) == 2

    def test_multi_product_total_price(self, client):
        response = client.post('/order',
            data=json.dumps({
                'products': [
                    {'id': 1, 'quantity': 2},
                    {'id': 2, 'quantity': 1},
                ]
            }),
            content_type='application/json'
        )
        location = response.headers['Location']
        order_id = int(location.rstrip('/').split('/')[-1])

        resp = client.get(f'/order/{order_id}')
        data = resp.get_json()
        # 28.1*2 + 29.45*1 = 85.65
        assert data['order']['total_price'] == 85.65

    def test_multi_product_shipping(self, client):
        response = client.post('/order',
            data=json.dumps({
                'products': [
                    {'id': 1, 'quantity': 2},
                    {'id': 2, 'quantity': 1},
                ]
            }),
            content_type='application/json'
        )
        location = response.headers['Location']
        order_id = int(location.rstrip('/').split('/')[-1])

        resp = client.get(f'/order/{order_id}')
        data = resp.get_json()
        # Poids : 400*2 + 299*1 = 1099g -> 10$
        assert data['order']['shipping_price'] == 10.0

    def test_multi_product_one_out_of_stock(self, client):
        response = client.post('/order',
            data=json.dumps({
                'products': [
                    {'id': 1, 'quantity': 1},
                    {'id': 3, 'quantity': 1},
                ]
            }),
            content_type='application/json'
        )
        assert response.status_code == 422
        data = response.get_json()
        assert data['errors']['product']['code'] == 'out-of-inventory'

    def test_empty_products_list(self, client):
        response = client.post('/order',
            data=json.dumps({'products': []}),
            content_type='application/json'
        )
        assert response.status_code == 422


class TestGetOrder:
    def test_get_order(self, client, sample_order):
        response = client.get(f'/order/{sample_order}')
        assert response.status_code == 200
        data = response.get_json()
        assert 'order' in data
        order = data['order']
        assert order['id'] == sample_order
        assert order['paid'] == False
        # Partie 2 : products est une liste
        assert isinstance(order['products'], list)
        assert order['products'][0]['id'] == 1
        assert order['products'][0]['quantity'] == 2

    def test_order_not_found(self, client):
        response = client.get('/order/99999')
        assert response.status_code == 404

    def test_initial_order_fields(self, client, sample_order):
        response = client.get(f'/order/{sample_order}')
        data = response.get_json()
        order = data['order']
        assert order['email'] is None
        assert order['shipping_information'] == {}
        assert order['credit_card'] == {}
        assert order['transaction'] == {}
        assert order['paid'] == False


class TestUpdateOrderClientInfo:
    def test_update_shipping(self, client, sample_order):
        response = client.put(f'/order/{sample_order}',
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
        assert response.status_code == 200
        data = response.get_json()
        order = data['order']
        assert order['email'] == 'test@example.com'
        assert order['shipping_information']['province'] == 'QC'

    def test_tax_calculation_qc(self, client, sample_order):
        client.put(f'/order/{sample_order}',
            data=json.dumps({
                'order': {
                    'email': 'test@example.com',
                    'shipping_information': {
                        'country': 'Canada',
                        'address': '123 Test St',
                        'postal_code': 'G7X 3Y7',
                        'city': 'Quebec',
                        'province': 'QC'
                    }
                }
            }),
            content_type='application/json'
        )
        response = client.get(f'/order/{sample_order}')
        data = response.get_json()
        order = data['order']
        # total_price = 28.1 * 2 = 56.2, shipping = 5.0 (800g)
        expected_tax = round((56.2 + 5.0) * 1.15, 2)
        assert order['total_price_tax'] == expected_tax

    def test_missing_email(self, client, sample_order):
        response = client.put(f'/order/{sample_order}',
            data=json.dumps({
                'order': {
                    'shipping_information': {
                        'country': 'Canada',
                        'address': '123',
                        'postal_code': 'G7X',
                        'city': 'Quebec',
                        'province': 'QC'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_missing_shipping_field(self, client, sample_order):
        response = client.put(f'/order/{sample_order}',
            data=json.dumps({
                'order': {
                    'email': 'test@example.com',
                    'shipping_information': {
                        'country': 'Canada',
                        'province': 'QC'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_order_not_found(self, client):
        response = client.put('/order/99999',
            data=json.dumps({
                'order': {
                    'email': 'test@example.com',
                    'shipping_information': {
                        'country': 'Canada',
                        'address': '123',
                        'postal_code': 'G7X',
                        'city': 'Quebec',
                        'province': 'QC'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 404


class TestPaymentAsync:
    """Tests partie 2 : paiement asynchrone via RQ."""

    def test_payment_returns_202(self, client, sample_order_with_shipping):
        """Le paiement doit retourner 202 (traitement en arriere-plan)."""
        response = client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 202

    def test_payment_without_shipping_returns_422(self, client, sample_order):
        response = client.put(f'/order/{sample_order}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_processing_order_returns_409_on_put(self, client, sample_order_with_shipping):
        """Une commande en cours de paiement retourne 409 sur PUT."""
        # Premier paiement -> 202
        client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        # Deuxieme tentative -> 409
        response = client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 409

    def test_processing_order_returns_202_on_get(self, client, sample_order_with_shipping):
        """GET sur une commande en cours de paiement retourne 202."""
        client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        response = client.get(f'/order/{sample_order_with_shipping}')
        assert response.status_code == 202

    def test_update_shipping_on_processing_returns_409(self, client, sample_order_with_shipping):
        """Modifier les infos client d'une commande en cours retourne 409."""
        client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'credit_card': {
                    'name': 'John Doe',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 9
                }
            }),
            content_type='application/json'
        )
        response = client.put(f'/order/{sample_order_with_shipping}',
            data=json.dumps({
                'order': {
                    'email': 'new@email.com',
                    'shipping_information': {
                        'country': 'Canada',
                        'address': '456',
                        'postal_code': 'H2X',
                        'city': 'Montreal',
                        'province': 'QC'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 409


class TestRedisCache:
    """Tests du cache Redis."""

    def test_cached_order_returned(self, client, app, sample_order):
        """Si une commande est dans le cache, elle est retournee depuis Redis."""
        cached_data = {
            'order': {
                'id': sample_order,
                'paid': True,
                'total_price': 100.0,
                'products': [{'id': 1, 'quantity': 2}],
            }
        }
        app.redis.get.return_value = json.dumps(cached_data).encode()

        response = client.get(f'/order/{sample_order}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['order']['paid'] == True


class TestHTMLPages:
    def test_html_home(self, client):
        response = client.get('/html')
        assert response.status_code == 200
        assert b'Boutique en ligne' in response.data

    def test_html_order(self, client, sample_order):
        response = client.get(f'/html/order/{sample_order}')
        assert response.status_code == 200
        assert b'Commande' in response.data


# ============================================================
# Test d integration : flux complet
# ============================================================

class TestFullOrderFlow:
    def test_complete_flow_multi_product(self, client):
        # 1. Lister les produits
        response = client.get('/')
        assert response.status_code == 200

        # 2. Creer une commande multi-produits
        response = client.post('/order',
            data=json.dumps({
                'products': [
                    {'id': 1, 'quantity': 1},
                    {'id': 2, 'quantity': 2},
                ]
            }),
            content_type='application/json'
        )
        assert response.status_code == 302
        location = response.headers['Location']
        order_id = int(location.rstrip('/').split('/')[-1])

        # 3. Verifier la commande
        response = client.get(f'/order/{order_id}')
        assert response.status_code == 200
        order = response.get_json()['order']
        assert len(order['products']) == 2
        assert order['paid'] == False

        # 4. Ajouter infos client
        response = client.put(f'/order/{order_id}',
            data=json.dumps({
                'order': {
                    'email': 'flow@test.com',
                    'shipping_information': {
                        'country': 'Canada',
                        'address': '789 Flow St',
                        'postal_code': 'H2X 1Y4',
                        'city': 'Montreal',
                        'province': 'ON'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

        # 5. Payer (retourne 202 en async)
        response = client.put(f'/order/{order_id}',
            data=json.dumps({
                'credit_card': {
                    'name': 'Test User',
                    'number': '4242 4242 4242 4242',
                    'expiration_year': 2030,
                    'cvv': '123',
                    'expiration_month': 12
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 202

        # 6. La commande est en traitement
        response = client.get(f'/order/{order_id}')
        assert response.status_code == 202
