import logging

from django.db import models
from django.contrib.auth import get_user_model
from .base_model import Order
from apps.order.utils import OrderStatus
from typing import List, Optional, Union

User = get_user_model()
logger = logging.getLogger(__name__)

#
# class Order(SystemBaseModel):
#     """
#     Model of Pet entity
#     """
#
#     breed = models.CharField(max_length=100)
#     nickname = models.CharField(max_length=100)
#     owner = models.ForeignKey(
#         to=User,
#         related_name='owner_of_pets',
#         on_delete=models.CASCADE)
#
#     def __str__(self):
#         return f"{self.nickname}: {self.breed}: {self.owner}"


class BuyOrder(Order):
    type_: str = 'buy'
    order_type_separator: str = 'b'

    def __init__(self, market, symbol, quantity, price, signal_id=None, index=None):
        super().__init__()
        self.market = market
        self.symbol = symbol
        self.quantity = quantity
        self.price = price
        self.bought_quantity: float = 0
        self.status = OrderStatus.NOT_SENT
        self.order_id = self.form_order_id(market.order_id_separator, signal_id, index)

    def create_real(self):
        logger.debug('Create real buy order')
        # todo послать запрос на размещение ордера
        self.market.create_buy_limit_order(self)

    def fake_complete(self):
        # Fake - Типа сработал ордер
        if self.market.get_current_price(self.symbol) < self.price:
            self.bought_quantity = self.quantity
            self.status = OrderStatus.COMPLETED

    def update_info_by_api(self):
        logger.debug('Get info about order by API')
        # TODO удалить после проверок
        self.status, self.bought_quantity = self.market.get_order_info(self.symbol, self.order_id)
        # self.fake_complete()


class SellOrder(Order):
    type_: str = 'sell'
    order_type_separator: str = 's'

    def __init__(self, market, symbol, quantity, price, stop_loss=None, signal_id=None, index=None):
        super().__init__()
        self.market = market
        self.symbol = symbol
        self.quantity = quantity
        self.price = price
        self.stop_loss = stop_loss
        self.sold_quantity: float = 0
        self.status = OrderStatus.NOT_SENT
        self.order_id = self.form_order_id(market.order_id_separator, signal_id, index)

    def create_real(self):
        logger.debug('Create real sell order')
        # todo послать запрос на размещение ордера


# typing
BuyData = List[BuyOrder]

SellData = List[SellOrder]

