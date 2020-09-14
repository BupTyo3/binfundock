import logging

from utils.framework.models import SystemBaseModel
from .utils import SignalStatus

logger = logging.getLogger(__name__)


class BaseSignal(SystemBaseModel):
    status: SignalStatus

    class Meta:
        abstract = True

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        logger.debug(f'Set Signal status: {self}: {self._status.upper()} -> {value.upper()}')
        self._status = value

