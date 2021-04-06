import logging

from asgiref.sync import sync_to_async
from django.db import models, transaction
from django.contrib.auth import get_user_model
from .base_model import BasePair

User = get_user_model()
logger = logging.getLogger(__name__)


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

    last_ticker_price = models.FloatField(
        default=0,
        help_text="This price may be a little outdated")

    objects = models.Manager()

    def __str__(self):
        return f"{self.symbol}:{self.market}"

    @classmethod
    def get_pair(cls, symbol: str, market: Market):
        pair = cls.objects.filter(symbol=symbol, market=market).first()
        return pair

    @classmethod
    @sync_to_async
    def get_async_pair(cls, symbol: str, market: Market):
        pair = cls.objects.filter(symbol=symbol, market=market).first()
        return pair

    @classmethod
    def last_prices_update(cls):
        from apps.market.models import get_or_create_market
        ticker_prices = get_or_create_market().logic.get_ticker_current_prices()
        ticker_prices_transformed = {
            ticker_price['symbol']: float(ticker_price['price']) for ticker_price in ticker_prices
        }
        objs = []
        for pair in cls.objects.all():
            try:
                pair.last_ticker_price = ticker_prices_transformed[pair.symbol]
                objs.append(pair)
            except KeyError as ex:
                logger.warning(f"Price for Pair '{pair}' not received. Ex: '{ex}'")
        cls.objects.bulk_update(objs, ['last_ticker_price'])
