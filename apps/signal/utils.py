import logging

from enum import Enum
from typing import List, Union


logger = logging.getLogger(__name__)


class SignalStatus(Enum):
    NEW = 'new'
    FORMED = 'formed'  # first_forming
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


def calculate_position(stop_loss: Union[float, str],
                       entry_points: List[Union[float, str]],
                       take_profits: List[Union[float, str]]):
    """
    Calculate position: LONG or SHORT
    """
    entry_points = [float(i) for i in entry_points]
    take_profits = [float(i) for i in take_profits]
    stop_loss = float(stop_loss)

    max_entry = max(entry_points)
    min_entry = min(entry_points)
    min_take = min(take_profits)
    max_take = max(take_profits)

    if max_entry < min_take and stop_loss < min_entry:
        position = SignalPosition.LONG.value
        logger.debug(f"{position}")
    elif min_entry > max_take and stop_loss > max_entry:
        position = SignalPosition.SHORT.value
        logger.debug(f"{position}")
    else:
        logger.error("Wrong info in the signal!")
        return 'error'
    return position

