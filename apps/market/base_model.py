from abc import ABC, abstractmethod
from typing import Tuple

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus
from apps.pair.base_model import PairsData


class BaseMarket(SystemBaseModel):
    price_: str = 'price'
    quantity_: str = 'quantity'
    executed_quantity_: str = 'executed_quantity'
    status_: str = 'status'
    order_statuses: OrderStatus = OrderStatus
    order_id_separator: str
    pairs: PairsData

    class Meta:
        abstract = True

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_current_balance(self, coin: str) -> float:
        pass

    @abstractmethod
    def get_order_info(self, symbol: str, custom_order_id: str) -> Tuple[OrderStatus, float]:
        pass

    @abstractmethod
    def create_buy_limit_order(self, order):
        pass
