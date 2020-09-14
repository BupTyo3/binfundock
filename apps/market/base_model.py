import logging

from abc import ABC, abstractmethod
from typing import Tuple, Union, Optional

from django.db import models

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus
from apps.pair.base_model import PairsData
from .base_client import BaseClient

logger = logging.getLogger(__name__)


class BaseMarket(SystemBaseModel):
    price_: str = 'price'
    quantity_: str = 'quantity'
    executed_quantity_: str = 'executed_quantity'
    status_: str = 'status'
    order_statuses: OrderStatus = OrderStatus
    order_id_separator: str
    pairs: PairsData
    client_class: BaseClient

    class Meta:
        abstract = True

    @property
    def my_client(self):
        logger.debug('Get MY_CLIENT')
        return self.client_class.activate_connection()
        # self.my_client: BaseClient = BaseClient(
        #     conf_obj.market_api_key, conf_obj.market_api_secret)
        # return self._my_client

    # @my_client.setter
    # def my_client(self, value):
    #     logger.debug('Set MY_CLIENT')
    #     self.my_client: BaseClient = BaseClient(
    #         conf_obj.market_api_key, conf_obj.market_api_secret)
    #     self._my_client = value

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
    def create_buy_limit_order(self, order):
        pass
