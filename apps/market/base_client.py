import logging

from abc import ABC, abstractmethod
from typing import Callable

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """
    BaseClient class.
    To create real class use multiple inheritance, e.g.
    class BiClient(client.Client, BaseClient):
        client = client.Client

    """
    api_client_class: Callable
    api_key: str
    api_secret: str

    @property
    @abstractmethod
    def api_key(self) -> str:
        pass

    @property
    @abstractmethod
    def api_secret(self) -> str:
        pass

    @classmethod
    def activate_connection(cls):
        logger.debug("Opening connection .....")
        return cls.api_client_class(cls.api_key, cls.api_secret)
