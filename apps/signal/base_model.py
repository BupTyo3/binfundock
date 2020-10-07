import logging

from typing import Optional, TYPE_CHECKING

from utils.framework.models import SystemBaseModel
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
        self._status = value

