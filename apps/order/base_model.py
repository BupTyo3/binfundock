import logging

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict

from utils.framework.models import SystemBaseModel
from apps.order.utils import OrderStatus
from apps.market.base_model import Market
from tools.tools import gen_short_uuid

logger = logging.getLogger(__name__)


class Order(SystemBaseModel):
    order_id: Optional[str]
    market: Market
    symbol: str
    quantity: float
    price: float
    signal_id: Optional[int]
    index: Optional[int]
    stop_loss: Optional[float]
    status: OrderStatus

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status = OrderStatus.NOT_SENT
        self.stop_loss = None

    @property
    def status(self):
        logger.debug('Get Order status')
        return self._status

    @status.setter
    def status(self, value):
        logger.debug(f'Set Order status: {self._status.__str__()} -> {value}')
        self._status = value

    @property
    @abstractmethod
    def order_type_separator(self) -> str:
        pass

    def form_order_id(self,
                      market_separator: str,
                      message_id: Optional[int],
                      index: Optional[int]) -> str:
        if not (message_id or index):
            return f'{market_separator}_{self.order_type_separator}_{gen_short_uuid()}'
        return f'{market_separator}_{str(message_id)}_{self.order_type_separator}_{index}'


