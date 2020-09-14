import logging

from typing import Optional

from django.db import models, transaction
from django.db.models import QuerySet, Sum

from utils.framework.models import SystemBaseModel
from .base_model import BaseSignal
from .utils import SignalStatus
from apps.market.base_model import BaseMarket
from binfun.settings import conf_obj
from tools.tools import rounded_result, debug_input_and_returned

logger = logging.getLogger(__name__)


class Signal(BaseSignal):
    conf = conf_obj
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField(unique=True)
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

    def save(self, *args, **kwargs):
        self.main_coin = self._get_first_coin(self.symbol)
        super().save(*args, **kwargs)
        logger.debug(self)

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
        """Оборот на одну пару.
        Сколько выделяем денег на ставку на пару
        Если баланс 1000 долларов, 10% - конфигурационный параметр на одну пару, то будет
         эквивалент 100 долларов"""
        res = (market.get_current_balance(self.main_coin) *
               self.conf.how_percent_for_one_signal /
               self.conf.one_hundred_percent)
        return res
        # return res / n_distribution  # эквивалент 33 долларов

    @staticmethod
    def __find_not_fractional_by_step_quantity(quantity, step_quantity):
        return (quantity // step_quantity) * step_quantity

    @rounded_result
    def _get_distributed_toc_quantity(self, market: BaseMarket, entry_point_price):
        from tools.tools import convert_to_coin_quantity
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=self.symbol, market=market.id).first()
        step_quantity = pair.step_quantity
        quantity = self.__get_turnover_by_coin_pair(market) / self.__get_buy_distribution()
        coin_quantity = convert_to_coin_quantity(quantity, entry_point_price)
        return self.__find_not_fractional_by_step_quantity(coin_quantity, step_quantity)

    @rounded_result
    def _get_distributed_sell_quantity(self, market: BaseMarket, all_quantity: float):
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=self.symbol, market=market.id).first()
        step_quantity = pair.step_price
        quantity = all_quantity / self.__get_sell_distribution()
        return self.__find_not_fractional_by_step_quantity(quantity, step_quantity)

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
                          take_profit: 'TakeProfit', index: int):
        from apps.order.models import SellOrder
        order = SellOrder.objects.create(
            market=market,
            symbol=self.symbol,
            quantity=distributed_quantity,
            price=take_profit.value,
            stop_loss=self.stop_loss,
            signal=self,
            index=index)
        return order

    @transaction.atomic
    def formation_buy_orders(self, market: BaseMarket) -> None:
        """Функция расчёта данных для создания ордеров на покупку"""
        if self._status != SignalStatus.NEW.value:
            raise Exception(f'Not valid status: {self._status} : {SignalStatus.NEW.value}')
        self.status = SignalStatus.FORMED.value
        self.save()
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(market, entry_point.value)
            self.__form_buy_order(market, coin_quantity, entry_point, index)

    def _formation_sell_orders(self, market: BaseMarket, sell_quantity: Optional[float] = None) -> None:
        """Функция расчёта данных для создания ордеров на продажу"""
        distributed_quantity = self._get_distributed_sell_quantity(market, sell_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_sell_order(market, distributed_quantity, take_profit, index)

    @debug_input_and_returned
    def _update_bought_quantity(self):
        bought_quantity: float = 0
        for buy_order in self.buy_orders.all():
            # TODO change the logic
            # buy_order.update_info_by_api()
            bought_quantity += buy_order.bought_quantity
        self._bought_quantity = bought_quantity

    def push_buy_orders(self):
        from apps.order.utils import OrderStatus
        _statuses = [SignalStatus.FORMED.value, ]
        if self._status not in _statuses:
            raise Exception(f'Not valid status: {self._status} : {SignalStatus.FORMED.value}')
        for buy_order in self.buy_orders.filter(_status=OrderStatus.NOT_SENT.value):
            buy_order.push_to_market()
            # set status if at least one order has created
            if self.status != SignalStatus.PUSHED.value:
                self.status = SignalStatus.PUSHED.value
                self.save()

    def push_sell_orders(self):
        from apps.order.utils import OrderStatus
        for sell_order in self.sell_orders.filter(_status=OrderStatus.NOT_SENT.value):
            sell_order.push_to_market()
            # set status if at least one order has created
            if self.status != SignalStatus.BOUGHT.value:
                self.status = SignalStatus.BOUGHT.value
                self.save()

    def __get_not_handled_worked_buy_orders(self) -> QuerySet:
        # TODO: maybe move to orders
        from apps.order.utils import OrderStatus
        from apps.order.models import BuyOrder
        params = {
            'signal': self,
            'handled_worked': False,
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
            '_status': OrderStatus.COMPLETED.value
        }
        return SellOrder.objects.filter(**params)

    @staticmethod
    def __update_flag_handled_worked_orders(worked_orders: QuerySet):
        # TODO: move it
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders.update(handled_worked=True)

    @staticmethod
    def __get_bought_quantity(worked_orders: QuerySet):
        # TODO: move it
        res = worked_orders.aggregate(Sum('bought_quantity'))
        return res['bought_quantity__sum']

    def worker_for_bought_orders(self):
        """Worker для одного сигнала. Запускать когда сработал BUY order"""
        # TODO: Maybe add select_for_update - чтоб другой процесс не установил флаги
        #  или ещё флаг добавить, что в обработке ордера или ничего, если один процесс
        # TODO: Check
        # TODO: Maybe add BOUGHT status
        _statuses = [SignalStatus.PUSHED.value, ]
        if self._status not in _statuses:
            raise Exception(f'Not valid status: {self._status} : {_statuses}')
        worked_orders = self.__get_not_handled_worked_buy_orders()
        if worked_orders:
            bought_quantity = self.__get_bought_quantity(worked_orders)
            logger.debug(f"Calculate quantity for Sell order: Bought_quantity = {bought_quantity}")
            self._formation_sell_orders(worked_orders.last().market, bought_quantity)
            self.__update_flag_handled_worked_orders(worked_orders)

    def worker_for_sold_orders(self):
        """Worker для одного сигнала. Запускать когда сработал SELL order"""
        # TODO: Maybe add select_for_update - чтоб другой процесс не установил флаги
        #  или ещё флаг добавить, что в обработке ордера или ничего, если один процесс
        # TODO: Check
        worked_orders = self.__get_not_handled_worked_sell_orders()
        # TODO: Add logic
        pass

    @classmethod
    def handle_new_signals(cls, market: BaseMarket, outer_signal_id=None):
        """Handle all NEW signals: Step 2"""
        params = {'_status': SignalStatus.NEW.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        new_signals = Signal.objects.filter(**params)
        # TODO add logic
        for signal in new_signals:
            signal.formation_buy_orders(market)

    @classmethod
    def handle_formed_signals(cls, outer_signal_id=None):
        """Handle all FORMED signals: Step 3"""
        params = {'_status': SignalStatus.FORMED.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.push_buy_orders()
        # TODO: Maybe add the same for sell orders?

    @classmethod
    def update_signal_info_by_api(cls, outer_signal_id=None):
        # TODO: Возможно убрать BOUGHT сигналы
        _statuses = [SignalStatus.PUSHED.value, SignalStatus.BOUGHT.value]
        params = {'_status__in': _statuses}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        formed_signals = Signal.objects.filter(**params)
        # TODO
        for signal in formed_signals:
            signal.update_info_by_api()

    def update_info_by_api(self):
        _statuses = [SignalStatus.PUSHED.value, SignalStatus.BOUGHT.value]
        if self._status not in _statuses:
            raise Exception(f'Not valid status: {self._status} : {_statuses}')
        for buy_order in self.buy_orders.all():
            buy_order.update_buy_order_info_by_api()
        # TODO Maybe Add the same for sell_orders?

    @classmethod
    def handle_pushed_signals(cls, outer_signal_id=None):
    # def gain_profit(self):
        """Асинхронная функция для менеджера задач.
        Разветвления:
        1)Проверяет сработал ли Osell(с профитом):
            - отменить все Obuy
            - увеличить self.income (профит)
            - пересоздание Osell (с новыми StopLoss)
        2)Проверяет сработал ли Obuy:
            - пересоздание Osell (с новыми quantity)
        3)Проверяет сработал ли Osell (по StopLoss)
            - уменьшить self.income (Loss)
        """
        params = {'_status': SignalStatus.PUSHED.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        pushed_signals = Signal.objects.filter(**params)

        for signal in pushed_signals:
            if signal.check_if_order_sell_has_worked():
                # TODO add logic
                pass
            if signal.check_if_order_buy_has_worked():
                # TODO add logic
                pass

    def check_if_order_sell_has_worked(self):
        """
        получить данные из БД = self.sell_orders
        получить данные по API по custom_id каждого из sell ордеров
        """
        pass

    def check_if_order_buy_has_worked(self):
        pass

    @classmethod
    def bought_orders_worker(cls, outer_signal_id=None):
        """Handle all PUSHED signals. Buy orders worker"""
        # TODO: Возможно добавить BOUGHT сигналы
        params = {'_status': SignalStatus.PUSHED.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        formed_signals = Signal.objects.filter(**params)
        # TODO
        for signal in formed_signals:
            signal.worker_for_bought_orders()

    @classmethod
    def sold_orders_worker(cls, outer_signal_id=None):
        """Handle all BOUGHT signals. Buy orders worker"""
        # TODO: Возможно добавить BOUGHT сигналы
        params = {'_status': SignalStatus.BOUGHT.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id})
        formed_signals = Signal.objects.filter(**params)
        # TODO
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

