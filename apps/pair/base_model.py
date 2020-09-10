from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict

from utils.framework.models import SystemBaseModel


class BasePair(SystemBaseModel):
    symbol: str
    min_price: float
    step_price: float
    step_quantity: float
    min_quantity: float
    min_amount: float


# typing

PairsData = Dict[str, BasePair]
