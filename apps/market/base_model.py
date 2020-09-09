from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus
from apps.pair.models import Pair
from apps.pair.base_model import PairsData


class Market(SystemBaseModel):
    price_: str = 'price'
    quantity_: str = 'quantity'
    executed_quantity_: str = 'executed_quantity'
    status_: str = 'status'
    order_statuses: OrderStatus = OrderStatus
    order_id_separator: str
    pairs: PairsData
    pair_class: Pair

    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pairs: PairsData = dict()
        self.name: str = name

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_current_balance(self, coin: str) -> float:
        pass

    @abstractmethod
    def get_order_info(self, symbol: str, order_id: str) -> Tuple[OrderStatus, float]:
        pass

    @abstractmethod
    def create_buy_limit_order(self, order):
        pass
