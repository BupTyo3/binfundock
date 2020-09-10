from django.db import models
from django.contrib.auth import get_user_model
from .base_model import BasePair

User = get_user_model()


class Pair(BasePair):
    """
    Model of Pair entity
    """
    from apps.market.models import Market
    market = models.ForeignKey(to=Market,
                               related_name='pairs',
                               on_delete=models.CASCADE)
    symbol = models.CharField(max_length=24)
    min_price = models.FloatField()
    step_price = models.FloatField()
    step_quantity = models.FloatField()
    min_quantity = models.FloatField()
    min_amount = models.FloatField()

    def __str__(self):
        return f"{self.symbol}"

