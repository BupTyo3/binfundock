import logging

from abc import abstractmethod
from typing import Optional, TYPE_CHECKING, Union

from utils.framework.models import SystemBaseModel, SystemBaseModelWithoutModified
from .utils import SignalStatus

if TYPE_CHECKING:
    from apps.techannel.base_model import TechannelBase

logger = logging.getLogger(__name__)


class BaseSignal(SystemBaseModel):
    status: SignalStatus
    techannel: "TechannelBase"
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
                         status: str,
                         current_price: Optional[float] = None):
        pass
