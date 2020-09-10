from django.db import models

from .base_model import Strategy


class FirstStrategy(Strategy):
    """
    Model of FirstStrategy entity
    """
    name = 'FirstStrategy'
