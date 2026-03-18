"""
Modeles Peewee pour l'application e-commerce api8inf349.
Utilise un DatabaseProxy pour supporter PostgreSQL.
"""

import datetime
from peewee import (
    DatabaseProxy, Model, AutoField, CharField, TextField,
    FloatField, IntegerField, BooleanField, ForeignKeyField,
    DateTimeField
)

# Proxy qui sera initialise dans create_app() avec PostgresqlDatabase
database_proxy = DatabaseProxy()


class BaseModel(Model):
    """Modele de base avec connexion via proxy."""
    class Meta:
        database = database_proxy


class Product(BaseModel):
    """Produit du catalogue."""
    id = IntegerField(primary_key=True)
    name = CharField()
    description = TextField(default='')
    price = FloatField()
    weight = IntegerField(default=0)
    in_stock = BooleanField(default=False)
    image = CharField(default='')

    class Meta:
        table_name = 'products'


class Order(BaseModel):
    """Commande client."""
    id = AutoField(primary_key=True)
    total_price = FloatField(default=0)
    total_price_tax = FloatField(default=0)
    shipping_price = FloatField(default=0)
    email = CharField(null=True, default=None)
    paid = BooleanField(default=False)
    # Statut pour le traitement asynchrone du paiement
    # Valeurs : 'created', 'processing', 'paid', 'error'
    payment_status = CharField(default='created')
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = 'orders'


class OrderProduct(BaseModel):
    """Association commande-produit (supporte plusieurs produits)."""
    id = AutoField(primary_key=True)
    order = ForeignKeyField(Order, backref='order_products', on_delete='CASCADE')
    product = ForeignKeyField(Product, backref='order_products', on_delete='CASCADE')
    quantity = IntegerField()

    class Meta:
        table_name = 'order_products'


class ShippingInformation(BaseModel):
    """Informations de livraison."""
    id = AutoField(primary_key=True)
    order = ForeignKeyField(Order, backref='shipping_info', unique=True, on_delete='CASCADE')
    country = CharField()
    address = CharField()
    postal_code = CharField()
    city = CharField()
    province = CharField()

    class Meta:
        table_name = 'shipping_information'


class CreditCard(BaseModel):
    """Carte de credit masquee (apres paiement)."""
    id = AutoField(primary_key=True)
    order = ForeignKeyField(Order, backref='credit_card_info', unique=True, on_delete='CASCADE')
    name = CharField()
    first_digits = CharField()
    last_digits = CharField()
    expiration_year = IntegerField()
    expiration_month = IntegerField()

    class Meta:
        table_name = 'credit_cards'


class Transaction(BaseModel):
    """Transaction de paiement avec support des erreurs."""
    id = AutoField(primary_key=True)
    order = ForeignKeyField(Order, backref='transaction_info', unique=True, on_delete='CASCADE')
    transaction_id = CharField(default='')
    success = BooleanField()
    amount_charged = FloatField()
    # Champ erreur pour persister les erreurs du service distant
    error_code = CharField(default='')
    error_name = CharField(default='')

    class Meta:
        table_name = 'transactions'
