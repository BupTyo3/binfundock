from enum import Enum


class OrderStatus(Enum):
    CANCELED = 'canceled'
    COMPLETED = 'completed'
    PARTIAL = 'partial'
    NOT_SENT = 'not_sent'
    NOT_EXISTS = 'not_exists'
    SENT = 'sent'
    EXPIRED = 'expired'
    UNKNOWN = 'unknown'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


OPENED_ORDER_STATUSES = [
    OrderStatus.NOT_SENT.value,
    OrderStatus.SENT.value,
]
SENT_ORDER_STATUSES = [
    OrderStatus.SENT.value,
]


class OrderType(Enum):
    LIMIT = 'limit'
    MARKET = 'market'
    TAKE_PROFIT = 'take_profit'
    STOP_LOSS = 'stop_loss'
    STOP_LOSS_LIMIT = 'stop_loss_limit'
    STOP_MARKET = 'stop_market'
    TAKE_PROFIT_LIMIT = 'take_profit_limit'
    LIMIT_MAKER = 'limit_maker'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

