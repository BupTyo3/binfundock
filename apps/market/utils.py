import logging

from enum import Enum

logger = logging.getLogger(__name__)


class MarketType(Enum):
    SPOT = 'spot'
    FUTURES = 'futures'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class APIError(object):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __repr__(self):
        return f'APIError(code={self.code}): {self.msg}'


class MarketAPIExceptionError(Enum):
    """
    List of errors of binance e.g.:
    https://binance-docs.github.io/apidocs/futures/en/
    It can be overridden to assign specific errors' responses of the other Market
    """
    MARGIN_NOT_SUFFICIEN = APIError(-2019, 'Margin is insufficient.')
    MIN_NOTIONAL_FILTER = APIError(-1013, 'Filter failure: MIN_NOTIONAL')
    INVALID_TIMESTAMP = APIError(-1021, 'Timestamp for this request is outside of the recvWindow.')
    QTY_LESS_THAN_ZERO = APIError(-4003, 'Quantity less than zero.')
    ORDER_WOULD_IMMEDIATELY_TRIGGER = APIError(-2021, 'Order would immediately trigger.')
    NO_SUCH_ORDER = APIError(-2013, 'Order does not exist.')
    CANCEL_REJECTED = APIError(-2011, 'CANCEL_REJECTED')
    INVALID_OPTIONS_EVENT_TYPE = APIError(-4066, 'Invalid options event type')
    LEVERAGE_REDUCTION_NOT_SUPPORTED = APIError(-4161, 'Leverage reduction is not supported in Isolated Margin Mode '
                                                       'with open positions')

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]
