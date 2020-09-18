from abc import ABC

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import models
from model_utils.models import TimeStampedModel


class SystemBaseModel(TimeStampedModel):
    """Base model for models"""

    class Meta:
        abstract = True


class SystemBaseModelWithoutModified(TimeStampedModel):
    """Base model for models"""
    modified = None

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


def generate_increment_name_after_suffix(
        name,
        check_if_that_name_already_exists_function,
        suffix,
        max_number,
        max_length_of_result):
    """
    Create new name with incremented number in the end after suffix
    Useful for unique field instead of deleting the object we change the original name

    Example:
    name = Hello
    suffix = '__DELETED__'
    if check_if_that_name_already_exists_function returns True
    result will be
    Hello__DELETED__16
    if Hello__DELETED__15 exists, but Hello__DELETED__16 doesn't exist

    Example of check_if_that_name_already_exists_function:
    def check_if_that_name_already_exists_function(name):
        if Model.objects.filter(name=name).exists():
            return True
    :type max_length_of_result: int
    :type max_number: int
    :type suffix: str
    :type name: str
    :param check_if_that_name_already_exists_function: function
    :rtype: str or False
    """
    start_count_number = 1
    increment = 1
    new_name = f"{name}{suffix}"[-max_length_of_result:]
    for i in range(max_number):
        if check_if_that_name_already_exists_function(new_name):
            name_splitted = new_name.split(suffix)
            name = name_splitted[0]
            number = name_splitted[1]
            number = int(number) + increment if number else start_count_number
            new_name = ''.join((name, suffix, str(number)))
        else:
            break
    else:
        return False
    return new_name[-max_length_of_result:]
