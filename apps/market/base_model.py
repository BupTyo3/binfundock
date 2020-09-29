import logging

from abc import ABC, abstractmethod
from typing import Tuple, Union, Optional, Callable

from django.db import models

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus
from .base_client import BaseClient

logger = logging.getLogger(__name__)


class BaseMarket(SystemBaseModel):
    price_: str = 'price'
    quantity_: str = 'quantity'
    executed_quantity_: str = 'executed_quantity'
    status_: str = 'status'
    market_fee: float

    order_statuses: OrderStatus = OrderStatus

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def client_class(self) -> BaseClient:
        pass

    @property
    @abstractmethod
    def order_id_separator(self) -> str:
        pass

    @property
    def my_client(self):
        logger.debug('Get MY_CLIENT')
        return self.client_class.activate_connection()

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_current_balance(self, coin: str) -> float:
        pass

    @abstractmethod
    def get_order_info(self, symbol: Union[str, models.CharField], custom_order_id: str) -> Tuple[OrderStatus, float]:
        pass

    @abstractmethod
    def push_buy_limit_order(self, order):
        pass
