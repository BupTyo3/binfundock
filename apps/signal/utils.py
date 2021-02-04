import logging

from enum import Enum
from functools import partial, wraps
from typing import List, Union, TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from .base_model import BaseSignal


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
NEW_FORMED_PUSHED__SIG_STATS = [
    SignalStatus.NEW.value,
    SignalStatus.FORMED.value,
    SignalStatus.PUSHED.value,
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

SIG_STATS_FOR_SPOIL_WORKER = NEW_FORMED_PUSHED__SIG_STATS


class SignalPosition(Enum):
    LONG = 'long'  # BUY
    SHORT = 'short'  # SELL
    ERROR = 'error'  # something wrong with the signal

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


CORRECT_SIGNAL_POSITIONS = [
    SignalPosition.LONG.value,
    SignalPosition.SHORT.value,
]


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


def refuse_if_busy(func: Optional[Callable] = None):
    """
    Decorator to refuse doing the task if the object
     of Signal model is busy with another task
    @refuse_if_busy
    @refuse_if_busy()
    """
    if func is None:
        return partial(refuse_if_busy)

    @wraps(func)
    def wrapper(self: 'BaseSignal', *args, **kwargs):
        if self.is_busy:
            logger.debug(f"'{self}' - IS_BUSY_NOW")
            return
        self.is_busy = True
        self.save()
        try:
            result = func(self, *args, **kwargs)
        except Exception as ex:
            logger.warning(f"IS_BUSY_EXCEPTION: '{ex}'")
            # Code duplicating to unset the flag
            # failed to access the variable ex outside the block
            # but anyway we want to raise the exception to understand what happened
            # TODO: Maybe should handle DB lock exception
            self.is_busy = False
            self.save()
            raise ex
        self.is_busy = False
        self.save()
        return result
    return wrapper
