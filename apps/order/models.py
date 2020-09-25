import logging

from typing import TYPE_CHECKING

from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.order.utils import OrderStatus
from apps.market.models import Market
from apps.signal.models import Signal
from .base_model import BaseOrder, HistoryApiBaseOrder

if TYPE_CHECKING:
    from apps.market.base_model import BaseMarket

User = get_user_model()
logger = logging.getLogger(__name__)


class BuyOrder(BaseOrder):
    type_: str = 'buy'
    order_type_separator: str = 'b'
    market = models.ForeignKey(to=Market,
                               related_name='buy_orders',
                               on_delete=models.DO_NOTHING)
    # TODO: remove this field and _bought_quantity and setters, getters and others using
    bought_quantity = models.FloatField(default=0)
    _status = models.CharField(max_length=32,
                               choices=OrderStatus.choices(),
                               default=OrderStatus.NOT_SENT.value,
                               db_column='status')
    index = models.PositiveIntegerField()
    signal = models.ForeignKey(to=Signal,
                               related_name='buy_orders',
                               on_delete=models.DO_NOTHING)
    handled_worked = models.BooleanField(
        help_text="Did something if the order has worked",
        default=False)

    market: Market
    signal: Signal
    index: int

    objects = models.Manager()

    def __str__(self):
        return f"{self.pk}:{self.symbol}:{self.custom_order_id}"

    def save(self, *args, **kwargs):
        if not self.pk and not self.custom_order_id:
            self.custom_order_id = self.form_order_id(
                self.market.order_id_separator,
                self.signal.outer_signal_id,
                self.signal.techannel.abbr,
                self.index)
        super().save(*args, **kwargs)

    def push_to_market(self):
        logger.debug(f"Push buy order! {self}")
        self.market.push_buy_limit_order(self)

    def cancel_into_market(self):
        logger.debug(f"Cancel BUY order! {self}")
        self.market.cancel_order(self)

    def update_buy_order_info_by_api(self):
        statuses_ = [OrderStatus.SENT.value, ]
        if self.status not in statuses_:
            return
        logger.debug(f"Get info about BUY order by API: {self}")
        status, bought_quantity = self.market.get_order_info(self.symbol, self.custom_order_id)
        self.update_order_api_history(status, bought_quantity)

    def _set_updated_by_api_without_saving(self):
        self.last_updated_by_api = timezone.now()

    @transaction.atomic
    def update_order_api_history(self, status, executed_quantity):
        self._set_updated_by_api_without_saving()
        last_api_history = HistoryApiBuyOrder.objects.filter(main_order=self).last()
        if not last_api_history or (last_api_history.status != status or
                                    last_api_history.bought_quantity != executed_quantity):
            self.status = status
            self.bought_quantity = executed_quantity
            HistoryApiBuyOrder.objects.create(main_order=self,
                                              status=status,
                                              bought_quantity=executed_quantity)
        self.save()


class SellOrder(BaseOrder):
    SL_APPEND_INDEX = 500
    type_: str = 'sell'
    order_type_separator: str = 's'

    market = models.ForeignKey(to=Market,
                               related_name='sell_orders',
                               on_delete=models.DO_NOTHING)
    stop_loss = models.FloatField(default=0)
    sold_quantity = models.FloatField(default=0)
    _status = models.CharField(max_length=32,
                               choices=OrderStatus.choices(),
                               default=OrderStatus.NOT_SENT.value,
                               db_column='status')
    index = models.PositiveIntegerField()
    signal = models.ForeignKey(to=Signal,
                               related_name='sell_orders',
                               on_delete=models.DO_NOTHING)
    tp_order = models.OneToOneField(to='self',
                                    related_name='sl_order',
                                    null=True,
                                    blank=True,
                                    on_delete=models.DO_NOTHING)

    market: Market
    signal: Signal
    index: int
    tp_order: 'SellOrder.objects'
    sl_order: 'SellOrder.objects'
    stop_loss: float

    objects = models.Manager()

    def __str__(self):
        return f"{self.pk}:{self.symbol}:{self.custom_order_id}"

    def save(self, *args, **kwargs):
        if not self.pk and not self.custom_order_id:
            self.custom_order_id = self.form_order_id(
                self.market.order_id_separator,
                self.signal.techannel.abbr,
                self.signal.outer_signal_id,
                self.index)
        super().save(*args, **kwargs)

    @classmethod
    def _form_sell_stop_loss_order(cls, tp_order: 'SellOrder'):
        """Form Stop Loss order by Take Profit order"""
        calculated_real_stop_loss = tp_order.signal.get_real_stop_price(tp_order.stop_loss, tp_order.market)
        custom_sl_order_id = cls.form_sl_order_id(tp_order)
        order = SellOrder.objects.create(
            market=tp_order.market,
            symbol=tp_order.symbol,
            quantity=tp_order.quantity,
            price=calculated_real_stop_loss,
            stop_loss=0,
            tp_order=tp_order,
            no_need_push=True,
            signal=tp_order.signal,
            custom_order_id=custom_sl_order_id,
            index=tp_order.index + cls.SL_APPEND_INDEX)
        return order

    @classmethod
    def _form_tp_order(cls, market: 'BaseMarket', signal: Signal, quantity: float,
                       take_profit: float, stop_loss: float,
                       custom_order_id: str, index: int):
        """Form Take Profit order"""
        order = SellOrder.objects.create(
            market=market,
            symbol=signal.symbol,
            quantity=quantity,
            price=take_profit,
            stop_loss=stop_loss if stop_loss is not None else signal.stop_loss,
            signal=signal,
            custom_order_id=None if not custom_order_id else custom_order_id,
            index=index)
        return order

    @classmethod
    def form_sell_order(cls, market: 'BaseMarket', signal: Signal, quantity: float,
                        take_profit: float, stop_loss: float,
                        custom_order_id: str, index: int):
        tp_order = cls._form_tp_order(
            market=market, signal=signal, quantity=quantity, take_profit=take_profit,
            stop_loss=stop_loss, custom_order_id=custom_order_id, index=index)
        cls._form_sell_stop_loss_order(tp_order=tp_order)
        return tp_order

    def push_to_market(self):
        if self.no_need_push:
            return
        logger.debug(f"Push sell order! {self}")
        self.market.push_sell_stop_loss_limit_order(self)

    def cancel_into_market(self):
        logger.debug(f"Cancel SELL order! {self}")
        self.market.cancel_order(self)

    def update_sell_order_info_by_api(self):
        statuses_ = [OrderStatus.SENT.value, ]
        if self.status not in statuses_:
            return
        logger.debug(f"Get info about SELL order by API: {self}")
        status, sold_quantity = self.market.get_order_info(self.symbol, self.custom_order_id)
        self.update_order_api_history(status, sold_quantity)

    def _set_updated_by_api_without_saving(self):
        self.last_updated_by_api = timezone.now()

    @transaction.atomic
    def update_order_api_history(self, status, executed_quantity):
        self._set_updated_by_api_without_saving()
        last_api_history = HistoryApiSellOrder.objects.filter(main_order=self).last()
        if not last_api_history or (last_api_history.status != status or
                                    last_api_history.sold_quantity != executed_quantity):
            self.status = status
            self.sold_quantity = executed_quantity
            HistoryApiSellOrder.objects.create(main_order=self,
                                               status=status,
                                               sold_quantity=executed_quantity)
        self.save()


class HistoryApiBuyOrder(HistoryApiBaseOrder):
    status = models.CharField(max_length=32,
                              choices=OrderStatus.choices(),
                              default=OrderStatus.NOT_SENT.value)
    main_order = models.ForeignKey(to=BuyOrder,
                                   related_name='api_history',
                                   on_delete=models.CASCADE)
    bought_quantity = models.FloatField(default=0)

    objects = models.Manager()

    def __str__(self):
        return f"HABO_{self.pk}:Main_order:{self.main_order}"


class HistoryApiSellOrder(HistoryApiBaseOrder):
    status = models.CharField(max_length=32,
                              choices=OrderStatus.choices(),
                              default=OrderStatus.NOT_SENT.value)
    main_order = models.ForeignKey(to=SellOrder,
                                   related_name='api_history',
                                   on_delete=models.CASCADE)
    sold_quantity = models.FloatField(default=0)

    objects = models.Manager()

    def __str__(self):
        return f"HASO_{self.pk}:Main_order:{self.main_order}"


# class BuyOrderWorker(SystemBaseModel):
#     master_buy_order = models.ForeignKey(to=BuyOrder,
#                                          related_name='buy_worker',
#                                          on_delete=models.CASCADE)
#     slave_sell_orders = models.ManyToManyField(to=SellOrder,
#                                                related_name='buy_order_workers',
#                                                on_delete=models.CASCADE)
#
#
# class SellOrderWorker(SystemBaseModel):
#     master_sell_order = models.ForeignKey(to=SellOrder,
#                                           related_name='sell_worker',
#                                           on_delete=models.CASCADE)
#     slave_sell_orders = models.ManyToManyField(to=SellOrder,
#                                                related_name='sell_order_workers',
#                                                on_delete=models.CASCADE)
#
