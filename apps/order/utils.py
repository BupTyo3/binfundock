from enum import Enum


class OrderStatus(Enum):
    CANCELED = 'canceled'
    COMPLETED = 'completed'
    PARTIAL = 'partial'
    NOT_SENT = 'not_sent'
    NOT_EXISTS = 'not_exists'
    SENT = 'sent'
    UNKNOWN = 'unknown'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

