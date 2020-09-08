import logging

from django.db import models
from django.contrib.auth import get_user_model

from utils.framework.models import SystemBaseModel
from typing import Tuple, Optional

from binance import client
from apps.order.utils import OrderStatus
from .base_model import Market
from apps.pair.models import Pair
from tools.tools import (
    floated_result,
    api_logging,
    debug_input_and_returned,
    catch_exception,
)


User = get_user_model()
logger = logging.getLogger(__name__)


# class Market(SystemBaseModel):
#     """
#     Model of Market entity
#     """
#
#     breed = models.CharField(max_length=100)
#     nickname = models.CharField(max_length=100)
#     owner = models.ForeignKey(
#         to=User,
#         related_name='owner_of_pets',
#         on_delete=models.CASCADE)
#
#     def __str__(self):
#         return f"{self.nickname}: {self.breed}: {self.owner}"


class TestMarket(Market):
    order_id_separator = 'tm'
    pair_class: Pair = Pair

    def __init__(self):
        super().__init__()
        self.fake_update_pairs_info()

    def get_current_price(self, symbol):
        # return 70.0
        return 120.0
        # return 190.0

    def get_current_balance(self, coin: str):
        return 1000.0

    def get_order_info(self, symbol, order_id):
        quantity_executed = 7
        is_completed = True
        return quantity_executed, is_completed

    def create_buy_limit_order(self, order):
        logger.debug(f"We are creating the Test order: {order.__dict__}")

    def fake_update_pairs_info(self):
        fake_data = (
            ('ZECETH', 0.001, 0.00001, 0.001, 0.001, 0.001, 0.01),
            ('LTCUSDT', 0.01, 0.01, 0.001, 0.00001, 0.00001, 10.0),
        )
        for pair in fake_data:
            self.pairs[pair[0]] = self.pair_class(
                symbol=pair[0],
                min_price=pair[1],
                step_price=pair[2],
                step_quantity=pair[3],
                min_quantity=pair[4],
                min_amount=pair[5])


class BiMarket(Market):
    symbol_ = 'symbol'
    bidPrice_ = 'bidPrice'
    askPrice_ = 'askPrice'
    id_ = 'id'
    limit_history = 500
    balances_ = 'balances'
    asset_ = 'asset'
    locked_ = 'locked'
    baseAsset_ = 'baseAsset'
    quoteAsset_ = 'quoteAsset'
    filters_ = 'filters'
    minQty_ = 'minQty'
    minAmount_ = 'minNotional'
    stepSize_ = 'stepSize'
    minPrice_ = 'minPrice'
    stepPrice_ = 'tickSize'
    time_ = 'time'
    status_ = 'status'
    type_ = 'type'
    side_ = 'side'
    price_ = 'price'
    origQty_ = 'origQty'
    orderId_ = 'orderId'
    new_ = 'NEW'
    filled_ = 'FILLED'
    symbols_ = 'symbols'

    executed_quantity_: str = 'executedQty'
    free_: str = 'free'

    order_id_separator = 'bim'
    client_class: client.Client = client.Client
    pair_class: Pair = Pair
    ORDER_STATUSES_MATCH: dict = {
        client_class.ORDER_STATUS_CANCELED:
            Market.order_statuses.CANCELED,
        client_class.ORDER_STATUS_FILLED:
            Market.order_statuses.COMPLETED,
        client_class.ORDER_STATUS_NEW:
            Market.order_statuses.SENT,
        Market.order_statuses.NOT_EXISTS:
            Market.order_statuses.NOT_EXISTS,
    }

    def __init__(self, api_key: str, api_secret: str):
        super().__init__()
        self.my_client: client.Client = self.client_class(api_key, api_secret)
        self.update_pairs_info_api()

    @floated_result
    def get_current_price(self, symbol):
        response = self.my_client.get_avg_price(symbol=symbol)
        return response[self.price_]

    @api_logging
    def _get_balance_api(self, coin):
        return self.my_client.get_asset_balance(coin)

    @floated_result
    def get_current_balance(self, coin) -> float:
        return self._get_balance_api(coin)[self.free_]

    @floated_result
    def _get_executed_quantity(self, response) -> float:
        return response[self.executed_quantity_]

    @catch_exception(
        code=-2013, alternative={'status': OrderStatus.NOT_EXISTS, executed_quantity_: 0.0})
    @api_logging(text="Getting info by OrderId")
    def _get_order_info_api(self, symbol, order_id):
        return self.my_client.get_order(symbol=symbol, origClientOrderId=order_id)

    @debug_input_and_returned
    def get_order_info(self, symbol, order_id) -> Tuple[OrderStatus, float]:
        response = self._get_order_info_api(symbol, order_id)
        order_status, updated = self._convert_to_our_order_status(response[self.status_])
        return order_status, self._get_executed_quantity(response)

    def _convert_to_our_order_status(self, market_order_status: str) -> Tuple[OrderStatus, bool]:
        if market_order_status in self.ORDER_STATUSES_MATCH:
            return self.ORDER_STATUSES_MATCH[market_order_status], True
        logger.debug(f"Status {market_order_status} not in ORDER_STATUSES_MATCH")
        return self.order_statuses.UNKNOWN, False

    @api_logging
    def _create_buy_limit_order(self, symbol, quantity, price, order_id):
        res = self.my_client.order_limit_buy(
            symbol=symbol, quantity=quantity, price=price, newClientOrderId=order_id)
        return res

    def create_buy_limit_order(self, order):
        logger.debug(f"ОГРАНИЧЕНИЯ по {order.symbol}: {self.pairs[order.symbol].__dict__}")
        res = self._create_buy_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, order_id=order.order_id)
        return res

    @api_logging
    def _get_rules_api(self):
        return self.my_client.get_exchange_info()

    @floated_result
    def __get_pair_rule(self, data: dict, first: str, order: int, second: str):
        return data[first][order][second]

    def update_pairs_info_api(self):
        info = self._get_rules_api()[self.symbols_]
        for i in info:
            symbol = i[self.symbol_]
            min_price = self.__get_pair_rule(i, self.filters_, 0, self.minPrice_)
            step_price = self.__get_pair_rule(i, self.filters_, 0, self.stepPrice_)
            min_quantity = self.__get_pair_rule(i, self.filters_, 2, self.minQty_)
            min_amount = self.__get_pair_rule(i, self.filters_, 3, self.minAmount_)
            step_size = self.__get_pair_rule(i, self.filters_, 2, self.stepSize_)
            pair = self.pair_class(symbol, min_price, step_price, step_size, min_quantity, min_amount)
            self.pairs[pair.symbol] = pair