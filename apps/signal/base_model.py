import logging

from abc import abstractmethod
from typing import Optional, TYPE_CHECKING, Union

from django.db import models

from utils.framework.models import SystemBaseModel, SystemBaseModelWithoutModified
from tools.tools import debug_input_and_returned
from .utils import SignalStatus

if TYPE_CHECKING:
    from apps.techannel.base_model import TechannelBase

logger = logging.getLogger(__name__)


class BaseSignalOrig(SystemBaseModel):
    techannel: 'TechannelBase'
    outer_signal_id: int

    class Meta:
        abstract = True


class BaseSignal(SystemBaseModel):
    status: SignalStatus
    techannel: 'TechannelBase'
    outer_signal_id: int

    class Meta:
        abstract = True

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
