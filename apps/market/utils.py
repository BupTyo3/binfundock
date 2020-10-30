import logging

from enum import Enum

logger = logging.getLogger(__name__)


class MarketType(Enum):
    SPOT = 'spot'
    FUTURES = 'futures'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

