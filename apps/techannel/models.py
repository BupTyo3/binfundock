import logging

from django.db import models
from .base_model import TechannelBase

logger = logging.getLogger(__name__)


class Techannel(TechannelBase):
    """
    Model of Telegram channel entity
    """
    abbr = models.CharField(max_length=15,
                            unique=True,
                            help_text='unique abbreviation')
    name = models.CharField(max_length=100,
                            blank=True)
    abbr: str
    name: str

    def __str__(self):
        return f"{self.pk}:{self.name}:{self.abbr}"

    def save(self, *args, **kwargs):
        self.abbr = self.abbr.lower()
        return super(Techannel, self).save(*args, **kwargs)

    @classmethod
    def create_techannel(cls, abbr: str, name='') -> 'Techannel':
        techannel = cls.objects.create(name=name, abbr=abbr)
        logger.debug(f"Telegram channel '{techannel}' has been created successfully")
        return techannel
