from abc import ABC

from model_utils.models import TimeStampedModel
from django.core.management.base import BaseCommand


class SystemBaseModel(TimeStampedModel):
    """Base model for models"""

    class Meta:
        abstract = True


class SystemCommand(BaseCommand, ABC):
    def log_success(self, message):
        self.stdout.write(self.style.SUCCESS(message))

    def log_error(self, message):
        self.stdout.write(self.style.ERROR(message))

