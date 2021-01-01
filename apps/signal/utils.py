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
    ERROR = 'error'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class MarginType(Enum):
    ISOLATED = 'ISOLATED'
    CROSSED = 'CROSSED'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


FORMED__SIG_STATS = [
    SignalStatus.FORMED.value,
]
FORMED_PUSHED__SIG_STATS = [
    SignalStatus.FORMED.value,
    SignalStatus.PUSHED.value,
]
FORMED_PUSHED_BOUGHT__SIG_STATS = [
    SignalStatus.FORMED.value,
    SignalStatus.PUSHED.value,
    SignalStatus.BOUGHT.value,
]
FORMED_PUSHED_BOUGHT_SOLD__SIG_STATS = [
    SignalStatus.FORMED.value,
    SignalStatus.PUSHED.value,
    SignalStatus.BOUGHT.value,
    SignalStatus.SOLD.value,
]
FORMED_PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS = [
    SignalStatus.FORMED.value,
    SignalStatus.PUSHED.value,
    SignalStatus.BOUGHT.value,
    SignalStatus.SOLD.value,
    SignalStatus.CANCELING.value,
]
PUSHED_BOUGHT_SOLD__SIG_STATS = [
    SignalStatus.PUSHED.value,
    SignalStatus.BOUGHT.value,
    SignalStatus.SOLD.value,
]
PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS = [
    SignalStatus.PUSHED.value,
    SignalStatus.BOUGHT.value,
    SignalStatus.SOLD.value,
    SignalStatus.CANCELING.value,
]
BOUGHT_SOLD__SIG_STATS = [
    SignalStatus.BOUGHT.value,
    SignalStatus.SOLD.value,
]
SOLD__SIG_STATS = [
    SignalStatus.SOLD.value,
]
BOUGHT__SIG_STATS = [
    SignalStatus.BOUGHT.value,
]
ERROR__SIG_STATS = [
    SignalStatus.ERROR.value,
]


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

