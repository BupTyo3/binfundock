import logging

from abc import abstractmethod
from typing import Optional

from django.db import models
from django.db.models import F
from django.utils import timezone

from utils.framework.models import SystemBaseModel, SystemBaseModelWithoutModified
from apps.order.utils import OrderStatus
from tools.tools import gen_short_uuid

logger = logging.getLogger(__name__)


class BaseOrder(SystemBaseModel):
    stop_loss_separator: str = '_sl_'
    custom_order_id: Optional[str]
    symbol: str
    quantity: float
    price: float
    outer_signal_id: Optional[models.PositiveIntegerField]
    index: Optional[models.PositiveIntegerField]
    stop_loss: Optional[float]
    status: OrderStatus

    symbol = models.CharField(max_length=16)
    quantity = models.FloatField()
    price = models.FloatField()
    push_count = models.PositiveIntegerField(default=0)
    custom_order_id = models.CharField(max_length=55)
    handled_worked = models.BooleanField(
        help_text="Did something if the order has worked",
        default=False)
    local_canceled = models.BooleanField(default=False)
    local_canceled_time = models.DateTimeField(blank=True,
                                               null=True)
    no_need_push = models.BooleanField(
        help_text="No need push the order to the market",
        default=False)
    last_updated_by_api = models.DateTimeField(blank=True,
                                               null=True)

    class Meta:
        abstract = True

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        logger.debug(f'Set Order status: {self}: {self._status.upper()} -> {value.upper()}')
        self._status = value

    @property
    @abstractmethod
    def order_type_separator(self) -> str:
        pass

    def form_order_id(self,
                      market_separator: str,
                      message_id: Optional[int],
                      techannel_abbr: str,
                      index: Optional[int]) -> str:
        if not (message_id or index or techannel_abbr):
            return f'{market_separator}_{self.order_type_separator}_{gen_short_uuid()}'
        return f'{market_separator}_{techannel_abbr}_{str(message_id)}' \
               f'_{self.order_type_separator}_{index}'

    @classmethod
    def form_sl_order_id(cls, main_order: 'BaseOrder') -> str:
        return f"{main_order.custom_order_id}_{cls.stop_loss_separator}"

    def push_count_increase(self):
        self.push_count = F('push_count') + 1
        self.save()

    def _set_updated_by_api_without_saving(self):
        """Update last_updated_by_api field by current time"""
        self.last_updated_by_api = timezone.now()


class HistoryApiBaseOrder(SystemBaseModelWithoutModified):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Disable update"""
        if self.pk is None:
            super().save(*args, **kwargs)
