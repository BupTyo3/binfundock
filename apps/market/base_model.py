import logging
import time

from abc import ABC, abstractmethod
from typing import Tuple, Union, Optional, Callable, Type, List, TypedDict

from django.db import models

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus, NOT_EXISTS_ORDER_STATUSES
from .base_client import BaseClient
from .utils import MarketAPIExceptionError

from tools.tools import debug_input_and_returned

logger = logging.getLogger(__name__)


class SymbolPriceDict(TypedDict):
    symbol: str
    price: str


class BaseExternalAPIException(Exception):
    code: int
    message: str


class PartialResponse(TypedDict):
    status: str
    status_updated: bool
    price: float
    executed_quantity: float
    avg_executed_market_price: Optional[float]


class BaseMarketException(ABC):
    """
    """
    @property
    @abstractmethod
    def api_exception(self) -> BaseExternalAPIException:
        pass

    @property
    @abstractmethod
    def api_errors(self) -> Type[MarketAPIExceptionError]:
        pass


class BaseMarketLogic(ABC):

    get_order_info_retry_count_default = 5
    get_order_info_retry_delay_default = 0.7

    asset_ = 'asset'
    balance_ = 'balance'
    balances_ = 'balances'
    filters_ = 'filters'
    free_ = 'free'
    locked_ = 'locked'
    quantity_ = 'quantity'
    side_ = 'side'
    status_ = 'status'
    symbol_ = 'symbol'
    symbols_ = 'symbols'
    time_ = 'time'
    type_ = 'type'

    order_statuses: OrderStatus = OrderStatus

    @abstractmethod
    def _get_partially_order_data_from_response(self, response: dict) -> PartialResponse:
        """Get partially order data"""
        pass

    @abstractmethod
    def _get_order_info_api(self, symbol: str, custom_order_id: str) -> dict:
        """Send request to get order info"""
        pass

    @debug_input_and_returned
    def get_order_info(self,
                       symbol: Union[str, models.CharField],
                       custom_order_id: str,
                       retry_statuses: Optional[List[str]] = None,
                       retry_count: int = get_order_info_retry_count_default,
                       retry_delay: float = get_order_info_retry_delay_default,
                       ) -> PartialResponse:
        """
        Get transformed order info from the Market by api.
        Added Retry functionality:
        If we get not_exists status we do retry to get order info from the Market
        retry_statuses: the same from alternative part in @catch_exception decorator
         above _get_order_info_api to catch Market exceptions
        """
        data = dict()
        retry_statuses = NOT_EXISTS_ORDER_STATUSES if not retry_statuses else retry_statuses

        for i in range(retry_count):
            logger.debug(f"The Attempt number '{i}' to get order_info by order: '{custom_order_id}'")
            if i:
                time.sleep(retry_delay)
            response = self._get_order_info_api(symbol, custom_order_id)
            data = self._get_partially_order_data_from_response(response)
            if data.get('status') not in retry_statuses:
                break
        return data

    @property
    @abstractmethod
    def market(self) -> 'BaseMarket':
        pass

    @property
    @abstractmethod
    def type(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def market_fee(self) -> float:
        pass

    @property
    @abstractmethod
    def client_class(self) -> Type[BaseClient]:
        pass

    @property
    @abstractmethod
    def exception_class(self) -> BaseMarketException:
        pass

    @property
    @abstractmethod
    def order_id_separator(self) -> str:
        pass

    @property
    def my_client(self):
        logger.debug('Get MY_CLIENT')
        return self.client_class.activate_connection()

    @abstractmethod
    def update_pairs_info_api(self) -> None:
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_current_balance(self, coin: str) -> float:
        pass

    def get_ticker_current_prices(self, symbol: Optional[str] = None) -> List[SymbolPriceDict]:
        pass

    @abstractmethod
    def push_buy_limit_order(self, order):
        pass

    @abstractmethod
    def push_sell_market_order(self, order):
        pass

    @abstractmethod
    def push_sell_oco_order(self, order):
        pass

    @abstractmethod
    def cancel_order(self, order):
        pass


class BaseMarket(SystemBaseModel):
    name: str

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def logic(self) -> BaseMarketLogic:
        pass

    @abstractmethod
    def is_spot_market(self) -> bool:
        pass

    @abstractmethod
    def is_futures_market(self) -> bool:
        pass
