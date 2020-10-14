import logging

from abc import abstractmethod
from typing import Optional, List, TYPE_CHECKING

from django.db import models
from django.db.models import F
from django.utils import timezone

from utils.framework.models import SystemBaseModel, SystemBaseModelWithoutModified
from apps.order.utils import OrderStatus, OrderType
from tools.tools import gen_short_uuid, debug_input_and_returned

if TYPE_CHECKING:
    from apps.signal.base_model import BaseSignal

logger = logging.getLogger(__name__)


class BaseOrder(SystemBaseModel):
    stop_loss_separator: str = 'sl'
    number_copies_separator: str = 'cc'
    custom_order_id: Optional[str]
    symbol: str
    quantity: float
    price: float
    outer_signal_id: Optional[models.PositiveIntegerField]
    index: Optional[models.PositiveIntegerField]
    stop_loss: Optional[float]
    status: str
    signal: "BaseSignal"

    symbol = models.CharField(max_length=16)
    quantity = models.FloatField()
    price = models.FloatField()
    _status = models.CharField(max_length=32,
                               choices=OrderStatus.choices(),
                               default=OrderStatus.NOT_SENT.value,
                               db_column='status')
    type = models.CharField(max_length=32,
                            choices=OrderType.choices(),
                            default=OrderType.LIMIT.value)
    push_count = models.PositiveIntegerField(default=0)
    custom_order_id = models.CharField(max_length=36)
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

    objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Addition: Form custom_order_id on creation
        """
        if not self.pk and not self.custom_order_id:
            self.custom_order_id = self.form_order_id(
                message_id=self.signal.outer_signal_id,
                techannel_abbr=self.signal.techannel.abbr,
                index=self.index)
        super().save(*args, **kwargs)

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
                      message_id: Optional[int],
                      techannel_abbr: str,
                      index: Optional[int]) -> str:
        start_number_of_copies = 0
        if not (message_id or index or techannel_abbr):
            return f'{start_number_of_copies}{self.order_type_separator}_{gen_short_uuid()}'
        return f'{start_number_of_copies}{self.order_type_separator}_{techannel_abbr}_{message_id}_{index}'

    @classmethod
    def form_sl_order_id(cls, main_order: 'BaseOrder') -> str:
        return f"{main_order.custom_order_id.rstrip(cls.stop_loss_separator)}_{cls.stop_loss_separator}"

    def push_count_increase(self):
        self.push_count = F('push_count') + 1
        self.save()

    def _set_updated_by_api_without_saving(self):
        """Update last_updated_by_api field by current time"""
        self.last_updated_by_api = timezone.now()


class BaseBuyOrder(BaseOrder):
    type_: str = 'buy'
    order_type_separator: str = 'bb'

    class Meta:
        abstract = True

    @classmethod
    @debug_input_and_returned
    def get_min_price_order(cls,
                            signal: 'BaseSignal',
                            statuses: Optional[List[OrderStatus]] = None) -> Optional['BaseOrder']:
        params = {'signal': signal}
        if statuses:
            params.update({'_status__in': statuses})
        return cls.objects.filter(**params).order_by('-price').last()

    @classmethod
    @debug_input_and_returned
    def get_max_price_order(cls,
                            signal: 'BaseSignal',
                            statuses: Optional[List[OrderStatus]] = None) -> Optional['BaseOrder']:
        params = {'signal': signal}
        if statuses:
            params.update({'_status__in': statuses})
        return cls.objects.filter(**params).order_by('price').last()


class BaseSellOrder(BaseOrder):
    type_: str = 'sell'
    order_type_separator: str = 'ss'

    class Meta:
        abstract = True

    @classmethod
    @debug_input_and_returned
    def get_min_price_order(cls,
                            signal: 'BaseSignal',
                            statuses: Optional[List[OrderStatus]] = None,
                            stop_loss_orders: bool = False) -> Optional['BaseOrder']:
        """
        Function to get a SellOrder with min price
         (choose from stop_loss orders or take_profit orders)
        """
        params = {'signal': signal}
        if statuses:
            params.update({'_status__in': statuses})
        if stop_loss_orders:
            return cls.objects.filter(**params).exclude(tp_order=None).order_by('-price').last()
        else:
            return cls.objects.filter(**params).exclude(sl_order=None).order_by('-price').last()

    @classmethod
    @debug_input_and_returned
    def get_max_price_order(cls,
                            signal: 'BaseSignal',
                            statuses: Optional[List[OrderStatus]] = None,
                            stop_loss_orders: bool = False) -> Optional['BaseOrder']:
        """
        Function to get a SellOrder with min price
         (choose from stop_loss orders or take_profit orders)
        """
        params = {'signal': signal}
        if statuses:
            params.update({'_status__in': statuses})
        if stop_loss_orders:
            return cls.objects.filter(**params).exclude(tp_order=None).order_by('price').last()
        else:
            return cls.objects.filter(**params).exclude(sl_order=None).order_by('price').last()


class HistoryApiBaseOrder(SystemBaseModelWithoutModified):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Disable update"""
        if self.pk is None:
            super().save(*args, **kwargs)
