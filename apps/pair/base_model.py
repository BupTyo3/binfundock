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

    def __init__(self, symbol, min_price, step_price, step_quantity, min_quantity, min_amount, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = symbol
        self.min_price = min_price
        self.step_price = step_price
        self.step_quantity = step_quantity
        self.min_quantity = min_quantity
        self.min_amount = min_amount


# typing

PairsData = Dict[str, BasePair]