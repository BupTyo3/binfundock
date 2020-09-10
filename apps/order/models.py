import logging

from django.db import models
from django.contrib.auth import get_user_model

from .base_model import Order
from apps.order.utils import OrderStatus
from apps.market.models import Market
from apps.signal.models import Signal
from typing import List

User = get_user_model()
logger = logging.getLogger(__name__)


class BuyOrder(Order):
    type_: str = 'buy'
    order_type_separator: str = 'b'
    market = models.ForeignKey(to=Market,
                               related_name='buy_orders',
                               on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=16)
    quantity = models.FloatField()
    price = models.FloatField()
    bought_quantity = models.FloatField(default=0)
    custom_order_id = models.CharField(max_length=30)
    _status = models.CharField(max_length=32,
                               choices=OrderStatus.choices(),
                               default=OrderStatus.NOT_SENT.value,
                               db_column='status')
    index = models.PositiveIntegerField()
    signal = models.ForeignKey(to=Signal,
                               related_name='buy_orders',
                               on_delete=models.DO_NOTHING)

    def save(self, *args, **kwargs):
        self.custom_order_id = self.form_order_id(self.market.order_id_separator, self.signal_id, self.index)
        super().save(*args, **kwargs)

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
        self.status, self.bought_quantity = self.market.objects.get_order_info(self.symbol, self.custom_order_id)
        # self.fake_complete()


class SellOrder(Order):
    type_: str = 'sell'
    order_type_separator: str = 's'
    market = models.ForeignKey(to=Market,
                               related_name='sell_orders',
                               on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=16)
    quantity = models.FloatField()
    price = models.FloatField()
    stop_loss = models.FloatField()
    sold_quantity = models.FloatField(default=0)
    custom_order_id = models.CharField(max_length=30)
    _status = models.CharField(max_length=32,
                               choices=OrderStatus.choices(),
                               default=OrderStatus.NOT_SENT.value,
                               db_column='status')
    index = models.PositiveIntegerField()
    signal = models.ForeignKey(to=Signal,
                               related_name='sell_orders',
                               on_delete=models.DO_NOTHING)

    def save(self, *args, **kwargs):
        self.custom_order_id = self.form_order_id(self.market.order_id_separator, self.signal_id, self.index)
        super().save(*args, **kwargs)

    def create_real(self):
        logger.debug('Create real sell order')
        # todo послать запрос на размещение ордера


# typing
BuyData = List[BuyOrder]

SellData = List[SellOrder]

