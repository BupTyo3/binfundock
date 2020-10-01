from django.db import models
from django.contrib.auth import get_user_model
from .base_model import CronTaskBase

User = get_user_model()


class CronTask(CronTaskBase):
    """
    Model of CronTask entity
    """
    _default_slip_delta_stop_loss_percentage = 0.2
    _default_balance_percentage_by_signal = 0

    form_buy_orders_enabled = models.BooleanField(default=False)
    push_job_enabled = models.BooleanField(default=False)
    pull_job_enabled = models.BooleanField(default=False)
    bought_worker_enabled = models.BooleanField(default=False)
    sold_worker_enabled = models.BooleanField(default=False)
    china_channel_enabled = models.BooleanField(default=False)
    crypto_channel_enabled = models.BooleanField(default=False)
    tca_leverage_enabled = models.BooleanField(default=False)
    tca_altcoin_enabled = models.BooleanField(default=False)
    tca_origin_enabled = models.BooleanField(default=False)
    balance_to_signal_perc = models.FloatField(
        default=_default_balance_percentage_by_signal,
        help_text='how percent for one signal from the balance'
    )
    slip_delta_sl_perc = models.FloatField(
        default=_default_slip_delta_stop_loss_percentage,
        help_text='slip delta stop loss percentage'
    )

    objects = models.Manager()

    # def __str__(self):
    #     return f"{self.symbol}"

