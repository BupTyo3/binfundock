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

    first_forming_enabled = models.BooleanField(default=False)
    push_job_enabled = models.BooleanField(default=False)
    pull_job_enabled = models.BooleanField(default=False)
    bought_worker_enabled = models.BooleanField(default=False)
    sold_worker_enabled = models.BooleanField(default=False)
    spoil_worker_enabled = models.BooleanField(default=False)
    close_worker_enabled = models.BooleanField(default=False)

    ai_algorithm = models.BooleanField(default=False)
    crypto_passive = models.BooleanField(default=False)
    assist_leverage = models.BooleanField(default=False)
    assist_altcoin = models.BooleanField(default=False)
    assist_origin = models.BooleanField(default=False)
    margin_whale = models.BooleanField(default=False)
    white_bull = models.BooleanField(default=False)

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

