from abc import ABC

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import models
from model_utils.models import TimeStampedModel


class SystemBaseModel(TimeStampedModel):
    """Base model for models"""

    class Meta:
        abstract = True


class SystemCommand(BaseCommand, ABC):
    def log_success(self, message):
        self.stdout.write(self.style.SUCCESS(message))

    def log_error(self, message):
        self.stdout.write(self.style.ERROR(message))


class SingletonModel(models.Model):

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        pass

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SingletonModel, self).save(*args, **kwargs)
        self.set_cache()

    @classmethod
    def load(cls):
        if cache.get(cls.__name__) is None:
            obj, created = cls.objects.get_or_create(pk=1)
            if not created:
                obj.set_cache()
        return cache.get(cls.__name__)

    def set_cache(self):
        cache.set(self.__class__.__name__, self)
