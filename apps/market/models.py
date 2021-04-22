import logging

from asgiref.sync import sync_to_async
from django.db import models
from django.contrib.auth import get_user_model

from typing import (
    Tuple, TypedDict, TYPE_CHECKING,
    Union, Callable, Type, Any,
    Optional, List
)

from binance import client
from binance.exceptions import BinanceAPIException
from apps.order.utils import OrderStatus
from .base_model import (
    BaseMarket,
    BaseMarketLogic,
    BaseMarketException,
    PartialResponse,
)
from .utils import (
    MarketType,
    MarketAPIExceptionError,
)
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


def get_or_create_market() -> BaseMarket:
    market_obj, created = Market.objects.get_or_create(name=BiMarketLogic.name)
    if created:
        logger.debug(f"Market '{market_obj}' has been created")
    return market_obj


def get_or_create_futures_market() -> BaseMarket:
    market_obj, created = Market.objects.get_or_create(name=BiFuturesMarketLogic.name)
    if created:
        logger.debug(f"Market '{market_obj}' has been created")
    return market_obj

@sync_to_async
def get_or_create_async_futures_market() -> BaseMarket:
    market_obj, created = Market.objects.get_or_create(name=BiFuturesMarketLogic.name)
    if created:
        logger.debug(f"Market '{market_obj}' has been created")
    return market_obj


class BiClient(client.Client, BaseClient):
    api_client_class = client.Client
    api_key = conf_obj.market_api_key
    api_secret = conf_obj.market_api_secret


class BiFuturesClient(client.Client, BaseClient):
    api_client_class = client.Client
    api_key = conf_obj.futures_market_api_key
    api_secret = conf_obj.futures_market_api_secret


class Market(BaseMarket):
    default_name = 'Binance'
    name = models.CharField(max_length=32,
                            unique=True,
                            default=default_name)

    objects = models.Manager()

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        """Addition: Fill DB by Pairs rules data from the Market api"""
        super().save(*args, **kwargs)
        self.logic.update_pairs_info_api()

    @property
    def logic(self) -> BaseMarketLogic:
        if self.name == BiMarketLogic.name:
            return BiMarketLogic()
        elif self.name == BiFuturesMarketLogic.name:
            return BiFuturesMarketLogic()

    def is_spot_market(self) -> bool:
        return True if self.logic.type == MarketType.SPOT.value else False

    def is_futures_market(self) -> bool:
        return True if self.logic.type == MarketType.FUTURES.value else False


class BinanceDataMixin:
    askPrice_ = 'askPrice'
    avgPrice_ = 'avgPrice'
    baseAsset_ = 'baseAsset'
    bidPrice_ = 'bidPrice'
    fills_ = 'fills'
    minAmount_ = 'minNotional'
    minPrice_ = 'minPrice'
    minQty_ = 'minQty'
    orderId_ = 'orderId'
    origQty_ = 'origQty'
    price_ = 'price'
    quoteAsset_ = 'quoteAsset'
    stepPrice_ = 'tickSize'
    stepSize_ = 'stepSize'
    stopPrice_ = 'stopPrice'
    executed_quantity_ = 'executedQty'

    @floated_result
    def _get_pair_rule(self, data: dict, first: str, order: int, second: str):
        """Parsing of response about Pairs rules"""
        return data[first][order][second]

    @floated_result
    def _get_price(self, response) -> float:
        """Get partially data by key price"""
        return response.get(self.price_)

    @floated_result
    def _get_executed_quantity(self, response) -> float:
        """Get partially data by key executed_quantity"""
        return response[self.executed_quantity_]

    @floated_result
    def _get_avg_executed_price(self, response) -> float:
        """Get partially data by key price"""
        avg_price = response.get(self.avgPrice_)
        if avg_price:
            return avg_price
        fills = response.get(self.fills_)
        if not fills:
            return 0
        res = 0
        n = 0
        for order in fills:
            n += 1
            res += self._get_price(order)
        return res / n


class BinanceFuturesDataMixin:
    available_balance_ = 'withdrawAvailable'
    order_type_stop_market = 'STOP_MARKET'


class BiMarketException(BaseMarketException):
    """
    """
    api_exception = BinanceAPIException
    api_errors = MarketAPIExceptionError


class BiMarketLogic(BaseMarketLogic,
                    BinanceDataMixin):
    type = MarketType.SPOT.value
    raw_url = conf_obj.market_spot_raw_url
    name = 'Binance'
    market_fee = conf_obj.market_fee
    limit_history = 500

    order_id_separator = 'bim'
    client_class = BiClient
    exception_class = BiMarketException

    ORDER_STATUSES_MATCH: dict = {
        client_class.ORDER_STATUS_CANCELED:
            BaseMarketLogic.order_statuses.CANCELED.value,
        client_class.ORDER_STATUS_FILLED:
            BaseMarketLogic.order_statuses.COMPLETED.value,
        client_class.ORDER_STATUS_PARTIALLY_FILLED:
            BaseMarketLogic.order_statuses.PARTIAL.value,
        client_class.ORDER_STATUS_NEW:
            BaseMarketLogic.order_statuses.SENT.value,
        client_class.ORDER_STATUS_EXPIRED:
            BaseMarketLogic.order_statuses.EXPIRED.value,
        BaseMarketLogic.order_statuses.NOT_EXISTS.value:
            BaseMarketLogic.order_statuses.NOT_EXISTS.value,
    }

    @property
    def market(self) -> 'BaseMarket':
        market, created = Market.objects.get_or_create(name=self.name)
        return market

    def _get_ticker_current_prices(self, symbol: Optional[str] = None):
        kwargs = dict()
        if symbol:
            kwargs.update({'symbol': symbol})
        return self.my_client.get_symbol_ticker(**kwargs)

    def get_ticker_current_prices(self, symbol: Optional[str] = None):
        return self._get_ticker_current_prices(symbol=symbol)

    @api_logging
    def _get_balance_api(self, coin):
        """Send request to get balance by asset (coin)"""
        return self.my_client.get_asset_balance(coin)

    @catch_exception(
        code=exception_class.api_errors.NO_SUCH_ORDER.value.code,
        alternative={'status': OrderStatus.NOT_EXISTS.value, 'executedQty': 0.0, 'price': 0.0})
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
            'avg_executed_market_price': self._get_avg_executed_price(response),
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
                             trigger: float, custom_order_id: str,
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
            stopPrice=price_to_str(trigger),
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
        code=exception_class.api_errors.CANCEL_REJECTED.value.code,
        alternative={'status': OrderStatus.NOT_EXISTS.value, 'executedQty': 0.0, 'price': 0.0})
    @api_logging(text="Cancel order into Market")
    def _cancel_order(self, symbol: str, custom_order_id: str):
        """Send request to cancel order"""
        return self.my_client.cancel_order(symbol=symbol, origClientOrderId=custom_order_id)

    # @api_logging
    def _get_rules_api(self):
        """Send request to get Pairs rules info"""
        return self.my_client.get_exchange_info()

    @floated_result
    def get_current_balance(self, coin) -> float:
        """Get balance by asset (coin)"""
        return self._get_balance_api(coin)[self.free_]

    @floated_result
    def get_current_price(self, symbol):
        """Send request to get current average price by pair (symbol)"""
        response = self.my_client.get_avg_price(symbol=symbol)
        return response[self.price_]

    def push_buy_limit_order(self, order: 'BuyOrder'):
        """Push Buy limit order"""
        response = self._push_buy_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def push_sell_oco_order(self, order: 'SellOrder'):
        """
        Push OCO order.
        We push one request to the Market, but two orders will be created:
        tp_order, sl_order
        """
        # TODO: change to sell order
        response = self._push_sell_oco_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price,
            custom_order_id=order.custom_order_id, custom_sl_order_id=order.sl_order.custom_order_id,
            trigger=order.sl_order.trigger, stop_limit_price=order.sl_order.price)
        default_executed_quantity = 0.0
        default_status = OrderStatus.SENT.value
        order.update_order_api_history(default_status, default_executed_quantity, order.price)
        order.sl_order.update_order_api_history(default_status, default_executed_quantity, order.sl_order.price)
        return response

    def push_sell_market_order(self, order: 'SellOrder'):
        """
        Push Market order.
        """
        response = self._push_sell_market_order(
            symbol=order.symbol, quantity=order.quantity,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def cancel_order(self, order: 'BaseOrder'):
        """Cancel order"""
        self._cancel_order(order.symbol, order.custom_order_id)

    @debug_input_and_returned
    def update_pairs_info_api(self):
        """
        Create pairs rules info by info from the Market
        """
        from apps.pair.models import Pair

        info = self._get_rules_api()[self.symbols_]
        for i in info:
            symbol = i[self.symbol_]
            min_price = self._get_pair_rule(i, self.filters_, 0, self.minPrice_)
            step_price = self._get_pair_rule(i, self.filters_, 0, self.stepPrice_)
            min_quantity = self._get_pair_rule(i, self.filters_, 2, self.minQty_)
            min_amount = self._get_pair_rule(i, self.filters_, 3, self.minAmount_)
            step_size = self._get_pair_rule(i, self.filters_, 2, self.stepSize_)
            if not Pair.objects.filter(symbol=symbol, market=self.market):
                logger.debug(f"Add a new pair rule {symbol}")
                Pair.objects.create(symbol=symbol,
                                    min_price=min_price,
                                    step_price=step_price,
                                    step_quantity=step_size,
                                    min_quantity=min_quantity,
                                    min_amount=min_amount,
                                    market=self.market)


class BiFuturesMarketException(BaseMarketException):
    """
    """
    api_exception = BinanceAPIException
    api_errors = MarketAPIExceptionError


class BiFuturesMarketLogic(BaseMarketLogic,
                           BinanceDataMixin,
                           BinanceFuturesDataMixin):
    name = 'BiFutures'
    raw_url = conf_obj.market_futures_raw_url
    order_id_separator = 'bifu'
    market_fee = conf_obj.futures_market_fee
    type = MarketType.FUTURES.value

    client_class = BiFuturesClient
    exception_class = BiFuturesMarketException

    ORDER_STATUSES_MATCH: dict = {
        client_class.ORDER_STATUS_CANCELED:
            BaseMarketLogic.order_statuses.CANCELED.value,
        client_class.ORDER_STATUS_FILLED:
            BaseMarketLogic.order_statuses.COMPLETED.value,
        client_class.ORDER_STATUS_PARTIALLY_FILLED:
            BaseMarketLogic.order_statuses.PARTIAL.value,
        client_class.ORDER_STATUS_NEW:
            BaseMarketLogic.order_statuses.SENT.value,
        client_class.ORDER_STATUS_EXPIRED:
            BaseMarketLogic.order_statuses.EXPIRED.value,
        BaseMarketLogic.order_statuses.NOT_EXISTS.value:
            BaseMarketLogic.order_statuses.NOT_EXISTS.value,
    }

    @property
    def market(self) -> 'BaseMarket':
        market, created = Market.objects.get_or_create(name=self.name)
        return market

    @floated_result
    def get_current_price(self, symbol):
        """Send request to get Position info filtering it by symbol and obtaining its current mark price"""
        response = self._get_position_info(symbol=symbol)
        mark_price = response[0].get('markPrice')
        return mark_price

    def get_ticker_current_prices(self, symbol: Optional[str] = None):
        pass

    @api_logging
    def _get_balance_api(self):
        """Send request to get balance"""
        return self.my_client.futures_account_balance()

    @floated_result
    def get_current_balance(self, coin) -> float:
        """Get balance by asset (coin)"""
        response = self._get_balance_api()
        for asset_data in response:
            if asset_data.get(self.asset_) == coin:
                avail_bal = asset_data.get(self.available_balance_)
                bal = asset_data.get(self.balance_)
                return avail_bal if avail_bal else bal

    def _convert_to_our_order_status(self, market_order_status: str) -> Tuple[OrderStatus, bool]:
        """Function to transform response orders statuses to our"""
        if market_order_status in self.ORDER_STATUSES_MATCH.keys():
            return self.ORDER_STATUSES_MATCH[market_order_status], True
        logger.debug(f"Status {market_order_status} not in ORDER_STATUSES_MATCH")
        return self.order_statuses.UNKNOWN.value, False

    @catch_exception(
        code=exception_class.api_errors.NO_SUCH_ORDER.value.code,
        alternative={'status': OrderStatus.NOT_EXISTS.value, 'executedQty': 0.0, 'price': 0.0})
    @api_logging(text="Getting info by CustomOrderId")
    def _get_order_info_api(self, symbol, custom_order_id):
        """Send request to get order info"""
        return self.my_client.futures_get_order(symbol=symbol, origClientOrderId=custom_order_id)

    @api_logging
    def _get_position_info(self, symbol):
        """Send request to get position info"""
        return self.my_client.futures_position_information(symbol=symbol)

    @api_logging
    def _set_leverage(self, symbol, leverage):
        self.my_client.futures_change_leverage(symbol=symbol, leverage=leverage)

    @catch_exception(
        # TODO: change alternative if needs
        code=exception_class.api_errors.INVALID_OPTIONS_EVENT_TYPE.value.code,
        alternative={})
    @api_logging
    def _change_margin_type(self, symbol, margin_type):
        """
        Types margin: crossed (high risks, all money you are able to lose)
        isolated (use money are allocated only for the order)
        """
        self.my_client.futures_change_margin_type(symbol=symbol, marginType=margin_type)

    def _get_partially_order_data_from_response(self, response) -> PartialResponse:
        """Get partially order data"""
        order_status, updated = self._convert_to_our_order_status(response[self.status_])
        res = dict()
        res.update({
            'status': order_status,
            'status_updated': updated,
            'price': self._get_price(response) if response.get(self.price_) else None,
            'avg_executed_market_price': self._get_avg_executed_price(response),
            'executed_quantity': self._get_executed_quantity(response)
        })
        return res
    
    @api_logging
    def _push_buy_limit_order(self, symbol: str, quantity: float, price: float, custom_order_id: str):
        """Send request to create BUY LIMIT order"""
        response = self.my_client.futures_create_order(
            symbol=symbol,
            side=self.my_client.SIDE_BUY,
            type=self.my_client.ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=price_to_str(price),
            newClientOrderId=custom_order_id,
            timeInForce=self.my_client.TIME_IN_FORCE_GTC)
        return response

    @api_logging
    def _push_sell_limit_order(self, symbol: str, quantity: float, price: float, custom_order_id: str):
        """Send request to create SELL LIMIT order"""
        response = self.my_client.futures_create_order(
            symbol=symbol,
            side=self.my_client.SIDE_SELL,
            type=self.my_client.ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=price_to_str(price),
            newClientOrderId=custom_order_id,
            timeInForce=self.my_client.TIME_IN_FORCE_GTC)
        return response

    @api_logging
    def _push_sell_tp_order(self, symbol: str,
                            quantity: float, price: float,
                            stop_trigger: float, custom_order_id: str):
        """Send request to create TAKE PROFIT order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_SELL,
            type=self.my_client.ORDER_TYPE_TAKE_PROFIT,
            symbol=symbol,
            quantity=quantity,
            reduceOnly=True,
            price=price_to_str(price),
            newClientOrderId=custom_order_id,
            stopPrice=price_to_str(stop_trigger),
            stopLimitTimeInForce=self.my_client.TIME_IN_FORCE_GTC)
        return response

    @api_logging
    def _push_buy_tp_order(self, symbol: str,
                           quantity: float, price: float,
                           stop_trigger: float, custom_order_id: str):
        """Send request to create TAKE PROFIT order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_BUY,
            type=self.my_client.ORDER_TYPE_TAKE_PROFIT,
            symbol=symbol,
            quantity=quantity,
            reduceOnly=True,
            price=price_to_str(price),
            newClientOrderId=custom_order_id,
            stopPrice=price_to_str(stop_trigger),
            stopLimitTimeInForce=self.my_client.TIME_IN_FORCE_GTC)
        return response

    @api_logging
    def _push_sell_gl_sl_market_order(self,
                                      symbol: str,
                                      quantity: float,
                                      stop_price: float,
                                      custom_order_id: str):
        """Send request to create STOP MARKET order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_SELL,
            type=self.order_type_stop_market,
            symbol=symbol,
            reduceOnly=True,
            stopPrice=price_to_str(stop_price),
            quantity=quantity,
            newClientOrderId=custom_order_id)
        return response

    @api_logging
    def _push_buy_gl_sl_market_order(self,
                                     symbol: str,
                                     quantity: float,
                                     stop_price: float,
                                     custom_order_id: str):
        """Send request to create STOP MARKET order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_BUY,
            type=self.order_type_stop_market,
            symbol=symbol,
            reduceOnly=True,
            stopPrice=price_to_str(stop_price),
            quantity=quantity,
            newClientOrderId=custom_order_id)
        return response

    @api_logging
    def _push_sell_market_order(self,
                                symbol: str,
                                quantity: float,
                                custom_order_id: str):
        """Send request to create SELL MARKET order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_SELL,
            type=self.my_client.ORDER_TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
            newClientOrderId=custom_order_id)
        return response

    @api_logging
    def _push_buy_market_order(self,
                               symbol: str,
                               quantity: float,
                               custom_order_id: str):
        """Send request to create BUY MARKET order.
        """
        response = self.my_client.futures_create_order(
            side=self.my_client.SIDE_BUY,
            type=self.my_client.ORDER_TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
            newClientOrderId=custom_order_id)
        return response

    @catch_exception(
        code=exception_class.api_errors.CANCEL_REJECTED.value.code,
        alternative={'status': OrderStatus.NOT_EXISTS.value, 'executedQty': 0.0, 'price': 0.0})
    @api_logging(text="Cancel order into Market")
    def _cancel_order(self, symbol: str, custom_order_id: str):
        """Send request to cancel order"""
        return self.my_client.futures_cancel_order(symbol=symbol, origClientOrderId=custom_order_id)

    def _push_preconditions(self, order: 'BaseOrder'):
        try:
            # Set leverage
            self._set_leverage(order.symbol, order.signal.leverage)
            # Set margin type
            self._change_margin_type(order.symbol, order.signal.margin_type)
        except BiFuturesMarketException.api_exception as ex:
            logger.error(f'ORDER {order.id} for {order.symbol}, PUSH PRECONDITIONS ERROR: {ex}')

    def push_buy_limit_order(self, order: 'BuyOrder'):
        """Push BUY LIMIT order to Futures"""
        self._push_preconditions(order=order)

        response = self._push_buy_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def push_sell_limit_order(self, order: 'BuyOrder'):
        """Push SELL LIMIT order to Futures"""
        self._push_preconditions(order=order)

        response = self._push_sell_limit_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price, custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def push_sell_market_order(self, order):
        """
        Push SELL MARKET order.
        """
        self._push_preconditions(order=order)

        response = self._push_sell_market_order(
            symbol=order.symbol, quantity=order.quantity,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def push_buy_market_order(self, order):
        """
        Push BUY MARKET order.
        """
        self._push_preconditions(order=order)

        response = self._push_buy_market_order(
            symbol=order.symbol, quantity=order.quantity,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price)
        return response

    def push_sell_gl_sl_market_order(self, order):
        """
        Push SELL STOP MARKET order.
        """
        self._push_preconditions(order=order)

        response = self._push_sell_gl_sl_market_order(
            symbol=order.symbol, quantity=order.quantity, stop_price=order.price,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price or order.price)
        return response

    def push_buy_gl_sl_market_order(self, order):
        """
        Push BUY STOP MARKET order.
        """
        self._push_preconditions(order=order)

        response = self._push_buy_gl_sl_market_order(
            symbol=order.symbol, quantity=order.quantity, stop_price=order.price,
            custom_order_id=order.custom_order_id)
        data = self._get_partially_order_data_from_response(response)
        status, executed_quantity = data.get('status'), data.get('executed_quantity')
        avg_executed_market_price = data.get('avg_executed_market_price')
        order.update_order_api_history(status, executed_quantity, avg_executed_market_price or order.price)
        return response

    def push_sell_oco_order(self, order):
        pass

    def push_sell_tp_order(self, order: 'SellOrder'):
        """
        Push TP order.
        """
        self._push_preconditions(order=order)

        response = self._push_sell_tp_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price,
            custom_order_id=order.custom_order_id, stop_trigger=order.trigger)
        default_executed_quantity = 0.0
        default_status = OrderStatus.SENT.value
        order.update_order_api_history(default_status, default_executed_quantity, order.price)
        return response

    def push_buy_tp_order(self, order: 'SellOrder'):
        """
        Push TP order.
        """
        self._push_preconditions(order=order)

        response = self._push_buy_tp_order(
            symbol=order.symbol, quantity=order.quantity, price=order.price,
            custom_order_id=order.custom_order_id, stop_trigger=order.trigger)
        default_executed_quantity = 0.0
        default_status = OrderStatus.SENT.value
        order.update_order_api_history(default_status, default_executed_quantity, order.price)
        return response

    def cancel_order(self, order: 'BaseOrder'):
        """Cancel order"""
        self._cancel_order(order.symbol, order.custom_order_id)

    # @api_logging
    def _get_rules_api(self):
        """Send request to get Pairs rules info"""
        return self.my_client.futures_exchange_info()

    @debug_input_and_returned
    def update_pairs_info_api(self) -> None:
        """
        Create pairs rules info by info from the Market
        """
        from apps.pair.models import Pair
        min_amount = 0.00000001

        info = self._get_rules_api()[self.symbols_]
        for i in info:
            symbol = i[self.symbol_]
            min_price = self._get_pair_rule(i, self.filters_, 0, self.minPrice_)
            step_price = self._get_pair_rule(i, self.filters_, 0, self.stepPrice_)
            min_quantity = self._get_pair_rule(i, self.filters_, 1, self.minQty_)
            step_size = self._get_pair_rule(i, self.filters_, 1, self.stepSize_)
            if not Pair.objects.filter(symbol=symbol, market=self.market):
                logger.debug(f"Add a new pair rule {symbol}")
                Pair.objects.create(symbol=symbol,
                                    min_price=min_price,
                                    step_price=step_price,
                                    step_quantity=step_size,
                                    min_quantity=min_quantity,
                                    min_amount=min_amount,
                                    market=self.market)
