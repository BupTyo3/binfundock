import logging

from typing import Optional, TYPE_CHECKING

from django.db import models, transaction
from django.contrib.auth import get_user_model

from apps.order.utils import OrderStatus, OrderType
from apps.market.models import Market
from apps.signal.models import Signal
from .base_model import (
    BaseBuyOrder,
    BaseSellOrder,
    HistoryApiBaseOrder,
)

if TYPE_CHECKING:
    from apps.market.base_model import BaseMarket

User = get_user_model()
logger = logging.getLogger(__name__)


class BuyOrder(BaseBuyOrder):
    market = models.ForeignKey(to=Market,
                               related_name='buy_orders',
                               on_delete=models.DO_NOTHING)
    bought_quantity = models.FloatField(default=0)
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

    def push_to_market(self):
        """
        Push order to the Market by api
        """
        logger.debug(f"Push buy order! {self}")
        self.push_count_increase()
        self.market_logic.push_buy_limit_order(self)

    def cancel_into_market(self):
        """
        Cancel order into the Market
        """
        logger.debug(f"Cancel BUY order! {self}")
        data = self.market_logic.cancel_order(self)
        # status, bought_quantity = data.get('status'), data.get('executed_quantity', 0)
        # self.update_order_api_history(status, bought_quantity)

    def update_buy_order_info_by_api(self):
        """
        Only for SENT BUY orders.
        Get info from Market api and update OrderHistory table if we got new data
        """
        statuses_ = [OrderStatus.SENT.value, ]
        if self.status not in statuses_:
            return
        logger.debug(f"Get info about BUY order by API: {self}")
        data = self.market_logic.get_order_info(self.symbol, self.custom_order_id)
        status, bought_quantity = data.get('status'), data.get('executed_quantity')
        self.update_order_api_history(status, bought_quantity)

    # @transaction.atomic
    def update_order_api_history(self, status, executed_quantity, price=None):
        """
        Create HistoryApiBuyOrder entity if not exists or we got new data (status or executed_quantity).
        Set Order status (for the first time - SENT)
        """
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


class SellOrder(BaseSellOrder):
    _SL_APPEND_INDEX = 500
    _MARKET_INDEX = 300

    market = models.ForeignKey(to=Market,
                               related_name='sell_orders',
                               on_delete=models.DO_NOTHING)
    stop_loss = models.FloatField(default=0)
    sold_quantity = models.FloatField(default=0)
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

    @classmethod
    def _form_sell_stop_loss_order(cls, tp_order: 'SellOrder'):
        """Form Stop Loss order by Take Profit order"""
        calculated_real_stop_loss = tp_order.signal.get_real_stop_price(tp_order.stop_loss)
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
            type=OrderType.STOP_LOSS_LIMIT.value,
            index=tp_order.index + cls._SL_APPEND_INDEX)
        return order

    @classmethod
    def _form_tp_order(cls, market: 'BaseMarket', signal: Signal, quantity: float,
                       take_profit: float, stop_loss: float,
                       custom_order_id: Optional[str], index: int):
        """Form Take Profit order"""
        order = SellOrder.objects.create(
            market=market,
            symbol=signal.symbol,
            quantity=quantity,
            price=take_profit,
            stop_loss=stop_loss if stop_loss is not None else signal.stop_loss,
            signal=signal,
            custom_order_id=custom_order_id,
            type=OrderType.LIMIT_MAKER.value,
            index=index)
        return order

    @classmethod
    def _form_sell_market_order(cls, market: 'BaseMarket',
                                signal: Signal,
                                quantity: float,
                                price: float,
                                custom_order_id: Optional[str]):
        """Form Take Profit order"""
        order = SellOrder.objects.create(
            market=market,
            symbol=signal.symbol,
            quantity=quantity,
            price=price,
            signal=signal,
            custom_order_id=custom_order_id,
            type=OrderType.MARKET.value,
            index=cls._MARKET_INDEX)
        return order

    @classmethod
    def form_sell_oco_order(cls, market: 'BaseMarket', signal: Signal, quantity: float,
                            take_profit: float, stop_loss: float,
                            custom_order_id: Optional[str], index: int):
        """Form OCO SELL order:
        One - tp_order (Take Profit order),
        Second - sl_order (Stop Loss order)"""
        tp_order = cls._form_tp_order(
            market=market, signal=signal, quantity=quantity, take_profit=take_profit,
            stop_loss=stop_loss, custom_order_id=custom_order_id, index=index)
        cls._form_sell_stop_loss_order(tp_order=tp_order)
        return tp_order

    @classmethod
    def form_sell_market_order(cls, market: 'BaseMarket',
                               signal: Signal,
                               quantity: float,
                               price: float,
                               custom_order_id: Optional[str] = None):
        """Form Market SELL order:
        """
        order = cls._form_sell_market_order(
            market=market, signal=signal, quantity=quantity, price=price,
            custom_order_id=custom_order_id)
        return order

    def push_to_market(self):
        """
        Push order to the Market by api
        """
        if self.no_need_push:
            return
        logger.debug(f"Push sell order! {self}")
        self.push_count_increase()
        if self.type == OrderType.LIMIT_MAKER.value:
            self.market_logic.push_sell_oco_order(self)
        elif self.type == OrderType.MARKET.value:
            self.market_logic.push_sell_market_order(self)

    def cancel_into_market(self):
        """
        Cancel order into the Market
        """
        logger.debug(f"Cancel SELL order! {self}")
        data = self.market_logic.cancel_order(self)
        # status, sold_quantity = data.get('status'), data.get('executed_quantity', 0)
        # self.update_order_api_history(status, sold_quantity)

    def update_sell_order_info_by_api(self):
        """
        Only for SENT SELL orders.
        Get info from Market api and update OrderHistory table if we got new data
        """
        statuses_ = [OrderStatus.SENT.value, ]
        if self.status not in statuses_:
            return
        logger.debug(f"Get info about SELL order by API: {self}")
        data = self.market_logic.get_order_info(self.symbol, self.custom_order_id)
        status, sold_quantity, price = data.get('status'), data.get('executed_quantity'), data.get('price')
        self.update_order_api_history(status, sold_quantity, price)

    # @transaction.atomic
    def update_order_api_history(self, status: str, executed_quantity: float, price: Optional[float] = None):
        """
        Create HistoryApiSellOrder entity if not exists or we got new data (status or executed_quantity).
        Set Order status (for the first time - SENT)
        """
        self._set_updated_by_api_without_saving()
        last_api_history = HistoryApiSellOrder.objects.filter(main_order=self).last()
        if not last_api_history or (last_api_history.status != status or
                                    last_api_history.sold_quantity != executed_quantity):
            # Update order
            self.status = status
            self.sold_quantity = executed_quantity
            if self.type == OrderType.MARKET.value and price:
                logger.debug(f"Update price for Market order '{self}' = {self.price} -> {price}")
                self.price = price
            # Create history record
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
