from enum import Enum


class SignalStatus(Enum):
    NEW = 'new'
    FORMED = 'formed'  # form_buy_orders
    PUSHED = 'pushed'
    BOUGHT = 'bought'
    SOLD = 'sold'
    CANCELING = 'canceling'
    CLOSED = 'closed'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class SignalPosition(Enum):
    LONG = 'long'  # BUY
    SHORT = 'short'  # SELL
    ERROR = 'error'  # something wrong with the signal

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

