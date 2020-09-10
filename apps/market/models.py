import logging

from django.db import models
from django.contrib.auth import get_user_model

from typing import Tuple

from binance import client
from apps.order.utils import OrderStatus
from .base_model import BaseMarket
from tools.tools import (
    floated_result,
    api_logging,
    debug_input_and_returned,
    catch_exception,
)
from binfun.settings import conf_obj


User = get_user_model()
logger = logging.getLogger(__name__)


class Market(BaseMarket):
    default_name = 'Binance'
    name = models.CharField(max_length=32,
                            unique=True,
                            default=default_name)
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

    ORDER_STATUSES_MATCH: dict = {
        client_class.ORDER_STATUS_CANCELED:
            BaseMarket.order_statuses.CANCELED,
        client_class.ORDER_STATUS_FILLED:
            BaseMarket.order_statuses.COMPLETED,
        client_class.ORDER_STATUS_NEW:
            BaseMarket.order_statuses.SENT,
        BaseMarket.order_statuses.NOT_EXISTS:
            BaseMarket.order_statuses.NOT_EXISTS,
    }

    my_client: client.Client = client_class(
        conf_obj.market_api_key, conf_obj.market_api_secret)

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
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
    def _get_order_info_api(self, symbol, custom_order_id):
        return self.my_client.get_order(symbol=symbol, origClientOrderId=custom_order_id)

    @debug_input_and_returned
    def get_order_info(self, symbol, custom_order_id) -> Tuple[OrderStatus, float]:
        response = self._get_order_info_api(symbol, custom_order_id)
        order_status, updated = self._convert_to_our_order_status(response[self.status_])
        return order_status, self._get_executed_quantity(response)

    def _convert_to_our_order_status(self, market_order_status: str) -> Tuple[OrderStatus, bool]:
        if market_order_status in self.ORDER_STATUSES_MATCH:
            return self.ORDER_STATUSES_MATCH[market_order_status], True
        logger.debug(f"Status {market_order_status} not in ORDER_STATUSES_MATCH")
        return self.order_statuses.UNKNOWN, False

    @api_logging
    def _create_buy_limit_order(self, symbol, quantity, price, custom_order_id):
        res = self.my_client.order_limit_buy(
            symbol=symbol, quantity=quantity, price=price, newClientOrderId=custom_order_id)
        return res

    def create_buy_limit_order(self, order):
        from apps.pair.models import Pair

        # logger.debug(f"ОГРАНИЧЕНИЯ по {order.symbol}: {self.pairs[order.symbol].__dict__}")
        pair = Pair.objects.filter(symbol=order.symbol, market=self).first()
        logger.debug(f"ОГРАНИЧЕНИЯ по {order.symbol}: {pair.__dict__}")
        res = self._create_buy_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, custom_order_id=order.custom_order_id)
        return res

    # @api_logging
    def _get_rules_api(self):
        return self.my_client.get_exchange_info()

    @floated_result
    def __get_pair_rule(self, data: dict, first: str, order: int, second: str):
        return data[first][order][second]

    def update_pairs_info_api(self):
        from apps.pair.models import Pair

        info = self._get_rules_api()[self.symbols_]
        for i in info:
            symbol = i[self.symbol_]
            min_price = self.__get_pair_rule(i, self.filters_, 0, self.minPrice_)
            step_price = self.__get_pair_rule(i, self.filters_, 0, self.stepPrice_)
            min_quantity = self.__get_pair_rule(i, self.filters_, 2, self.minQty_)
            min_amount = self.__get_pair_rule(i, self.filters_, 3, self.minAmount_)
            step_size = self.__get_pair_rule(i, self.filters_, 2, self.stepSize_)
            # pair = self.pair_class(symbol, min_price, step_price, step_size, min_quantity, min_amount)
            if not Pair.objects.filter(symbol=symbol):
                logger.debug(f"Add a new pair rule {symbol}")
                pair = Pair.objects.create(symbol=symbol,
                                           min_price=min_price,
                                           step_price=step_price,
                                           step_quantity=step_size,
                                           min_quantity=min_quantity,
                                           min_amount=min_amount,
                                           market=self)
