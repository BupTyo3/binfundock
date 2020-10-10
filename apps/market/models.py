import logging

from django.db import models
from django.contrib.auth import get_user_model

from typing import Tuple, TypedDict, TYPE_CHECKING

from binance import client
from apps.order.utils import OrderStatus
from .base_model import BaseMarket
from .base_client import BaseClient
from tools.tools import (
    floated_result,
    api_logging,
    debug_input_and_returned,
    catch_exception,
    price_to_str,
)
from binfun.settings import conf_obj

if TYPE_CHECKING:
    from apps.order.base_model import BaseOrder
    from apps.order.models import SellOrder, BuyOrder

User = get_user_model()
logger = logging.getLogger(__name__)


class PartialResponse(TypedDict):
    status: str
    status_updated: bool
    price: float
    executed_quantity: float
    avg_sold_market_price: float


class BiClient(client.Client, BaseClient):
    api_client_class = client.Client
    api_key = conf_obj.market_api_key
    api_secret = conf_obj.market_api_secret


class Market(BaseMarket):
    default_name = 'Binance'
    market_fee = conf_obj.market_fee
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
    stopPrice_ = 'stopPrice'
    time_ = 'time'
    status_ = 'status'
    type_ = 'type'
    side_ = 'side'
    fills_ = 'fills'
    price_ = 'price'
    origQty_ = 'origQty'
    orderId_ = 'orderId'
    new_ = 'NEW'
    filled_ = 'FILLED'
    symbols_ = 'symbols'

    executed_quantity_: str = 'executedQty'
    free_: str = 'free'

    order_id_separator = 'bim'
    client_class = BiClient

    ORDER_STATUSES_MATCH: dict = {
        client_class.ORDER_STATUS_CANCELED:
            BaseMarket.order_statuses.CANCELED.value,
        client_class.ORDER_STATUS_FILLED:
            BaseMarket.order_statuses.COMPLETED.value,
        client_class.ORDER_STATUS_PARTIALLY_FILLED:
            BaseMarket.order_statuses.PARTIAL.value,
        client_class.ORDER_STATUS_NEW:
            BaseMarket.order_statuses.SENT.value,
        client_class.ORDER_STATUS_EXPIRED:
            BaseMarket.order_statuses.EXPIRED.value,
        BaseMarket.order_statuses.NOT_EXISTS.value:
            BaseMarket.order_statuses.NOT_EXISTS.value,
    }

    objects = models.Manager()

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        """Addition: Fill DB by Pairs rules data from the Market api"""
        super().save(*args, **kwargs)
        self.update_pairs_info_api()

    @api_logging
    def _get_balance_api(self, coin):
        """Send request to get balance by asset (coin)"""
        return self.my_client.get_asset_balance(coin)

    @floated_result
    def _get_executed_quantity(self, response) -> float:
        """Get partially data by key executed_quantity"""
        return response[self.executed_quantity_]

    @floated_result
    def _get_price(self, response) -> float:
        """Get partially data by key price"""
        return response.get(self.price_)

    @floated_result
    def _get_avg_sold_price(self, response) -> float:
        """Get partially data by key price"""
        fills = response.get(self.fills_)
        res = 0
        n = 0
        for order in fills:
            n += 1
            res += self._get_price(order)
        return res / n

    @catch_exception(
        code=-2013, alternative={'status': OrderStatus.NOT_EXISTS.value, executed_quantity_: 0.0, price_: 0.0})
    @api_logging(text="Getting info by CustomOrderId")
    def _get_order_info_api(self, symbol, custom_order_id):
        """Send request to get order info"""
        return self.my_client.get_order(symbol=symbol, origClientOrderId=custom_order_id)

    def _get_partially_order_data_from_response(self, response) -> PartialResponse:
        """Get partially order data"""
        order_status, updated = self._convert_to_our_order_status(response[self.status_])
        res = dict()
        res.update({
            'status': order_status,
            'status_updated': updated,
            'price': self._get_price(response) if response.get(self.price_) else None,
            'avg_sold_market_price': self._get_avg_sold_price(response) if response.get(self.fills_) else None,
            'executed_quantity': self._get_executed_quantity(response)
        })
        return res

    def _convert_to_our_order_status(self, market_order_status: str) -> Tuple[OrderStatus, bool]:
        """Function to transform response orders statuses to our"""
        if market_order_status in self.ORDER_STATUSES_MATCH.keys():
            return self.ORDER_STATUSES_MATCH[market_order_status], True
        logger.debug(f"Status {market_order_status} not in ORDER_STATUSES_MATCH")
        return self.order_statuses.UNKNOWN.value, False

    @api_logging
    def _push_buy_limit_order(self, symbol: str, quantity: float, price: float, custom_order_id: str):
        """Send request to create Buy limit order"""
        response = self.my_client.order_limit_buy(
            symbol=symbol, quantity=quantity, price=price_to_str(price), newClientOrderId=custom_order_id)
        return response

    @api_logging
    def _push_sell_oco_order(self, symbol: str,
                             quantity: float, price: float,
                             stop_loss: float, custom_order_id: str,
                             custom_sl_order_id: str,
                             stop_limit_price: float):
        """Send request to create OCO order.
        We push one request to the Market, but two orders will be created:
        tp_order, sl_order
        """
        response = self.my_client.order_oco_sell(
            symbol=symbol,
            quantity=quantity,
            price=price_to_str(price),
            limitClientOrderId=custom_order_id,
            stopClientOrderId=custom_sl_order_id,
            stopPrice=price_to_str(stop_loss),
            stopLimitPrice=price_to_str(stop_limit_price),
            stopLimitTimeInForce=self.my_client.TIME_IN_FORCE_GTC)
        return response

    @api_logging
    def _push_sell_market_order(self,
                                symbol: str,
                                quantity: float,
                                custom_order_id: str):
        """Send request to create Market order.
        """
        response = self.my_client.order_market_sell(
            symbol=symbol,
            quantity=quantity,
            newClientOrderId=custom_order_id)
        return response

    @catch_exception(
        code=-2011, alternative={'status': OrderStatus.NOT_EXISTS.value, executed_quantity_: 0.0, price_: 0.0})
    @api_logging(text="Cancel order into Market")
    def _cancel_order(self, symbol: str, custom_order_id: str):
        """Send request to cancel order"""
        return self.my_client.cancel_order(symbol=symbol, origClientOrderId=custom_order_id)

    # @api_logging
    def _get_rules_api(self):
        """Send request to get Pairs rules info"""
        return self.my_client.get_exchange_info()

    @floated_result
    def __get_pair_rule(self, data: dict, first: str, order: int, second: str):
        """Parsing of response about Pairs rules"""
        return data[first][order][second]

    @floated_result
    def get_current_balance(self, coin) -> float:
        """Get balance by asset (coin)"""
        return self._get_balance_api(coin)[self.free_]

    @floated_result
    def get_current_price(self, symbol):
        """Send request to get current average price by pair (symbol)"""
        response = self.my_client.get_avg_price(symbol=symbol)
        return response[self.price_]

    @debug_input_and_returned
    def get_order_info(self, symbol, custom_order_id) -> PartialResponse:
        """Get transformed order info from the Market by api"""
        response = self._get_order_info_api(symbol, custom_order_id)
        return self._get_partially_order_data_from_response(response)

    def push_buy_limit_order(self, order: 'BuyOrder'):
        """Push Buy limit order"""
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=order.symbol, market=self).first()
        logger.debug(f"Rules: {order.symbol}: {pair.__dict__}")
        response = self._push_buy_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        order.update_order_api_history(status, executed_quantity)
        return response

    def push_sell_oco_order(self, order: 'SellOrder'):
        """
        Push OCO order.
        We push one request to the Market, but two orders will be created:
        tp_order, sl_order
        """
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=order.symbol, market=self).first()
        logger.debug(f"Rules: {order.symbol}: {pair.__dict__}")
        # TODO: change to sell order
        response = self._push_sell_oco_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price,
            custom_order_id=order.custom_order_id, custom_sl_order_id=order.sl_order.custom_order_id,
            stop_loss=order.stop_loss, stop_limit_price=order.sl_order.price)
        default_executed_quantity = 0.0
        default_status = OrderStatus.SENT.value
        order.update_order_api_history(default_status, default_executed_quantity)
        order.sl_order.update_order_api_history(default_status, default_executed_quantity)
        return response

    def push_sell_market_order(self, order: 'SellOrder'):
        """
        Push Market order.
        """
        from apps.pair.models import Pair
        pair = Pair.objects.filter(symbol=order.symbol, market=self).first()
        logger.debug(f"Rules: {order.symbol}: {pair.__dict__}")
        response = self._push_sell_market_order(
            symbol=order.symbol, quantity=order.quantity,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_sold_market_price = data.get('avg_sold_market_price')
        order.update_order_api_history(status, executed_quantity, avg_sold_market_price)
        return response

    def cancel_order(self, order: 'BaseOrder'):
        """Cancel order"""
        response = self._cancel_order(order.symbol, order.custom_order_id)
        # return self._get_partially_order_data_from_response(response)

    def update_pairs_info_api(self):
        """
        Create pairs rules info by info from the Market
        """
        from apps.pair.models import Pair

        info = self._get_rules_api()[self.symbols_]
        for i in info:
            symbol = i[self.symbol_]
            min_price = self.__get_pair_rule(i, self.filters_, 0, self.minPrice_)
            step_price = self.__get_pair_rule(i, self.filters_, 0, self.stepPrice_)
            min_quantity = self.__get_pair_rule(i, self.filters_, 2, self.minQty_)
            min_amount = self.__get_pair_rule(i, self.filters_, 3, self.minAmount_)
            step_size = self.__get_pair_rule(i, self.filters_, 2, self.stepSize_)
            if not Pair.objects.filter(symbol=symbol):
                logger.debug(f"Add a new pair rule {symbol}")
                Pair.objects.create(symbol=symbol,
                                    min_price=min_price,
                                    step_price=step_price,
                                    step_quantity=step_size,
                                    min_quantity=min_quantity,
                                    min_amount=min_amount,
                                    market=self)
