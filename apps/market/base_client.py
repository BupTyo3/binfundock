import logging

from abc import ABC
from typing import Callable

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    client: Callable
    api_key: str
    api_secret: str

    @classmethod
    def activate_connection(cls):
        logger.debug("Opening connection .....")
        return cls.client(cls.api_key, cls.api_secret)
