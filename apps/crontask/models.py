from django.db import models
from django.contrib.auth import get_user_model
from .base_model import CronTaskBase

User = get_user_model()


class CronTask(CronTaskBase):
    """
    Model of CronTask entity
    """
    form_buy_orders_enabled = models.BooleanField(default=False)
    push_job_enabled = models.BooleanField(default=False)
    pull_job_enabled = models.BooleanField(default=False)
    bought_worker_enabled = models.BooleanField(default=False)
    sold_worker_enabled = models.BooleanField(default=False)
    china_channel_enabled = models.BooleanField(default=False)
    crypto_channel_enabled = models.BooleanField(default=False)
    tca_leverage_enabled = models.BooleanField(default=False)
    tca_altcoin_enabled = models.BooleanField(default=False)

    objects = models.Manager()

    # def __str__(self):
    #     return f"{self.symbol}"

