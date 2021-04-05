import logging
import copy

from typing import (
    Optional, List, Set,
    Callable,
    TYPE_CHECKING
)

from django.db import models
from .base_model import TechannelBase
from apps.crontask.models import CronTask
from utils.framework.models import (
    left_only_numbers_letters_underscores,
)
from tools.tools import gen_short_uuid

if TYPE_CHECKING:
    from apps.market.base_model import BaseMarket

logger = logging.getLogger(__name__)


class Techannel(TechannelBase):
    """
    Model of Telegram channel entity
    """
    _default_balance_percentage_by_signal = 0.5

    name = models.CharField(max_length=50,
                            unique=True,
                            help_text='unique name. Lowercase alphanumeric and underscores')
    abbr = models.CharField(max_length=6,
                            unique=True,
                            help_text='unique short abbreviation for custom_order_id')
    auto_bi_futures = models.BooleanField(
        default=False,
        help_text='Auto creating into Signal for BiFutures Market',
    )
    auto_bi_spot = models.BooleanField(
        default=False,
        help_text='Auto creating into Signal for BiSpot Market',
    )

    auto_trailing_stop = models.BooleanField(
        default=False,
        help_text="Auto add trailing_stop_enabled for new Signals. It works if one "
                  "of the next flags is set: auto_bi_futures, auto_bi_spot",
    )

    balance_to_signal_perc = models.FloatField(
        default=CronTask.default_balance_percentage_by_signal,
        help_text='percent for one signal from the balance'
    )

    leverage_boost = models.PositiveIntegerField(
        default=0,
        help_text='The number to add to the recommended leverage'
    )

    objects = models.Manager()

    def __str__(self):
        return f"{self.pk}:{self.abbr}"

    def save(self, *args, **kwargs):
        name = self.name.replace(' ', '_').replace('-', '_').lower()
        name = left_only_numbers_letters_underscores(name)
        if not self.abbr:
            self.abbr = self._get_unique_abbr(name)
        self.name = name
        return super(Techannel, self).save(*args, **kwargs)

    @classmethod
    def _get_unique_abbr(cls, abbr):
        pre_abbr = ''.join([i[:2] for i in abbr.split('_')])[:4]
        new_abbr = copy.copy(pre_abbr)
        max_number = 99
        for i in range(max_number):
            trailing_number = '' if i == 0 else i
            new_abbr = f"{pre_abbr}{trailing_number}"
            if not Techannel.objects.filter(abbr=new_abbr).exists():
                break
        return new_abbr

    @classmethod
    def create_techannel(cls, abbr: str, name='') -> 'Techannel':
        techannel = cls.objects.create(name=name, abbr=abbr)
        logger.debug(f"Telegram channel '{techannel}' has been created successfully")
        return techannel

    def get_bi_futures_market_if_auto_enabled(self) -> Optional['BaseMarket']:
        """
        Futures market
        Get a market, corresponding to the flag:
        auto creating Signal by SignalOrig
        """
        from apps.market.models import get_or_create_futures_market
        return get_or_create_futures_market() if self.auto_bi_futures else None

    def get_bi_spot_market_if_auto_enabled(self) -> Optional['BaseMarket']:
        """
        Spot market
        Get a market, corresponding to the flag:
        auto creating Signal by SignalOrig
        """
        from apps.market.models import get_or_create_market
        return get_or_create_market() if self.auto_bi_spot else None

    def get_market_auto_methods(self) -> List[Callable]:
        """
        Get list of methods to create markets
         to auto create into Signal
         after creating SignalOrig
        """
        return [
            self.get_bi_futures_market_if_auto_enabled,
            self.get_bi_spot_market_if_auto_enabled,
        ]
