import logging

from django.db import models
from typing import List

from utils.framework.models import SystemBaseModel
from apps.market.base_model import BaseMarket
from binfun.settings import conf_obj
from tools.tools import rounded_result, debug_input_and_returned

logger = logging.getLogger(__name__)


class Signal(SystemBaseModel):
    conf = conf_obj
    symbol = models.CharField(max_length=16)
    signal_id = models.PositiveIntegerField(unique=True)
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    _bought_quantity = models.FloatField(db_column='bought_quantity',
                                         help_text='Fullness of buy_orders',
                                         default=0)
    income = models.FloatField(help_text='Profit or Loss', default=0)

    def __str__(self):
        return f"Signal:{self.symbol}:{self.signal_id}"

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
        self._update_bought_quantity()
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
    def _get_distributed_toc_quantity(self, market: BaseMarket):
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=self.symbol, market=market.id).first()
        step_quantity = pair.step_quantity
        quantity = self.__get_turnover_by_coin_pair(market) / self.__get_buy_distribution()
        return self.__find_not_fractional_by_step_quantity(quantity, step_quantity)

    @debug_input_and_returned
    def __form_buy_order(self, market: BaseMarket, distributed_toc: float,
                         entry_point: 'EntryPoint', index: int):
        from apps.order.models import BuyOrder
        order, created = BuyOrder.objects.get_or_create(
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
        order, created = SellOrder.objects.get_or_create(
            market=market,
            symbol=self.symbol,
            quantity=distributed_quantity,
            price=take_profit.value,
            stop_loss=self.stop_loss,
            signal=self,
            index=index)
        return order

    def _formation_buy_orders(self, market: BaseMarket) -> None:
        """Функция расчёта данных для создания ордеров на покупку"""
        quantity = self._get_distributed_toc_quantity(market)
        for index, entry_point in enumerate(self.entry_points.all()):
            self.__form_buy_order(market, quantity, entry_point, index)

    def _formation_sell_orders(self, market: BaseMarket) -> None:
        """Функция расчёта данных для создания ордеров на продажу"""
        sell_quantity = self.bought_quantity
        distributed_quantity = sell_quantity / self.__get_sell_distribution()
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_sell_order(market, distributed_quantity, take_profit, index)

    @debug_input_and_returned
    def _update_bought_quantity(self):
        bought_quantity: float = 0
        for buy_order in self.buy_orders.all():
            buy_order.update_info_by_api()
            bought_quantity += buy_order.bought_quantity
        self._bought_quantity = bought_quantity

    def _create_buy_orders(self):
        for buy_order in self.buy_orders.all():
            buy_order.create_real()

    def _create_sell_orders(self):
        for sell_order in self.sell_orders.all():
            sell_order.create_real()

    def create_buy_orders(self, market: BaseMarket):
        # TODO добавить проверок
        # не были ли ещё созданы ордера
        self._formation_buy_orders(market)
        self._create_buy_orders()

    def create_sell_orders(self, market: BaseMarket):
        # TODO добавить проверок
        # не были ли ещё созданы ордера
        self._formation_sell_orders(market)
        self._create_sell_orders()


class EntryPoint(SystemBaseModel):
    signal = models.ForeignKey(to=Signal,
                               related_name='entry_points',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class TakeProfit(SystemBaseModel):
    signal = models.ForeignKey(to=Signal,
                               related_name='take_profits',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"
