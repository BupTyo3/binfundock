import logging

from abc import abstractmethod
from typing import Optional

from django.db import models

from utils.framework.models import SystemBaseModel
from apps.order.utils import OrderStatus
from tools.tools import gen_short_uuid

logger = logging.getLogger(__name__)


class Order(SystemBaseModel):
    custom_order_id: Optional[str]
    symbol: str
    quantity: float
    price: float
    signal_id: Optional[models.PositiveIntegerField]
    index: Optional[models.PositiveIntegerField]
    stop_loss: Optional[float]
    status: OrderStatus

    class Meta:
        abstract = True

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
                      index: Optional[models.PositiveIntegerField]) -> str:
        if not (message_id or index):
            return f'{market_separator}_{self.order_type_separator}_{gen_short_uuid()}'
        return f'{market_separator}_{str(message_id)}_{self.order_type_separator}_{index}'


