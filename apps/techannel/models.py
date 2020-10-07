import logging
import copy

from django.db import models
from .base_model import TechannelBase
from utils.framework.models import (
    left_only_numbers_letters_underscores,
)
from tools.tools import gen_short_uuid

logger = logging.getLogger(__name__)


class Techannel(TechannelBase):
    """
    Model of Telegram channel entity
    """
    name = models.CharField(max_length=50,
                            unique=True,
                            help_text='unique name. Lowercase alphanumeric and underscores')
    abbr = models.CharField(max_length=6,
                            unique=True,
                            help_text='unique short abbreviation for custom_order_id')

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
