import re
from abc import ABC
from typing import Optional, Union

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


class BinfunError(ValueError):
    pass


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


def get_trailing_number(s: str) -> Optional[int]:
    """
    Get trailing number from the string
    "hello45" -> 45
    "hello" -> None
    """
    m = re.search(r'\d+$', s)
    return int(m.group()) if m else None


def get_leading_number(s: str) -> Optional[int]:
    """
    Get leading number from the string
    "45hello" -> 45
    "hello" -> None
    """
    m = re.search(r'^\d+', s)
    return int(m.group()) if m else None


def left_only_numbers_letters_underscores(s: str) -> str:
    """
    Convert:
    "Hello world_18!!!" -> "Hello_world_18"
    """
    return re.sub(r'[\W]+', '', s)


def get_increased_leading_number(string: str) -> str:
    """
    Convert:
    "45hello" -> "46hello"
    "hello" -> "0hello"
    "0hello" -> "1hello"
    """
    leading_number = get_leading_number(string)
    new_main_part = string
    if leading_number is not None:
        new_leading_number = leading_number + 1
        new_main_part = string.lstrip(str(leading_number))
    else:
        new_leading_number = 0
    return f"{new_leading_number}{new_main_part}"


def get_increased_trailing_number(string: str, default: Union[None, int, str]) -> str:
    """
    Convert:
    "hello45" -> "hello46"
    "hello" -> "hello0"
    "hello0" -> "hello1"
    """
    trailing_number = get_trailing_number(string)
    new_main_part = string
    if trailing_number is not None:
        new_trailing_number = trailing_number + 1
        new_main_part = string.rstrip(str(trailing_number))
    else:
        new_trailing_number = 0
    new_trailing_number = default if default or default == 0 else new_trailing_number
    return f"{new_main_part}{new_trailing_number}"
