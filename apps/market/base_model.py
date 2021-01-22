import logging

from abc import ABC, abstractmethod
from typing import Tuple, Union, Optional, Callable, Type, List, TypedDict

from django.db import models

from utils.framework.models import SystemBaseModel

from apps.order.utils import OrderStatus
from .base_client import BaseClient
from .utils import MarketAPIExceptionError

logger = logging.getLogger(__name__)


class SymbolPriceDict(TypedDict):
    symbol: str
    price: str


class BaseMarketException(ABC):
    """
    """
    @property
    @abstractmethod
    def api_exception(self) -> Type[Exception]:
        pass

    @property
    @abstractmethod
    def api_errors(self) -> Type[MarketAPIExceptionError]:
        pass


class BaseMarketLogic(ABC):
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
    def exception_class(self) -> Type[BaseMarketException]:
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
    def get_order_info(self, symbol: Union[str, models.CharField], custom_order_id: str) -> Tuple[OrderStatus, float]:
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
