import logging

from abc import abstractmethod
from typing import Optional, TYPE_CHECKING, Union, Type

from django.db import models

from utils.framework.models import SystemBaseModel, SystemBaseModelWithoutModified
from tools.tools import debug_input_and_returned
from .utils import (
    SignalStatus,
    SignalPosition,
    MarginType,
    CORRECT_SIGNAL_POSITIONS,
)

if TYPE_CHECKING:
    from apps.techannel.base_model import TechannelBase
    from apps.market.base_model import BaseMarket, BaseMarketLogic, BaseMarketException

logger = logging.getLogger(__name__)


class BaseBaseSignal(SystemBaseModel):
    techannel: 'TechannelBase'
    outer_signal_id: int
    leverage: int
    margin_type: MarginType
    position: SignalPosition
    entry_points: 'BaseEntryPoint.objects'
    take_profits: 'BaseTakeProfit.objects'

    def is_position_short(self) -> bool:
        return True if self.position == SignalPosition.SHORT.value else False

    def is_position_correct(self) -> bool:
        return True if self.position.upper() in map(str.upper, CORRECT_SIGNAL_POSITIONS) else False

    def remove_near_tp(self):
        if self.is_position_short():
            near_tp = self.take_profits.order_by('value').last()
        else:
            near_tp = self.take_profits.order_by('value').first()
        if near_tp:
            logger.debug(f"'{self}': '{near_tp}' will be deleted")
            near_tp.delete()
            return True
        return False

    def remove_far_tp(self):
        if self.is_position_short():
            far_tp = self.take_profits.order_by('value').first()
        else:
            far_tp = self.take_profits.order_by('value').last()
        if far_tp:
            logger.debug(f"'{self}': '{far_tp}' will be deleted")
            far_tp.delete()
            return True
        return False

    def remove_far_ep(self):
        if self.is_position_short():
            far_ep = self.entry_points.order_by('value').last()
        else:
            far_ep = self.entry_points.order_by('value').first()
        if far_ep:
            logger.debug(f"'{self}': '{far_ep}' will be deleted")
            far_ep.delete()
            return True
        return False

    def remove_near_ep(self):
        if self.is_position_short():
            near_ep = self.entry_points.order_by('value').first()
        else:
            near_ep = self.entry_points.order_by('value').last()
        if near_ep:
            logger.debug(f"'{self}': '{near_ep}' will be deleted")
            near_ep.delete()
            return True
        return False

    class Meta:
        abstract = True


class BaseSignalOrig(BaseBaseSignal):

    class Meta:
        abstract = True


class BaseSignal(BaseBaseSignal):
    status: SignalStatus
    market: 'BaseMarket'

    # Can be used by the refuse_if_busy decorator
    is_busy = models.BooleanField(
        help_text="For transactional tasks",
        default=False)

    class Meta:
        abstract = True

    @property
    def market_logic(self) -> 'BaseMarketLogic':
        return self.market.logic

    @property
    def market_exception_class(self) -> 'BaseMarketException':
        return self.market_logic.exception_class

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        logger.debug(f'Set Signal status: {self}: {self._status.upper()} -> {value.upper()}')
        BaseHistorySignal.write_in_history(signal=self, status=value)
        self._status = value


class BasePointOrig(SystemBaseModel):
    value: float

    objects = models.Manager()

    class Meta:
        abstract = True


class BasePoint(SystemBaseModel):
    value: float

    objects = models.Manager()

    class Meta:
        abstract = True

    @classmethod
    @debug_input_and_returned
    def get_min_value(cls, signal: BaseSignal) -> Optional[float]:
        min_take_profit: Optional[cls] = cls.objects.filter(signal=signal).order_by('-value').last()
        return min_take_profit.value if min_take_profit else None

    @classmethod
    @debug_input_and_returned
    def get_max_value(cls, signal: BaseSignal) -> Optional[float]:
        max_take_profit: Optional[cls] = cls.objects.filter(signal=signal).order_by('value').last()
        return max_take_profit.value if max_take_profit else None


class BaseEntryPoint(BasePoint):

    class Meta:
        abstract = True


class BaseTakeProfit(BasePoint):

    class Meta:
        abstract = True


class BaseHistorySignal(SystemBaseModelWithoutModified):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Disable update"""
        if self.pk is None:
            super().save(*args, **kwargs)

    @classmethod
    @abstractmethod
    def write_in_history(cls,
                         signal: BaseSignal,
                         status: str):
        pass
