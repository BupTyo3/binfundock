import logging

from typing import Optional, List, TYPE_CHECKING

from django.db import models, transaction
from django.db.models import QuerySet, Sum, F
from django.utils import timezone

from utils.framework.models import (
    get_increased_leading_number,
)
from .base_model import (
    BaseSignal, BaseHistorySignal,
    BaseEntryPoint, BaseTakeProfit,
    BaseSignalOrig, BasePointOrig,
)
from .utils import SignalStatus, SignalPosition, calculate_position
from apps.crontask.utils import get_or_create_crontask
from apps.market.base_model import BaseMarket
from apps.market.models import Market
from apps.market.utils import MarketType
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import (
    rou,
    rounded_result,
    debug_input_and_returned,
    subtract_fee,
)

if TYPE_CHECKING:
    from apps.order.models import SellOrder, BuyOrder

logger = logging.getLogger(__name__)


class SignalOrig(BaseSignalOrig):
    _default_leverage = 1
    conf = conf_obj

    techannel = models.ForeignKey(to=Techannel,
                                  related_name='signals_orig',
                                  on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField()
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    position = models.CharField(max_length=32,
                                choices=SignalPosition.choices(),
                                default=SignalPosition.LONG.value, )
    leverage = models.PositiveIntegerField(default=_default_leverage)
    message_date = models.DateTimeField(default=timezone.now, blank=True)

    techannel: Techannel
    entry_points: 'EntryPoint.objects'
    take_profits: 'TakeProfit.objects'

    objects = models.Manager()

    def __str__(self):
        return f"SignalOrig:{self.pk}:{self.symbol}:{self.techannel.abbr}:{self.outer_signal_id}"

    class Meta:
        unique_together = ['techannel', 'outer_signal_id', ]

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.main_coin = self._get_main_coin(self.symbol)
        super().save(*args, **kwargs)

    @classmethod
    @transaction.atomic
    def create_signal(cls, symbol: str, techannel_name: str,
                      stop_loss: float, outer_signal_id: int,
                      entry_points: List[float], take_profits: List[float],
                      leverage: Optional[int] = None,
                      message_date=timezone.now()):
        """
        Create signal
        """
        techannel, created = Techannel.objects.get_or_create(name=techannel_name)
        if created:
            logger.debug(f"Telegram channel '{techannel}' was created")
        sm_obj = Signal.objects.filter(outer_signal_id=outer_signal_id, techannel=techannel).first()
        if sm_obj:
            logger.warning(f"SignalOrig '{outer_signal_id}':'{techannel_name}' already exists")
            return
        position = calculate_position(stop_loss, entry_points, take_profits)
        sm_obj = cls.objects.create(
            techannel=techannel,
            symbol=symbol,
            stop_loss=stop_loss,
            outer_signal_id=outer_signal_id,
            position=position,
            leverage=leverage if leverage else cls._default_leverage,
            message_date=message_date)
        for entry_point in entry_points:
            EntryPointOrig.objects.create(signal=sm_obj, value=entry_point)
        for take_profit in take_profits:
            TakeProfitOrig.objects.create(signal=sm_obj, value=take_profit)
        logger.debug(f"SignalOrig '{sm_obj}' has been created successfully")
        return sm_obj

    @transaction.atomic
    def create_market_signal(self, market: Optional[BaseMarket] = None):
        signal = Signal.objects.create(
            techannel=self.techannel,
            symbol=self.symbol,
            stop_loss=self.stop_loss,
            outer_signal_id=self.outer_signal_id,
            position=self.position,
            leverage=self.leverage,
            message_date=self.message_date,
            market=market,
            signal_orig=self,
        )
        for entry_point in self.entry_points.all():
            EntryPoint.objects.create(signal=signal, value=entry_point.value)
        for take_profit in self.take_profits.all():
            TakeProfit.objects.create(signal=signal, value=take_profit.value)

    def _get_main_coin(self, symbol) -> str:
        """
        Example:
        symbol = LTCBTC
        if BTC in [conf.all_accessible_main_coins]:
        main_coin = BTC
        """
        for main_coin in self.conf.all_accessible_main_coins:
            if symbol[-len(main_coin):] == main_coin:
                return main_coin
        raise Exception("Provided main coin is not serviced")


class Signal(BaseSignal):
    _default_leverage = 1
    conf = conf_obj

    signal_orig = models.ForeignKey(to=SignalOrig,
                                    related_name='market_signals',
                                    on_delete=models.DO_NOTHING)
    market = models.ForeignKey(to=Market,
                               related_name='signals',
                               on_delete=models.DO_NOTHING)
    techannel = models.ForeignKey(to=Techannel,
                                  related_name='signals',
                                  on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField()
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    income = models.FloatField(help_text='Profit or Loss', default=0)
    amount = models.FloatField(help_text='Amount of Main Asset', default=0)
    _status = models.CharField(max_length=32,
                               choices=SignalStatus.choices(),
                               default=SignalStatus.NEW.value,
                               db_column='status')
    position = models.CharField(max_length=32,
                                choices=SignalPosition.choices(),
                                default=SignalPosition.LONG.value, )
    leverage = models.PositiveIntegerField(default=_default_leverage)
    message_date = models.DateTimeField(default=timezone.now, blank=True)
    all_targets = models.BooleanField(
        help_text="Flag is unset if the Signal was spoiled by admin",
        default=True)

    objects = models.Manager()

    entry_points: 'EntryPoint.objects'
    take_profits: 'TakeProfit.objects'
    buy_orders: 'BuyOrder.objects'
    sell_orders: 'SellOrder.objects'
    techannel: Techannel
    market: Market
    symbol: str

    def __str__(self):
        return f"Signal:{self.pk}:{self.symbol}:{self.techannel.abbr}:{self.outer_signal_id}"

    class Meta:
        unique_together = ['techannel', 'outer_signal_id', 'market']

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.main_coin = self._get_main_coin(self.symbol)
        super().save(*args, **kwargs)
        if self.pk is None:
            HistorySignal.write_in_history(self, self.status)

    @rounded_result
    def __get_calculated_amount(self):
        completed_buy_orders = self.__get_completed_buy_orders()
        bought_amount = self.__get_bought_amount(completed_buy_orders)
        return bought_amount

    @rounded_result
    def __get_calculated_income(self):
        completed_buy_orders = self.__get_completed_buy_orders()
        bought_amount = self.__get_bought_amount(completed_buy_orders)
        completed_sell_orders = self.__get_completed_sell_orders()
        sold_amount = self.__get_sold_amount(completed_sell_orders)
        sold_amount_subtracted_fee = subtract_fee(sold_amount, self._get_market_fee())
        res = sold_amount_subtracted_fee - bought_amount
        logger.debug(f"Income calculating for Signal '{self}': COMPLETED_BUY_ORDERS: {completed_buy_orders}; "
                     f"COMPLETED_SELL_ORDERS: {completed_sell_orders}; "
                     f"BOUGHT_amount={bought_amount}; SOLD_AMOUNT={sold_amount}; "
                     f"SOLD_AMOUNT_SUBTRACTED_FEE={sold_amount_subtracted_fee}; "
                     f"INCOME={rou(res)}")
        return res

    def _update_income(self):
        self.income = self.__get_calculated_income()
        self.save()

    def _update_amount(self):
        self.amount = self.__get_calculated_amount()
        self.save()

    def _get_main_coin(self, symbol) -> str:
        """
        Example:
        symbol = LTCBTC
        if BTC in [conf.accessible_main_coins]:
        main_coin = BTC
        """
        for main_coin in self.conf.accessible_main_coins:
            if symbol[-len(main_coin):] == main_coin:
                return main_coin
        raise Exception("Provided main coin is not serviced")

    def __get_buy_distribution(self):
        return self.entry_points.count()

    def __get_sell_distribution(self):
        return self.take_profits.count()

    def _get_current_balance_of_main_coin(self):
        return self.market_logic.get_current_balance(self.main_coin)

    def _get_current_price(self):
        return self.market_logic.get_current_price(self.symbol)

    def _get_market_fee(self):
        return self.market_logic.market_fee

    def _get_pair(self):
        from apps.pair.models import Pair
        return Pair.objects.filter(symbol=self.symbol, market=self.market.pk).first()

    @debug_input_and_returned
    @rounded_result
    def __get_turnover_by_coin_pair(self) -> float:
        """Turnover for one Signal.
        How much money we allocate for one Signal
        If free_balance 1000 usd, 10% - config parameter, so
         result will be 100 usd"""
        res = (self._get_current_balance_of_main_coin() *
               get_or_create_crontask().balance_to_signal_perc /
               self.conf.one_hundred_percent)
        return res
        # return res / n_distribution  # эквивалент 33 долларов

    @staticmethod
    @rounded_result
    def __find_not_fractional_by_step(value: float, step: float) -> float:
        """
        Round by Market rules
        Example:
        value = 0.123456
        pair.step_price = 0.001
        res = 0.123
        """
        return (value // step) * step

    @rounded_result
    def _get_distributed_toc_quantity(self, entry_point_price) -> float:
        """
        Calculate quantity for one coin
        Fraction by step
        """
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        quantity = self.__get_turnover_by_coin_pair() / self.__get_buy_distribution()
        coin_quantity = convert_to_coin_quantity(quantity, entry_point_price)
        return self.__find_not_fractional_by_step(coin_quantity, step_quantity)

    @rounded_result
    def _get_distributed_sell_quantity(self, all_quantity: float) -> float:
        """
        Get distributed sell quantity.
        Fraction by step
        """
        pair = self._get_pair()
        # TODO: Check, may be should change to step_quantity = pair.step_price
        step_quantity = pair.step_quantity
        quantity = all_quantity / self.__get_sell_distribution()
        return self.__find_not_fractional_by_step(quantity, step_quantity)

    @debug_input_and_returned
    @rounded_result
    def _get_residual_quantity(self) -> float:
        """
        Get residual quantity.
        return: (bought_quantity - sold_quantity)
        Fraction by step
        """
        completed_buy_orders = self.__get_completed_buy_orders()
        if not completed_buy_orders:
            return 0
        bought_quantity = self.__get_bought_quantity(completed_buy_orders)
        completed_sell_orders = self.__get_completed_sell_orders()
        sold_quantity = self.__get_sold_quantity(completed_sell_orders)
        residual_quantity = bought_quantity - sold_quantity if sold_quantity else bought_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        return self.__find_not_fractional_by_step(residual_quantity, step_quantity)

    @debug_input_and_returned
    def __form_buy_order(self, distributed_toc: float,
                         entry_point: 'EntryPoint', index: int):
        from apps.order.models import BuyOrder
        from apps.order.utils import OrderType
        order = BuyOrder.objects.create(
            market=self.market,
            symbol=self.symbol,
            quantity=distributed_toc,
            price=entry_point.value,
            signal=self,
            type=OrderType.LIMIT.value,
            index=index)
        return order

    @debug_input_and_returned
    def __form_oco_sell_order(self, distributed_quantity: float,
                              take_profit: float, index: int, stop_loss: Optional[float] = None,
                              custom_order_id: Optional[str] = None) -> 'SellOrder':
        """
        Form sell oco order for the signal
        """
        from apps.order.models import SellOrder
        msg = f"Form SELL ORDER for signal {self}"
        if stop_loss is not None:
            msg += f" with UPDATED STOP_LOSS: '{stop_loss}'"
        logger.debug(msg)
        order = SellOrder.form_sell_oco_order(
            market=self.market,
            signal=self,
            quantity=distributed_quantity,
            take_profit=take_profit,
            stop_loss=stop_loss,
            custom_order_id=custom_order_id,
            index=index
        )
        return order

    @debug_input_and_returned
    def __form_sell_market_order(self, quantity: float, price: float) -> 'SellOrder':
        """
        Form sell market order for the signal
        """
        from apps.order.models import SellOrder
        logger.debug(f"Form MARKET SELL ORDER for signal {self}")
        order = SellOrder.form_sell_market_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
        )
        return order

    @debug_input_and_returned
    @rounded_result
    def __get_amount_quantity(self) -> float:
        toc_quantity = self.__get_turnover_by_coin_pair()
        return toc_quantity / (self.__get_buy_distribution() * self.__get_sell_distribution())

    @debug_input_and_returned
    def _check_if_balance_enough_for_signal(self) -> bool:
        """
        Check if balance enough for Signal.
        Enough for create buy orders and then (after one buy order has worked) - sell orders
        """
        # TODO check
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair()
        # get amount and subtract fee for buy orders
        amount_quantity = subtract_fee(self.__get_amount_quantity(),
                                       self._get_market_fee() * self.__get_buy_distribution())
        logger.debug(f"'{self}':amount_quantity_subtracted_fee={amount_quantity}")
        if amount_quantity < pair.min_amount:
            logger.debug(f"Bad Check: amount_quantity < min_amount: {amount_quantity} < {pair.min_amount}!")
            return False
        entry_point_price = self.entry_points.last().value
        coin_quantity = convert_to_coin_quantity(amount_quantity, entry_point_price)
        logger.debug(f"'{self}':coin_quantity={coin_quantity}")
        if coin_quantity > pair.min_quantity:
            return True
        logger.debug(f"Bad Check: coin_quantity < min_quantity: {coin_quantity} < {pair.min_quantity}!")
        return False

    @debug_input_and_returned
    def _check_if_quantity_enough_for_sell(self, quantity: float, price: float) -> bool:
        """
        Check if quantity enough for Sell.
        """
        # TODO check
        from tools.tools import convert_to_amount
        pair = self._get_pair()
        amount_quantity = convert_to_amount(quantity, price)
        logger.debug(f"'{self}':amount_quantity={amount_quantity}")
        if amount_quantity < pair.min_amount:
            logger.debug(f"Bad Check: amount_quantity < min_amount: {amount_quantity} < {pair.min_amount}!")
            return False
        logger.debug(f"'{self}':coin_quantity={quantity}")
        if quantity > pair.min_quantity:
            return True
        logger.debug(f"Bad Check: coin_quantity < min_quantity: {quantity} < {pair.min_quantity}!")
        return False

    def _formation_first_sell_orders(self, sell_quantity: float) -> None:
        """
        Function for creating Sell orders
        """
        distributed_quantity = self._get_distributed_sell_quantity(sell_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_oco_sell_order(
                distributed_quantity=distributed_quantity,
                take_profit=take_profit.value, index=index)

    @rounded_result
    def _get_new_stop_loss(self, worked_sell_orders: QuerySet) -> float:
        """
        Business logic
        Fraction by step
        """
        last_worked_sell_order = worked_sell_orders.order_by('price').last()
        if last_worked_sell_order.index == 0:
            # if the first sell order has worked, new stop_loss is a max of entry_points
            res = self.entry_points.order_by('value').last().value
        else:
            # get price of previous order as a new stop_loss
            previous_order = self.sell_orders.filter(index=(last_worked_sell_order.index - 1)).last()
            res = previous_order.price
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_price)

    @debug_input_and_returned
    def _formation_copied_sell_order(self,
                                     original_order_id: int,
                                     sell_quantity: Optional[float] = None,
                                     new_stop_loss: Optional[float] = None):
        """
        Form one copied Sell order by original Sell order (with updated quantity or stop_loss)
        """
        from apps.order.models import SellOrder

        order = SellOrder.objects.filter(id=original_order_id).first()
        new_custom_order_id = get_increased_leading_number(order.custom_order_id)
        logger.debug(f"New copied SELL order custom_order_id = '{new_custom_order_id}'")
        new_sell_order = self.__form_oco_sell_order(
            distributed_quantity=sell_quantity if sell_quantity is not None else order.quantity,
            custom_order_id=new_custom_order_id,
            take_profit=order.price,
            index=order.index,
            stop_loss=order.stop_loss if new_stop_loss is None else new_stop_loss)
        return new_sell_order

    @debug_input_and_returned
    def _formation_copied_sell_orders(self,
                                      original_orders_ids: List[int],
                                      worked_sell_orders: QuerySet,
                                      sell_quantity: Optional[float] = None,
                                      new_stop_loss: Optional[float] = None) -> List['SellOrder']:
        """
        Form copied Sell orders with new stop_loss or new sell_quantity
        """
        if new_stop_loss is None and not sell_quantity:
            new_stop_loss = self._get_new_stop_loss(worked_sell_orders)
        res = list()
        original_orders_ids.sort()
        for order_id in original_orders_ids:
            res.append(self._formation_copied_sell_order(
                original_order_id=order_id, new_stop_loss=new_stop_loss, sell_quantity=sell_quantity))
        return res

    def __get_not_handled_worked_buy_orders(self) -> QuerySet:
        """
        Function to get not handled worked Buy orders
        """
        # TODO: maybe move to orders
        from apps.order.utils import OrderStatus
        from apps.order.models import BuyOrder
        params = {
            'signal': self,
            'handled_worked': False,
            'local_canceled': False,
            '_status': OrderStatus.COMPLETED.value
        }
        return BuyOrder.objects.filter(**params)

    def __get_not_handled_worked_sell_orders(self,
                                             sl_orders: bool = False,
                                             tp_orders: bool = False) -> QuerySet:
        """
        Function to get not handled worked Sell orders
        """
        # TODO: maybe move to orders
        from apps.order.utils import OrderStatus
        from apps.order.models import SellOrder
        params = {
            'signal': self,
            'handled_worked': False,
            'local_canceled': False,
            '_status': OrderStatus.COMPLETED.value
        }
        qs = SellOrder.objects.filter(**params)
        qs = qs.exclude(sl_order=None) if not sl_orders else qs
        qs = qs.exclude(tp_order=None) if not tp_orders else qs
        return qs

    @debug_input_and_returned
    def __get_sent_buy_orders(self, statuses: Optional[List] = None) -> QuerySet:
        """
        Function to get sent Buy orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [SENT, NOT_SENT]
        from apps.order.utils import OrderStatus
        from apps.order.models import BuyOrder
        statuses = [OrderStatus.SENT.value, ] if not statuses else statuses
        params = {
            'signal': self,
            'local_canceled': False,
            '_status__in': statuses
        }
        return BuyOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_sent_sell_orders(self, statuses: Optional[List] = None) -> QuerySet:
        """
        Function to get sent Sell orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [SENT, NOT_SENT]
        from apps.order.utils import OrderStatus
        from apps.order.models import SellOrder
        statuses = [OrderStatus.SENT.value, ] if not statuses else statuses
        params = {
            'signal': self,
            'local_canceled': False,
            'no_need_push': False,
            '_status__in': statuses
        }
        return SellOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_completed_sell_orders(self) -> QuerySet:
        """
        Function to get Completed Sell orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [COMPLETED, PARTIAL]
        from apps.order.utils import OrderStatus
        from apps.order.models import SellOrder
        params = {
            'signal': self,
            # TODO: check these cases
            '_status__in': [OrderStatus.COMPLETED.value, ]
        }
        return SellOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_completed_buy_orders(self) -> QuerySet:
        """
        Function to get Completed Buy orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [COMPLETED, PARTIAL]
        from apps.order.utils import OrderStatus
        from apps.order.models import BuyOrder
        params = {
            'signal': self,
            # TODO: check these cases
            # 'local_canceled': False,
            '_status__in': [OrderStatus.COMPLETED.value, ]
        }
        return BuyOrder.objects.filter(**params)

    @staticmethod
    def __update_flag_handled_worked_buy_orders(worked_orders: QuerySet):
        """
        Set flag handled_worked
        """
        # TODO: move it
        from apps.order.models import BuyOrder
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders_ids = list(worked_orders.all().values_list('id', flat=True))
        for order_id in worked_orders_ids:
            order = BuyOrder.objects.filter(id=order_id).first()
            order.handled_worked = True
            order.save()

    @staticmethod
    def __update_flag_handled_worked_sell_orders(worked_orders: QuerySet):
        """
        Set flag handled_worked
        """
        # TODO: move it
        from apps.order.models import SellOrder
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders_ids = list(worked_orders.all().values_list('id', flat=True))
        for order_id in worked_orders_ids:
            order = SellOrder.objects.filter(id=order_id).first()
            order.handled_worked = True
            order.save()

    @staticmethod
    @debug_input_and_returned
    def __cancel_sent_buy_orders(sent_orders: QuerySet):
        """
        Set flag local_cancelled for orders.
        The orders are ready to cancel
        """
        # TODO: move it
        from apps.order.models import BuyOrder
        logger.debug(f"Updating Sent orders by local_canceled flag")
        logger.debug(f"LOCAL CANCEL ORDERS: '{sent_orders}'")
        sent_orders_ids = list(sent_orders.all().values_list('id', flat=True))
        now_ = timezone.now()
        for order_id in sent_orders_ids:
            order = BuyOrder.objects.filter(id=order_id).first()
            order.local_canceled = True
            order.local_canceled_time = now_
            order.save()

    @staticmethod
    @debug_input_and_returned
    def __cancel_sent_sell_orders(sent_orders: QuerySet):
        """
        Set flag local_cancelled for orders.
        The orders are ready to cancel
        """
        # TODO: move it
        from apps.order.models import SellOrder
        logger.debug(f"Updating Sent orders by local_canceled flag")
        logger.debug(f"LOCAL CANCEL ORDERS: '{sent_orders}'")
        sent_orders_ids = list(sent_orders.all().values_list('id', flat=True))
        now_ = timezone.now()
        for order_id in sent_orders_ids:
            order = SellOrder.objects.filter(id=order_id).first()
            order.local_canceled = True
            order.local_canceled_time = now_
            order.save()

    @debug_input_and_returned
    @rounded_result
    def __get_bought_quantity(self, worked_orders: QuerySet) -> float:
        """
        Get Sum of bought_quantity of worked Buy orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('bought_quantity'))
        bought_quantity = res['bought_quantity__sum'] or 0
        res = subtract_fee(bought_quantity, self._get_market_fee())
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_quantity)

    @debug_input_and_returned
    @rounded_result
    def __get_bought_amount(self, worked_orders: QuerySet) -> float:
        """
        """
        # TODO: move it
        qs = worked_orders.annotate(amount=F('price') * F('quantity'))
        return qs.aggregate(Sum('amount'))['amount__sum'] or 0

    @staticmethod
    def __get_sold_amount(worked_orders: QuerySet) -> float:
        """
        """
        # TODO: move it
        qs = worked_orders.annotate(sold_amount=F('price') * F('sold_quantity'))
        return qs.aggregate(Sum('sold_amount'))['sold_amount__sum'] or 0

    @staticmethod
    def __get_sold_quantity(worked_orders: QuerySet) -> float:
        """
        Get Sum of quantity of orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('sold_quantity'))
        return res['sold_quantity__sum'] or 0

    @staticmethod
    def __get_planned_sold_quantity(worked_orders: QuerySet) -> float:
        """
        Get Sum of quantity of orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('quantity'))
        return res['quantity__sum']

    @debug_input_and_returned
    @rounded_result
    def __calculate_new_bought_quantity(self,
                                        sent_sell_orders: QuerySet,
                                        addition_quantity: float) -> float:
        """Calculate new bought_quantity by sent_sell_orders and addition_quantity
         (bought quantity of worked buy orders).
        Fraction by step
         """
        all_quantity = self.__get_planned_sold_quantity(sent_sell_orders) + addition_quantity
        res = all_quantity / sent_sell_orders.count()
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_quantity)

    @staticmethod
    def __exclude_sl_or_tp_orders(main_orders: QuerySet, worked_orders: QuerySet) -> QuerySet:
        """Exclude paired orders
        e.g.:
        main_orders = [order_1_tp, order_1_sl, order_2_tp]
        worked_orders = [order_2_sl]
        return: [order_1_tp, order_1_sl]
        """
        worked_sl_orders = worked_orders.exclude(sl_order=None).values('sl_order')
        worked_tp_orders = worked_orders.exclude(tp_order=None).values('tp_order')
        main_orders = main_orders.exclude(id__in=worked_sl_orders)
        main_orders = main_orders.exclude(id__in=worked_tp_orders)
        return main_orders

    @debug_input_and_returned
    # @transaction.atomic
    def _spoil(self, force: bool = False):
        from apps.order.utils import OrderStatus
        not_completed_buy_orders = self.__get_sent_buy_orders(
            statuses=[OrderStatus.NOT_SENT.value, OrderStatus.SENT.value])
        # Cancel all buy_orders
        if not_completed_buy_orders:
            self.__cancel_sent_buy_orders(not_completed_buy_orders)
        not_completed_sell_orders = self.__get_sent_sell_orders(
            statuses=[OrderStatus.NOT_SENT.value, OrderStatus.SENT.value])
        if not_completed_sell_orders:
            # Cancel opened sell_orders and form sell_market order
            self.__cancel_sent_sell_orders(not_completed_sell_orders)
        residual_quantity = self._get_residual_quantity()
        price = self._get_current_price()
        if residual_quantity and\
                self._check_if_quantity_enough_for_sell(quantity=residual_quantity, price=price):
            self.__form_sell_market_order(quantity=residual_quantity, price=price)
        else:
            logger.debug(f"No RESIDUAL QUANTITY for Signal '{self}'")
        if force:
            # Set flag because admin decided to spoil the signal
            self.all_targets = False
        self.status = SignalStatus.CANCELING.value
        self.save()

    @debug_input_and_returned
    def _check_is_ready_to_be_closed(self) -> bool:
        """
        Check Signal if it has no opened Buy orders and no opened Sell orders
        """
        from apps.order.utils import OrderStatus
        not_finished_orders_statuses = [
            OrderStatus.NOT_SENT.value,
            OrderStatus.SENT.value,
            OrderStatus.PARTIAL.value,
        ]
        not_finished_orders_params = {
            '_status__in': not_finished_orders_statuses,
        }
        if self.buy_orders.filter(**not_finished_orders_params).exists():
            return False
        logger.debug(f"1/2:Signal '{self}' has no Opened BUY orders")
        if self.sell_orders.filter(**not_finished_orders_params).exists():
            return False
        logger.debug(f"2/2:Signal '{self}' has no Opened SELL orders")
        return True

    @debug_input_and_returned
    def _close(self):
        """
        Function to close the Signal
        """
        logger.debug(f"Signal '{self}' will be closed")
        self.status = SignalStatus.CLOSED.value
        self.save()

    def _formation_futures_long_orders(self):
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(entry_point.value)
            # TODO: Form buy orders
            self.__form_buy_order(coin_quantity, entry_point, index)
        pass

    def _formation_futures_short_orders(self):
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(entry_point.value)
            # TODO: Form sell orders
            # self.__form_buy_order(coin_quantity, entry_point, index)
        pass

    def _formation_futures_orders(self):
        if not self._get_pair():
            logger.debug(f"Pair {self.symbol} does not exist in Futures")
            return
        if self.position == SignalPosition.LONG.value:
            logger.debug(f"Form Futures LONG: '{self}'")
            self._formation_futures_long_orders()
        elif self.position == SignalPosition.SHORT.value:
            logger.debug(f"Form Futures SHORT: '{self}'")
            self._formation_futures_short_orders()

    def _formation_spot_orders(self):
        if self.position != SignalPosition.LONG.value:
            logger.warning(f"Position is not LONG: '{self}'")
            return
        if not self._check_if_balance_enough_for_signal():
            # TODO: Add sent message to yourself telegram
            logger.debug(f"Not enough money for Signal '{self}'")
            return
        self.status = SignalStatus.FORMED.value
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(entry_point.value)
            self.__form_buy_order(coin_quantity, entry_point, index)
        self.save()

    @rounded_result
    def get_real_stop_price(self, price: float) -> float:
        """
        Calculate stop price with slip_delta_stop_loss_percentage parameter.
        Fraction by step
        """
        pair = self._get_pair()
        if get_or_create_crontask().slip_delta_sl_perc:
            real_stop_price = price - (
                    price * get_or_create_crontask().slip_delta_sl_perc /
                    self.conf.one_hundred_percent)
        else:
            real_stop_price = price
        return self.__find_not_fractional_by_step(real_stop_price, pair.step_price)

    # @transaction.atomic
    def formation_buy_orders(self) -> None:
        """
        Function for forming Buy orders for NEW signal
        """
        if self._status != SignalStatus.NEW.value:
            logger.warning(f"Not valid Signal status for formation BUY order: "
                           f"{self._status} : {SignalStatus.NEW.value}")
            return
        if self.market.logic.type == MarketType.FUTURES.value:
            return self._formation_futures_orders()
        else:
            return self._formation_spot_orders()

    @debug_input_and_returned
    # @transaction.atomic
    def try_to_spoil(self, force: bool = False):
        """
        Worker spoils the Signal if a current price reaches any of take_profits
        and there are no worked Buy orders
        """
        if force:
            self._spoil(force=True)
            return
        _statuses = [
            SignalStatus.FORMED.value,
            SignalStatus.PUSHED.value,
        ]
        if self._status not in _statuses:
            return
        current_price = self._get_current_price()
        min_profit_price = TakeProfit.get_min_value(self)
        msg = f"Check try_to_spoil '{self}':" \
              f" if: current_price >= min_profit_price: {current_price} >= {min_profit_price}?"
        if current_price >= min_profit_price:
            logger.debug(msg + ': Yes')
            self._spoil()
        else:
            logger.debug(msg + ': No')

    @debug_input_and_returned
    # @transaction.atomic
    def try_to_close(self) -> bool:
        """
        Worker closes the Signal if it has no opened Buy orders and no opened Sell orders
        """
        _statuses = [
            SignalStatus.FORMED.value,
            SignalStatus.PUSHED.value,
            SignalStatus.BOUGHT.value,
            SignalStatus.SOLD.value,
            SignalStatus.CANCELING.value,
        ]
        if self._status not in _statuses:
            return False
        if self._check_is_ready_to_be_closed():
            self._close()
            self._update_income()
            self._update_amount()

    @debug_input_and_returned
    def push_orders(self):
        """
        Function for interaction with the Real Market
        1)Cancel NOT_SENT local_cancelled Buy orders
        2)Sent request for local_cancelled SENT Buy orders
        3)Cancel NOT_SENT local_cancelled Sell orders
        4)Sent request for local_cancelled SENT Sell orders
        5)Sent request to create real Sell orders (NOT_SENT -> SENT)
        6)Sent request to create real Buy orders (NOT_SENT -> SENT)
        7)Change Signal status (NEW -> PUSHED) if this is the first launch

        """
        from apps.order.utils import OrderStatus
        cancelled_params = {
            'local_canceled': True,
        }
        no_need_push_params = {
            'no_need_push': False,
        }
        not_sent_params = {
            '_status__in': [OrderStatus.NOT_SENT.value, ]
        }
        sent_params = {
            '_status__in': [OrderStatus.SENT.value,
                            OrderStatus.PARTIAL.value]
        }
        # cancel NOT_SENT local_cancelled BUY orders
        for local_cancelled_order in self.buy_orders.filter(
                **cancelled_params).filter(**not_sent_params):
            local_cancelled_order.cancel_not_sent_order()
        # cancel SENT local_cancelled BUY orders
        for local_cancelled_order in self.buy_orders.filter(
                **cancelled_params).filter(**sent_params).filter(**no_need_push_params):
            local_cancelled_order.cancel_into_market()
        # cancel NOT_SENT local_cancelled SELL orders
        for local_cancelled_order in self.sell_orders.filter(
                **cancelled_params).filter(**not_sent_params):
            local_cancelled_order.cancel_not_sent_order()
        # cancel SENT local_cancelled SELL orders
        for local_cancelled_order in self.sell_orders.filter(
                **cancelled_params).filter(**sent_params).filter(**no_need_push_params):
            local_cancelled_order.cancel_into_market()
        orders_params_for_pushing = {
            '_status': OrderStatus.NOT_SENT.value,
            'local_canceled': False,
            'no_need_push': False,
        }
        # push NOT_SENT SELL orders
        for sell_order in self.sell_orders.filter(**orders_params_for_pushing):
            sell_order.push_to_market()
        # push NOT_SENT BUY orders
        for buy_order in self.buy_orders.filter(**orders_params_for_pushing):
            buy_order.push_to_market()
            # set status if at least one order has created
            if self.status not in [SignalStatus.PUSHED.value, SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]:
                self.status = SignalStatus.PUSHED.value
                self.save()

    @debug_input_and_returned
    # @transaction.atomic
    def worker_for_bought_orders(self):
        """
        Worker for one signal.
        Run if at least one Buy order has worked.
        1)Create Sell orders if no one exists
        2)Recreate Sent Sell orders with updated quantity
        """
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        if self._status not in _statuses:
            return
        worked_orders = self.__get_not_handled_worked_buy_orders()
        if not worked_orders:
            return
        bought_quantity = self.__get_bought_quantity(worked_orders)
        logger.debug(f"Calculate quantity for Sell order: Bought_quantity = {bought_quantity}")
        # TODO: Add logic recreating existing sell orders with updated quantity
        # Recreating opened sent sell orders with new quantity
        sent_sell_orders = self.__get_sent_sell_orders()
        if sent_sell_orders:
            new_bought_quantity = self.__calculate_new_bought_quantity(sent_sell_orders, bought_quantity)
            copied_sent_sell_orders_ids = list(sent_sell_orders.all().values_list('id', flat=True))
            self.__cancel_sent_sell_orders(sent_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_orders,
                                               sell_quantity=new_bought_quantity)
        # Form sell orders if the signal doesn't have any
        elif not self.sell_orders.exists():
            self._formation_first_sell_orders(sell_quantity=bought_quantity)
        self.__update_flag_handled_worked_buy_orders(worked_orders)
        # Change status
        if self.status not in [SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]:
            self.status = SignalStatus.BOUGHT.value
            self.save()

    @debug_input_and_returned
    # @transaction.atomic
    def worker_for_sold_orders(self):
        """
        Worker for one signal.
        Run if at least one Sell order has worked.
        1)Cancel BUY orders
        2)Recreating opened (sent) SELL orders with updated stop_loss
        3)Calculate profit (stop_loss or take_profit)
        """
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        _statuses = [SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        if self._status not in _statuses:
            return
        worked_tp_orders = self.__get_not_handled_worked_sell_orders(tp_orders=True)
        if not worked_tp_orders:
            return
        opened_buy_orders = self.__get_sent_buy_orders()
        # Cancel all buy_orders
        if opened_buy_orders:
            self.__cancel_sent_buy_orders(opened_buy_orders)
        # Recreating opened sent sell orders with new stop_loss
        sent_sell_orders = self.__get_sent_sell_orders()
        sent_sell_orders = self.__exclude_sl_or_tp_orders(sent_sell_orders, worked_tp_orders)
        if sent_sell_orders:
            copied_sent_sell_orders_ids = list(sent_sell_orders.all().values_list('id', flat=True))
            self.__cancel_sent_sell_orders(sent_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_tp_orders)
        # Change status
        if self.status not in [SignalStatus.SOLD.value, ]:
            self.status = SignalStatus.SOLD.value
            self.save()
        self.__update_flag_handled_worked_sell_orders(worked_tp_orders)
        # TODO: Add logic of calculate profit or loss
        pass

    @classmethod
    def handle_new_signals(cls,
                           outer_signal_id: Optional[int] = None,
                           techannel_abbr: Optional[str] = None):
        """Handle all NEW signals: Step 2"""
        params = {'_status': SignalStatus.NEW.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        new_signals = Signal.objects.filter(**params)
        for signal in new_signals:
            signal.formation_buy_orders()

    @classmethod
    def push_signals(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all FORMED signals: Step 3"""
        _statuses = [SignalStatus.FORMED.value,
                     SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.CANCELING.value,
                     SignalStatus.SOLD.value, ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        ready_for_push_signals = Signal.objects.filter(**params)
        for signal in ready_for_push_signals:
            signal.push_orders()

    @classmethod
    def update_signals_info_by_api(cls,
                                   outer_signal_id: Optional[int] = None,
                                   techannel_abbr: Optional[str] = None):
        """
        Get info for one Signal from Real Market by SENT orders
        """
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.CANCELING.value,
                     SignalStatus.SOLD.value, ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.update_info_by_api()

    def update_info_by_api(self):
        """
        Get info for all Signals (except NEW) from Real Market by SENT orders
        """
        from apps.order.utils import OrderStatus
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.CANCELING.value,
                     SignalStatus.SOLD.value, ]
        if self._status not in _statuses:
            return

        _order_statuses = [OrderStatus.SENT.value, ]
        params = {
            '_status__in': _order_statuses,
        }
        for buy_order in self.buy_orders.filter(**params):
            buy_order.update_buy_order_info_by_api()
        for sell_order in self.sell_orders.filter(**params):
            sell_order.update_sell_order_info_by_api()

    @classmethod
    def bought_orders_worker(cls,
                             outer_signal_id: Optional[int] = None,
                             techannel_abbr: Optional[str] = None):
        """Handle all PUSHED signals. Buy orders worker"""
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.worker_for_bought_orders()

    @classmethod
    def sold_orders_worker(cls,
                           outer_signal_id: Optional[int] = None,
                           techannel_abbr: Optional[str] = None):
        """Handle all BOUGHT signals. Sell orders worker"""
        _statuses = [SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.worker_for_sold_orders()

    @classmethod
    def spoil_worker(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all signals. Try_to_spoil worker"""
        _statuses = [
            SignalStatus.FORMED.value,
            SignalStatus.PUSHED.value,
        ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.try_to_spoil()

    @classmethod
    def close_worker(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all signals. Try_to_close worker"""
        _statuses = [
            SignalStatus.FORMED.value,
            SignalStatus.PUSHED.value,
            SignalStatus.BOUGHT.value,
            SignalStatus.SOLD.value,
            SignalStatus.CANCELING.value,
        ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        signals = Signal.objects.filter(**params)
        for signal in signals:
            signal.try_to_close()


class EntryPointOrig(BasePointOrig):
    signal = models.ForeignKey(to=SignalOrig,
                               related_name='entry_points',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'SignalOrig.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class EntryPoint(BaseEntryPoint):
    signal = models.ForeignKey(to=Signal,
                               related_name='entry_points',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'Signal.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class TakeProfitOrig(BasePointOrig):
    signal = models.ForeignKey(to=SignalOrig,
                               related_name='take_profits',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'SignalOrig.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class TakeProfit(BaseTakeProfit):
    signal = models.ForeignKey(to=Signal,
                               related_name='take_profits',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'Signal.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class HistorySignal(BaseHistorySignal):
    status = models.CharField(max_length=32,
                              choices=SignalStatus.choices(),
                              default=SignalStatus.NEW.value)
    main_signal = models.ForeignKey(to=Signal,
                                    related_name='signal_history',
                                    on_delete=models.CASCADE)
    current_price = models.FloatField(null=True)

    objects = models.Manager()

    def __str__(self):
        return f"HS_{self.pk}:Main_signal:{self.main_signal}"

    @classmethod
    def write_in_history(cls,
                         signal: Signal,
                         status: str):
        current_price = None
        try:
            current_price = signal.market_logic.get_current_price(signal.symbol)
        except Exception as ex:
            logger.warning(f"Current price for HistorySignal failed to get. Signal '{signal}'"
                           f": Exception:'{ex}'")
        cls.objects.create(main_signal=signal, status=status, current_price=current_price)
        logger.debug(f"Add HistorySignal Record for Signal '{signal}' status = '{status}'")
