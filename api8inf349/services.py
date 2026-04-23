"""
Services metier pour api8inf349.
Gestion des commandes, calculs, paiement asynchrone, cache Redis.
"""

import json
import logging
import os
from typing import Dict, Any, Optional, Tuple, List
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from .models import (
    database_proxy, Product, Order, OrderProduct,
    ShippingInformation, CreditCard, Transaction
)

logger = logging.getLogger(__name__)

# Taux de taxe par province
TAX_RATES = {
    'QC': 0.15,
    'ON': 0.13,
    'AB': 0.05,
    'BC': 0.12,
    'NS': 0.14,
}


def calculate_shipping_price(total_weight: int) -> float:
    """Calcule les frais d'expedition selon le poids total (grammes)."""
    if total_weight < 500:
        return 5.0
    elif total_weight < 2000:
        return 10.0
    else:
        return 25.0


def calculate_tax_rate(province: str) -> float:
    """Retourne le taux de taxe selon la province."""
    return TAX_RATES.get(province, 0.0)


def get_all_products() -> list:
    """Recupere tous les produits de la BD."""
    products = Product.select()
    return [
        {
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': p.price,
            'weight': p.weight,
            'in_stock': p.in_stock,
            'image': p.image,
        }
        for p in products
    ]


def create_order(products_data: list) -> Tuple[Optional[Order], Optional[Dict]]:
    """
    Cree une commande avec un ou plusieurs produits.

    Args:
        products_data: Liste de dicts {'id': ..., 'quantity': ...}

    Returns:
        Tuple (order, error).
    """
    # Valider chaque produit
    total_price = 0.0
    total_weight = 0
    validated_products = []

    for item in products_data:
        product_id = item.get('id')
        quantity = item.get('quantity')

        if product_id is None or quantity is None:
            return None, {
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }

        if not isinstance(quantity, int) or quantity < 1:
            return None, {
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }

        try:
            product = Product.get_by_id(product_id)
        except Product.DoesNotExist:
            return None, {
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }

        if not product.in_stock:
            return None, {
                'errors': {
                    'product': {
                        'code': 'out-of-inventory',
                        'name': "Le produit demande n'est pas en inventaire"
                    }
                }
            }

        total_price += product.price * quantity
        total_weight += product.weight
        validated_products.append((product, quantity))

    shipping_price = calculate_shipping_price(total_weight)

    order = Order.create(
        total_price=total_price,
        shipping_price=shipping_price,
        paid=False,
        payment_status='created',
    )

    for product, quantity in validated_products:
        OrderProduct.create(order=order, product=product, quantity=quantity)

    return order, None


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    """Recupere les details complets d'une commande."""
    try:
        order = Order.get_by_id(order_id)
    except Order.DoesNotExist:
        return None
    return _format_order(order)


def get_order_from_cache(order_id: int, redis_client) -> Optional[Dict]:
    """Tente de recuperer une commande depuis le cache Redis."""
    try:
        cached = redis_client.get(f'order:{order_id}')
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f'Erreur lecture cache Redis : {e}')
    return None


def cache_order(order_id: int, order_data: Dict, redis_client):
    """Met en cache une commande payee dans Redis."""
    try:
        redis_client.set(f'order:{order_id}', json.dumps(order_data))
    except Exception as e:
        logger.warning(f'Erreur ecriture cache Redis : {e}')


def get_payment_status(order_id: int) -> Optional[str]:
    """Recupere le statut de paiement d'une commande."""
    try:
        order = Order.get_by_id(order_id)
        return order.payment_status
    except Order.DoesNotExist:
        return None


def _format_order(order: Order) -> Dict[str, Any]:
    """Formate une commande en dictionnaire JSON."""
    # Produits associes (format liste pour multi-produits)
    order_products = OrderProduct.select().where(OrderProduct.order == order)
    products_data = [
        {'id': op.product_id, 'quantity': op.quantity}
        for op in order_products
    ]

    # Infos livraison
    shipping_info = ShippingInformation.get_or_none(ShippingInformation.order == order)
    shipping_data = {}
    if shipping_info:
        shipping_data = {
            'country': shipping_info.country,
            'address': shipping_info.address,
            'postal_code': shipping_info.postal_code,
            'city': shipping_info.city,
            'province': shipping_info.province,
        }

    # Carte de credit
    cc = CreditCard.get_or_none(CreditCard.order == order)
    cc_data = {}
    if cc:
        cc_data = {
            'name': cc.name,
            'first_digits': cc.first_digits,
            'last_digits': cc.last_digits,
            'expiration_year': cc.expiration_year,
            'expiration_month': cc.expiration_month,
        }

    # Transaction (avec champ error)
    txn = Transaction.get_or_none(Transaction.order == order)
    txn_data = {}
    if txn:
        error_data = {}
        if txn.error_code:
            error_data = {
                'code': txn.error_code,
                'name': txn.error_name,
            }
        txn_data = {
            'id': txn.transaction_id,
            'success': txn.success,
            'error': error_data,
            'amount_charged': txn.amount_charged,
        }

    return {
        'order': {
            'id': order.id,
            'total_price': order.total_price,
            'total_price_tax': order.total_price_tax,
            'email': order.email,
            'credit_card': cc_data,
            'shipping_information': shipping_data,
            'paid': order.paid,
            'transaction': txn_data,
            'products': products_data,
            'shipping_price': order.shipping_price,
        }
    }


def update_order_client_info(order_id: int, data: Dict) -> Tuple[Optional[Dict], Optional[Dict], int]:
    """Met a jour les informations client (email + shipping)."""
    try:
        order = Order.get_by_id(order_id)
    except Order.DoesNotExist:
        return None, None, 404

    # Verifier si la commande est en cours de paiement
    if order.payment_status == 'processing':
        return None, None, 409

    order_data = data.get('order', {})
    email = order_data.get('email')
    shipping = order_data.get('shipping_information', {})

    required_shipping_fields = ['country', 'address', 'postal_code', 'city', 'province']
    missing = not email or not shipping
    if not missing:
        missing = any(not shipping.get(f) for f in required_shipping_fields)

    if missing:
        return None, {
            'errors': {
                'order': {
                    'code': 'missing-fields',
                    'name': 'Il manque un ou plusieurs champs qui sont obligatoires',
                }
            }
        }, 422

    province = shipping['province']
    tax_rate = calculate_tax_rate(province)
    total_price_tax = (order.total_price + order.shipping_price) * (1 + tax_rate)

    order.email = email
    order.total_price_tax = round(total_price_tax, 2)
    order.save()

    ShippingInformation.delete().where(ShippingInformation.order == order).execute()
    ShippingInformation.create(
        order=order,
        country=shipping['country'],
        address=shipping['address'],
        postal_code=shipping['postal_code'],
        city=shipping['city'],
        province=shipping['province'],
    )

    return _format_order(order), None, 200


def enqueue_payment(order_id: int, credit_card_data: Dict, task_queue, payment_url: str, redis_url: str, db_config: Dict) -> Tuple[Optional[Dict], int]:
    """
    Valide et met en file d'attente le paiement via RQ.
    Retourne (error_body, status_code).
    """
    try:
        order = Order.get_by_id(order_id)
    except Order.DoesNotExist:
        return None, 404

    if order.payment_status == 'processing':
        return None, 409

    if order.paid:
        return {
            'errors': {
                'order': {
                    'code': 'already-paid',
                    'name': 'La commande a deja ete payee.'
                }
            }
        }, 422

    has_email = order.email is not None and order.email != ''
    has_shipping = ShippingInformation.get_or_none(ShippingInformation.order == order) is not None

    if not has_email or not has_shipping:
        return {
            'errors': {
                'order': {
                    'code': 'missing-fields',
                    'name': "Les informations du client sont necessaire avant d'appliquer une carte de credit"
                }
            }
        }, 422

    # Marquer la commande comme en cours de traitement
    order.payment_status = 'processing'
    order.save()

    # Envoyer la tache au worker RQ
    task_queue.enqueue(
        process_payment_task,
        order_id,
        credit_card_data,
        payment_url,
        redis_url,
        db_config,
    )

    return None, 202


def process_payment_task(order_id: int, credit_card_data: Dict, payment_url: str, redis_url: str, db_config: Dict):
    """
    Tache RQ : traite le paiement en arriere-plan.
    Cette fonction est executee par le worker, hors du contexte Flask.
    """
    from peewee import PostgresqlDatabase
    from redis import Redis

    # Reconnecter a PostgreSQL dans le worker
    db = PostgresqlDatabase(
        db_config['database'],
        host=db_config['host'],
        port=db_config['port'],
        user=db_config['user'],
        password=db_config['password'],
    )
    database_proxy.initialize(db)
    if database_proxy.is_closed():
        database_proxy.connect()

    redis_client = Redis.from_url(redis_url)

    try:
        order = Order.get_by_id(order_id)
        amount_charged = order.total_price_tax

        payment_body = {
            'credit_card': credit_card_data,
            'amount_charged': amount_charged,
        }

        try:
            result = _call_payment_service(payment_url, payment_body)

            # Paiement reussi
            cc_info = result.get('credit_card', {})
            txn_info = result.get('transaction', {})

            CreditCard.delete().where(CreditCard.order == order).execute()
            CreditCard.create(
                order=order,
                name=cc_info.get('name', ''),
                first_digits=cc_info.get('first_digits', ''),
                last_digits=cc_info.get('last_digits', ''),
                expiration_year=cc_info.get('expiration_year', 0),
                expiration_month=cc_info.get('expiration_month', 0),
            )

            Transaction.delete().where(Transaction.order == order).execute()
            Transaction.create(
                order=order,
                transaction_id=txn_info.get('id', ''),
                success=txn_info.get('success', False),
                amount_charged=txn_info.get('amount_charged', 0),
                error_code='',
                error_name='',
            )

            if txn_info.get('success', False):
                order.paid = True
                order.payment_status = 'paid'
            else:
                order.payment_status = 'error'
            order.save()

        except PaymentError as e:
            # Erreur du service distant -> persister l'erreur
            error_body = e.error_body
            # Extraire le code et le nom de l'erreur
            credit_card_error = error_body.get('errors', {}).get('credit_card', {})
            if not credit_card_error:
                credit_card_error = error_body.get('credit_card', {})

            Transaction.delete().where(Transaction.order == order).execute()
            Transaction.create(
                order=order,
                transaction_id='',
                success=False,
                amount_charged=amount_charged,
                error_code=credit_card_error.get('code', ''),
                error_name=credit_card_error.get('name', ''),
            )

            order.payment_status = 'error'
            order.paid = False
            order.save()

        # Mettre en cache si la commande est payee
        if order.paid:
            order_data = _format_order(order)
            cache_order(order.id, order_data, redis_client)

    finally:
        if not database_proxy.is_closed():
            database_proxy.close()


class PaymentError(Exception):
    """Exception levee quand le service de paiement retourne une erreur."""
    def __init__(self, error_body: Dict):
        self.error_body = error_body
        super().__init__(str(error_body))


def _call_payment_service(url: str, body: Dict) -> Dict:
    """Appelle le service de paiement distant."""
    data = json.dumps(body).encode('utf-8')
    req = Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')

    try:
        with urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        error_body = json.loads(e.read().decode('utf-8'))
        logger.warning(f'Erreur du service de paiement : {error_body}')
        raise PaymentError(error_body)
    except URLError as e:
        logger.error(f'Erreur de connexion au service de paiement : {e}')
        raise PaymentError({
            'errors': {
                'credit_card': {
                    'code': 'service-unavailable',
                    'name': 'Le service de paiement est indisponible'
                }
            }
        })