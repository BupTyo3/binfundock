import logging

from typing import Optional, List, TYPE_CHECKING

from django.db import models, transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from utils.framework.models import (
    SystemBaseModel,
    generate_increment_name_after_suffix,
)
from .base_model import BaseSignal
from .utils import SignalStatus
from apps.market.base_model import BaseMarket
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import rounded_result, debug_input_and_returned

if TYPE_CHECKING:
    from apps.order.models import SellOrder, BuyOrder

logger = logging.getLogger(__name__)


class Signal(BaseSignal):
    conf = conf_obj
    techannel = models.ForeignKey(to=Techannel,
                                  related_name='signals',
                                  on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField()
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    _bought_quantity = models.FloatField(db_column='bought_quantity',
                                         help_text='Fullness of buy_orders',
                                         default=0)
    income = models.FloatField(help_text='Profit or Loss', default=0)
    _status = models.CharField(max_length=32,
                               choices=SignalStatus.choices(),
                               default=SignalStatus.NEW.value,
                               db_column='status')

    objects = models.Manager()

    entry_points: 'EntryPoint.objects'
    take_profits: 'TakeProfit.objects'
    buy_orders: 'BuyOrder.objects'
    sell_orders: 'SellOrder.objects'

    def __str__(self):
        return f"Signal:{self.symbol}:{self.outer_signal_id}"

    class Meta:
        unique_together = ['techannel', 'outer_signal_id', ]

    def save(self, *args, **kwargs):
        self.main_coin = self._get_first_coin(self.symbol)
        super().save(*args, **kwargs)
        logger.debug(self)

    @classmethod
    @transaction.atomic
    def create_signal(cls, symbol: str, techannel_abbr: str,
                      stop_loss: float, outer_signal_id: int,
                      entry_points: List[float], take_profits: List[float]):
        techannel, created = Techannel.objects.get_or_create(abbr=techannel_abbr)
        if created:
            logger.debug(f"Telegram channel '{techannel}' was created")
        sm_obj = Signal.objects.filter(outer_signal_id=outer_signal_id, techannel=techannel).first()
        if sm_obj:
            logger.warning(f"Signal '{outer_signal_id}':'{techannel_abbr}' already exists")
            return
        sm_obj = Signal.objects.create(
            techannel=techannel, symbol=symbol,
            stop_loss=stop_loss, outer_signal_id=outer_signal_id)
        for entry_point in entry_points:
            EntryPoint.objects.create(signal=sm_obj, value=entry_point)
        for take_profit in take_profits:
            TakeProfit.objects.create(signal=sm_obj, value=take_profit)
        logger.debug(f"Signal '{sm_obj}' has been created successfully")
        return sm_obj

    def _get_first_coin(self, symbol) -> str:
        for main_coin in self.conf.accessible_main_coins:
            if symbol[-len(main_coin):] == main_coin:
                return main_coin
        raise Exception("Provided main coin is not serviced")

    @property
    def bought_quantity(self):
        # self._update_bought_quantity()
        return self._bought_quantity

    @bought_quantity.setter
    def bought_quantity(self, value: float):
        self._bought_quantity = value

    def __get_buy_distribution(self):
        return self.entry_points.count()

    def __get_sell_distribution(self):
        return self.take_profits.count()

    @rounded_result
    def __get_turnover_by_coin_pair(self, market: BaseMarket) -> float:
        """Turnover for one Signal.
        How much money we allocate for one Signal
        If free_balance 1000 usd, 10% - config parameter, so
         result will be 100 usd"""
        res = (market.get_current_balance(self.main_coin) *
               self.conf.how_percent_for_one_signal /
               self.conf.one_hundred_percent)
        return res
        # return res / n_distribution  # эквивалент 33 долларов

    @staticmethod
    def __find_not_fractional_by_step(quantity: float, step: float) -> float:
        return (quantity // step) * step

    def _get_pair(self, market: BaseMarket):
        from apps.pair.models import Pair
        return Pair.objects.filter(symbol=self.symbol, market=market.pk).first()

    @rounded_result
    def _get_distributed_toc_quantity(self, market: BaseMarket, entry_point_price):
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair(market)
        step_quantity = pair.step_quantity
        quantity = self.__get_turnover_by_coin_pair(market) / self.__get_buy_distribution()
        coin_quantity = convert_to_coin_quantity(quantity, entry_point_price)
        return self.__find_not_fractional_by_step(coin_quantity, step_quantity)

    def get_real_stop_price(self, price: float, market: BaseMarket):
        pair = self._get_pair(market)
        if self.conf.slip_delta_stop_loss_percentage:
            real_stop_price = price - (
                    price * self.conf.slip_delta_stop_loss_percentage /
                    self.conf.one_hundred_percent)
        else:
            real_stop_price = price
        return self.__find_not_fractional_by_step(real_stop_price, pair.step_price)

    @rounded_result
    def _get_distributed_sell_quantity(self, market: BaseMarket, all_quantity: float):
        pair = self._get_pair(market)
        # TODO: Check, may be should change to step_quantity = pair.step_price
        step_quantity = pair.step_quantity
        quantity = all_quantity / self.__get_sell_distribution()
        return self.__find_not_fractional_by_step(quantity, step_quantity)

    @debug_input_and_returned
    def __form_buy_order(self, market: BaseMarket, distributed_toc: float,
                         entry_point: 'EntryPoint', index: int):
        from apps.order.models import BuyOrder
        order = BuyOrder.objects.create(
            market=market,
            symbol=self.symbol,
            quantity=distributed_toc,
            price=entry_point.value,
            signal=self,
            index=index)
        return order

    @debug_input_and_returned
    def __form_sell_order(self, market: BaseMarket, distributed_quantity: float,
                          take_profit: float, index: int, stop_loss: Optional[float] = None,
                          custom_order_id: Optional[str] = None) -> 'SellOrder':
        from apps.order.models import SellOrder
        msg = f"Form SELL ORDER for signal {self}"
        if stop_loss is not None:
            msg += f" with UPDATED STOP_LOSS: '{stop_loss}'"
        logger.debug(msg)
        if stop_loss is not None:
            logger.debug(f"Form SELL ORDER for signal {self}")
        order = SellOrder.form_sell_order(
            market=market,
            signal=self,
            quantity=distributed_quantity,
            take_profit=take_profit,
            stop_loss=stop_loss,
            custom_order_id=None if not custom_order_id else custom_order_id,
            index=index
        )
        return order

    def _check_if_balance_enough_for_signal(self, market: BaseMarket):
        # TODO check
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair(market)
        amount_quantity = self.__get_turnover_by_coin_pair(market) / (
            self.__get_buy_distribution() + self.__get_sell_distribution())
        if amount_quantity < pair.min_amount:
            logger.debug(f"Bad Check: amount_quantity < min_amount: {amount_quantity} < {pair.min_amount}!")
            return False
        entry_point_price = self.entry_points.last().value
        coin_quantity = convert_to_coin_quantity(amount_quantity, entry_point_price)
        if coin_quantity > pair.min_quantity:
            return True
        logger.debug(f"Bad Check: coin_quantity < min_quantity: {coin_quantity} < {pair.min_quantity}!")
        return False

    @transaction.atomic
    def formation_buy_orders(self, market: BaseMarket) -> None:
        """Function for forming Buy orders for NEW signal"""
        if self._status != SignalStatus.NEW.value:
            logger.warning(f'Not valid Signal status for formation BUY order: '
                           f'{self._status} : {SignalStatus.NEW.value}')
            return
        if not self._check_if_balance_enough_for_signal(market):
            # TODO: Add sent message to yourself telegram
            logger.debug(f"Not enough money for Signal '{self}'")
            return
        self.status = SignalStatus.FORMED.value
        self.save()
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(market, entry_point.value)
            self.__form_buy_order(market, coin_quantity, entry_point, index)

    def _formation_sell_orders(self, market: BaseMarket, sell_quantity: float) -> None:
        """Function for creating Sell orders"""
        distributed_quantity = self._get_distributed_sell_quantity(market, sell_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_sell_order(
                market=market, distributed_quantity=distributed_quantity,
                take_profit=take_profit.value, index=index)

    def _get_new_stop_loss(self, worked_sell_orders: QuerySet) -> float:
        last_worked_sell_order = worked_sell_orders.order_by('price').last()
        if last_worked_sell_order.index == 0:
            # if the first sell order has worked, new stop_loss is a max of entry_points
            return self.entry_points.order_by('value').last().value
        else:
            # get price of previous order as a new stop_loss
            previous_order = self.sell_orders.filter(index=(last_worked_sell_order.index - 1)).last()
            return previous_order.price

    @debug_input_and_returned
    def _formation_copied_sell_order(self,
                                     original_order_id: int,
                                     sell_quantity: Optional[float] = None,
                                     new_stop_loss: Optional[float] = None):
        max_number_of_copies = 300  # Max number of copies of Sell orders
        copy_delimiter = '_copy_'
        max_length_of_signal_id = 50  # length of custom_order_id field of BaseOrder model
        from apps.order.models import SellOrder

        def check_if_that_name_already_exists_function(custom_order_id):
            if SellOrder.objects.filter(custom_order_id=custom_order_id).exists():
                return True
        order = SellOrder.objects.filter(id=original_order_id).first()
        new_custom_order_id = generate_increment_name_after_suffix(
            order.custom_order_id,
            check_if_that_name_already_exists_function,
            copy_delimiter,
            max_number_of_copies,
            max_length_of_signal_id
        )
        logger.debug(f"New copied SELL order custom_order_id = '{new_custom_order_id}'")
        new_sell_order = self.__form_sell_order(
            market=order.market,
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
        """Form copied sell orders with new stop_loss or new sell_quantity"""
        if new_stop_loss is None and not sell_quantity:
            new_stop_loss = self._get_new_stop_loss(worked_sell_orders)
        res = list()
        for order_id in original_orders_ids:
            res.append(self._formation_copied_sell_order(
                original_order_id=order_id, new_stop_loss=new_stop_loss, sell_quantity=sell_quantity))
        return res

    @debug_input_and_returned
    def _update_bought_quantity(self):
        bought_quantity: float = 0
        for buy_order in self.buy_orders.all():
            # TODO change the logic
            # buy_order.update_info_by_api()
            bought_quantity += buy_order.bought_quantity
        self._bought_quantity = bought_quantity

    def push_orders(self):
        from apps.order.utils import OrderStatus
        statuses_not_for_cancel = [OrderStatus.CANCELED.value,
                                   OrderStatus.NOT_EXISTS.value,
                                   OrderStatus.NOT_SENT.value, ]
        # cancel local_cancelled buy orders
        for local_cancelled_order in self.buy_orders.filter(
                local_canceled=True).exclude(_status__in=statuses_not_for_cancel):
            local_cancelled_order.cancel_into_market()
        # cancel local_cancelled sell orders
        for local_cancelled_order in self.sell_orders.filter(
                local_canceled=True).exclude(_status__in=statuses_not_for_cancel):
            local_cancelled_order.cancel_into_market()
        # push not_sent SELL orders
        for sell_order in self.sell_orders.filter(_status=OrderStatus.NOT_SENT.value):
            sell_order.push_to_market()
        # push not_sent BUY orders
        for buy_order in self.buy_orders.filter(_status=OrderStatus.NOT_SENT.value):
            buy_order.push_to_market()
            # set status if at least one order has created
            if self.status not in [SignalStatus.PUSHED.value, SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]:
                self.status = SignalStatus.PUSHED.value
                self.save()

    def __get_not_handled_worked_buy_orders(self) -> QuerySet:
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

    def __get_not_handled_worked_sell_orders(self) -> QuerySet:
        # TODO: maybe move to orders
        from apps.order.utils import OrderStatus
        from apps.order.models import SellOrder
        params = {
            'signal': self,
            'handled_worked': False,
            'local_canceled': False,
            '_status': OrderStatus.COMPLETED.value
        }
        return SellOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_sent_buy_orders(self) -> QuerySet:
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [SENT, NOT_SENT]
        from apps.order.utils import OrderStatus
        from apps.order.models import BuyOrder
        params = {
            'signal': self,
            'local_canceled': False,
            '_status__in': [OrderStatus.SENT.value, ]
        }
        return BuyOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_sent_sell_orders(self) -> QuerySet:
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [SENT, NOT_SENT]
        from apps.order.utils import OrderStatus
        from apps.order.models import SellOrder
        params = {
            'signal': self,
            'local_canceled': False,
            '_status__in': [OrderStatus.SENT.value, ]
        }
        return SellOrder.objects.filter(**params)

    @staticmethod
    def __update_flag_handled_worked_orders(worked_orders: QuerySet):
        # TODO: move it
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders.update(handled_worked=True)

    @staticmethod
    @debug_input_and_returned
    def __cancel_sent_orders(sent_orders: QuerySet):
        # TODO: move it
        logger.debug(f"Updating Sent orders by local_canceled flag")
        logger.debug(f"LOCAL CANCEL ORDERS: '{sent_orders.all()}'")
        now_ = timezone.now()
        sent_orders.update(local_canceled=True, local_canceled_time=now_)

    @staticmethod
    def __get_bought_quantity(worked_orders: QuerySet) -> float:
        # TODO: move it
        res = worked_orders.aggregate(Sum('bought_quantity'))
        return res['bought_quantity__sum']

    @staticmethod
    def __get_planned_sold_quantity(worked_orders: QuerySet) -> float:
        # TODO: move it
        res = worked_orders.aggregate(Sum('quantity'))
        return res['quantity__sum']

    @rounded_result
    def __calculate_new_bought_quantity(self,
                                        sent_sell_orders: QuerySet,
                                        addition_quantity: float) -> float:
        """Calculate new bought_quantity by sent_sell_orders and addition_quantity
         (bought quantity of worked buy orders)"""
        all_quantity = self.__get_planned_sold_quantity(sent_sell_orders) + addition_quantity
        return all_quantity / sent_sell_orders.count()

    @transaction.atomic
    @debug_input_and_returned
    def worker_for_bought_orders(self):
        """Worker for one signal. Run if at least one Buy order was worked"""
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        # TODO: Maybe add BOUGHT status
        _statuses = [SignalStatus.PUSHED.value, SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]
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
            self.__cancel_sent_orders(sent_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_orders,
                                               sell_quantity=new_bought_quantity)
        # Form sell orders if the signal doesn't have any
        elif not self.sell_orders.exists():
            self._formation_sell_orders(worked_orders.last().market, bought_quantity)
        self.__update_flag_handled_worked_orders(worked_orders)
        # Change status
        if self.status not in [SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]:
            self.status = SignalStatus.BOUGHT.value
            self.save()

    @transaction.atomic
    @debug_input_and_returned
    def worker_for_sold_orders(self):
        """Worker for one signal. Run if at least one Buy order was worked"""
        """Worker for one signal. Запускать когда сработал SELL order
        1)Cancel BUY orders
        2)Recreating opened (sent) SELL orders with updated stop_loss
        3)Calculate profit (stop_loss or take_profit)"""
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        _statuses = [SignalStatus.BOUGHT.value, SignalStatus.SOLD.value, ]
        if self._status not in _statuses:
            return
        worked_orders = self.__get_not_handled_worked_sell_orders()
        if not worked_orders:
            return
        opened_buy_orders = self.__get_sent_buy_orders()
        # Cancel all buy_orders
        if opened_buy_orders:
            self.__cancel_sent_orders(opened_buy_orders)
        # Recreating opened sent sell orders with new stop_loss
        sent_sell_orders = self.__get_sent_sell_orders()
        if sent_sell_orders:
            copied_sent_sell_orders_ids = list(sent_sell_orders.all().values_list('id', flat=True))
            self.__cancel_sent_orders(sent_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_orders)
        # Change status
        if self.status not in [SignalStatus.SOLD.value, ]:
            self.status = SignalStatus.SOLD.value
            self.save()
        self.__update_flag_handled_worked_orders(worked_orders)
        # TODO: Add logic of calculate profit or loss
        pass

    @classmethod
    def handle_new_signals(cls, market: BaseMarket,
                           outer_signal_id: Optional[int] = None,
                           techannel_abbr: Optional[str] = None):
        """Handle all NEW signals: Step 2"""
        params = {'_status': SignalStatus.NEW.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        new_signals = Signal.objects.filter(**params)
        for signal in new_signals:
            signal.formation_buy_orders(market)

    @classmethod
    def push_signals(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all FORMED signals: Step 3"""
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
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
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.update_info_by_api()

    def update_info_by_api(self):
        from apps.order.utils import OrderStatus
        _statuses = [SignalStatus.PUSHED.value,
                     SignalStatus.BOUGHT.value,
                     SignalStatus.SOLD.value, ]
        if self._status not in _statuses:
            return

        _order_statuses = [OrderStatus.SENT.value, ]
        params = {'_status__in': _order_statuses}
        for buy_order in self.buy_orders.filter(**params):
            buy_order.update_buy_order_info_by_api()
        for sell_order in self.sell_orders.filter(**params):
            sell_order.update_sell_order_info_by_api()

    @classmethod
    def bought_orders_worker(cls,
                             outer_signal_id: Optional[int] = None,
                             techannel_abbr: Optional[str] = None):
        """Handle all PUSHED signals. Buy orders worker"""
        # TODO: Maybe add BOUGHT Signals
        params = {'_status': SignalStatus.PUSHED.value}
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
        # TODO: Maybe add BOUGHT Signals
        params = {'_status': SignalStatus.BOUGHT.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.worker_for_sold_orders()


class EntryPoint(SystemBaseModel):
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


class TakeProfit(SystemBaseModel):
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

