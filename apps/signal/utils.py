from enum import Enum


class SignalStatus(Enum):
    NEW = 'new'
    FORMED = 'formed'  # form_buy_orders
    PUSHED = 'pushed'
    BOUGHT = 'bought'
    CLOSED = 'closed'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

