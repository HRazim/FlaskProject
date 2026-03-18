"""
Routes API REST et pages HTML pour api8inf349.
"""

import os
from flask import (
    Blueprint, jsonify, request, redirect, url_for,
    current_app, render_template, make_response
)

from . import services

bp = Blueprint('api', __name__)


# ============================================================
# API REST
# ============================================================

@bp.route('/', methods=['GET'])
def get_products():
    """GET / : retourne la liste des produits en JSON."""
    products = services.get_all_products()
    return jsonify({'products': products}), 200


@bp.route('/order', methods=['POST'])
def create_order():
    """
    POST /order : cree une nouvelle commande.
    Supporte un seul produit (retrocompatible) ou plusieurs.
    """
    data = request.get_json(force=True, silent=True)

    if not data:
        return jsonify({
            'errors': {
                'product': {
                    'code': 'missing-fields',
                    'name': "La creation d'une commande necessite un produit"
                }
            }
        }), 422

    # Support retrocompatible : 'product' (singulier) ou 'products' (pluriel)
    products_data = None

    if 'products' in data:
        products_data = data['products']
        if not isinstance(products_data, list) or len(products_data) == 0:
            return jsonify({
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }), 422
    elif 'product' in data:
        product = data['product']
        if not isinstance(product, dict):
            return jsonify({
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }), 422
        # Valider id et quantity
        if 'id' not in product or 'quantity' not in product:
            return jsonify({
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }), 422
        quantity = product['quantity']
        if not isinstance(quantity, int) or quantity < 1:
            return jsonify({
                'errors': {
                    'product': {
                        'code': 'missing-fields',
                        'name': "La creation d'une commande necessite un produit"
                    }
                }
            }), 422
        products_data = [product]
    else:
        return jsonify({
            'errors': {
                'product': {
                    'code': 'missing-fields',
                    'name': "La creation d'une commande necessite un produit"
                }
            }
        }), 422

    order, error = services.create_order(products_data)

    if error:
        return jsonify(error), 422

    return redirect(url_for('api.get_order', order_id=order.id), code=302)


@bp.route('/order/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """
    GET /order/<order_id> : retourne les details d'une commande.
    Verifie le cache Redis en premier pour les commandes payees.
    Si la commande est en cours de paiement, retourne 202.
    """
    # Verifier le cache Redis en premier
    cached = services.get_order_from_cache(order_id, current_app.redis)
    if cached:
        return jsonify(cached), 200

    # Verifier le statut de paiement
    status = services.get_payment_status(order_id)
    if status is None:
        return '', 404
    if status == 'processing':
        return '', 202

    result = services.get_order(order_id)
    if result is None:
        return '', 404

    return jsonify(result), 200


@bp.route('/order/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    """
    PUT /order/<order_id> : met a jour infos client OU traite le paiement.
    """
    data = request.get_json(force=True, silent=True)

    if not data:
        return jsonify({
            'errors': {
                'order': {
                    'code': 'missing-fields',
                    'name': 'Il manque un ou plusieurs champs qui sont obligatoires',
                }
            }
        }), 422

    has_credit_card = 'credit_card' in data
    has_order = 'order' in data

    if has_credit_card and has_order:
        return jsonify({
            'errors': {
                'order': {
                    'code': 'missing-fields',
                    'name': 'Il manque un ou plusieurs champs qui sont obligatoires',
                }
            }
        }), 422

    if has_order:
        result, error, status = services.update_order_client_info(order_id, data)
        if status == 404:
            return '', 404
        if status == 409:
            return '', 409
        if error:
            return jsonify(error), status
        return jsonify(result), 200

    elif has_credit_card:
        # Recuperer la config DB pour le worker
        db_config = {
            'host': current_app.config['DB_HOST'],
            'user': current_app.config['DB_USER'],
            'password': current_app.config['DB_PASSWORD'],
            'port': int(current_app.config['DB_PORT']),
            'database': current_app.config['DB_NAME'],
        }

        error, status = services.enqueue_payment(
            order_id,
            data['credit_card'],
            current_app.task_queue,
            current_app.config['PAYMENT_URL'],
            current_app.config['REDIS_URL'],
            db_config,
        )

        if status == 404:
            return '', 404
        if status == 409:
            return '', 409
        if status == 202:
            return '', 202
        if error:
            return jsonify(error), status
        return '', status

    else:
        return jsonify({
            'errors': {
                'order': {
                    'code': 'missing-fields',
                    'name': 'Il manque un ou plusieurs champs qui sont obligatoires',
                }
            }
        }), 422


# ============================================================
# Interface utilisateur HTML
# ============================================================

@bp.route('/html', methods=['GET'])
def html_home():
    """Page d'accueil HTML : liste des produits."""
    return render_template('index.html')


@bp.route('/html/order/<int:order_id>', methods=['GET'])
def html_order(order_id):
    """Page HTML d'une commande."""
    return render_template('order.html', order_id=order_id)
