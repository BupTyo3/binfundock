import logging

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from typing import List

from apps.order.models import SellOrder, BuyOrder, BuyData, SellData
from apps.market.base_model import Market
from binfun.settings import conf_obj
from tools.tools import rounded_result, debug_input_and_returned

logger = logging.getLogger(__name__)


class SignalModel:
    conf = conf_obj

    def __init__(self,
                 pair: str,
                 entry_points: List[float],
                 take_profits: List[float],
                 stop_loss: float,
                 signal_id: int):
        self.pair = pair
        self.entry_points = entry_points
        self.take_profits = take_profits
        self.stop_loss = stop_loss
        self.signal_id = signal_id
        self.buy_orders: BuyData = []
        self.sell_orders: SellData = []
        self._bought_quantity: float = 0
        self.main_coin = self._get_first_coin(pair)
        logger.debug(self)

    def __str__(self):
        return f"Signal:{self.pair}:{self.entry_points}:{self.take_profits}:{self.stop_loss}:{self.signal_id}"

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
        return len(self.entry_points)

    def __get_sell_distribution(self):
        return len(self.take_profits)

    @rounded_result
    def __get_turnover_by_coin_pair(self, market: Market) -> float:
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
    def _get_distributed_toc_quantity(self, market: Market):
        step_quantity = market.pairs[self.pair].step_quantity
        quantity = self.__get_turnover_by_coin_pair(market) / self.__get_buy_distribution()
        return self.__find_not_fractional_by_step_quantity(quantity, step_quantity)

    @debug_input_and_returned
    def __form_buy_order(self, market, distributed_toc, entry_point, index):
        return BuyOrder(market=market,
                        symbol=self.pair,
                        quantity=distributed_toc,
                        price=entry_point,
                        signal_id=self.signal_id,
                        index=index)

    @debug_input_and_returned
    def __form_sell_order(self, market, distributed_quantity, take_profit, index):
        return SellOrder(market=market,
                         symbol=self.pair,
                         quantity=distributed_quantity,
                         price=take_profit,
                         stop_loss=self.stop_loss,
                         signal_id=self.signal_id,
                         index=index)

    def _formation_buy_orders(self, market: Market) -> None:
        """Функция расчёта данных для создания ордеров на покупку"""
        quantity = self._get_distributed_toc_quantity(market)
        for index, entry_point in enumerate(self.entry_points):
            # todo добавить проверку нет ли такого ордера в self.buy_orders -> continue
            self.buy_orders.append(self.__form_buy_order(market, quantity, entry_point, index))

    def _formation_sell_orders(self, market: Market) -> None:
        """Функция расчёта данных для создания ордеров на продажу"""
        sell_quantity = self.bought_quantity
        distributed_quantity = sell_quantity / self.__get_sell_distribution()
        for index, take_profit in enumerate(self.take_profits):
            # todo добавить проверку нет ли такого ордера в self.sell_orders -> continue
            self.sell_orders.append(self.__form_sell_order(market, distributed_quantity, take_profit, index))

    @debug_input_and_returned
    def _update_bought_quantity(self):
        bought_quantity: float = 0
        for buy_order in self.buy_orders:
            buy_order.update_info_by_api()
            bought_quantity += buy_order.bought_quantity
        self._bought_quantity = bought_quantity

    def _create_buy_orders(self):
        for buy_order in self.buy_orders:
            buy_order.create_real()

    def _create_sell_orders(self):
        for sell_order in self.sell_orders:
            sell_order.create_real()

    def create_buy_orders(self, market: Market):
        # TODO добавить проверок
        # не были ли ещё созданы ордера
        self._formation_buy_orders(market)
        self._create_buy_orders()

    def create_sell_orders(self, market: Market):
        # TODO добавить проверок
        # не были ли ещё созданы ордера
        self._formation_sell_orders(market)
        self._create_sell_orders()


