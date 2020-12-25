from django.db import models
from django.contrib.auth import get_user_model
from .base_model import CronTaskBase

User = get_user_model()


class CronTask(CronTaskBase):
    """
    Model of CronTask entity
    """
    _default_slip_delta_stop_loss_percentage = 0.2
    default_balance_percentage_by_signal = 3

    first_forming_enabled = models.BooleanField(default=False)
    push_job_enabled = models.BooleanField(default=False)
    pull_job_enabled = models.BooleanField(default=False)
    bought_worker_enabled = models.BooleanField(default=False)
    sold_worker_enabled = models.BooleanField(default=False)
    spoil_worker_enabled = models.BooleanField(default=False)
    close_worker_enabled = models.BooleanField(default=False)
    sell_residual_quantity_enabled = models.BooleanField(
        default=False,
        help_text="If enabled in Futures (close_worker) residual quantity will be"
                  " sold (LONG) or bought (SHORT)")
    trailing_stop_enabled = models.BooleanField(
        default=False,
        help_text="Trail SL if price has become above near EP (LONG) or lower (SHORT)")
    prices_update_worker_enabled = models.BooleanField(
        default=True,
        help_text="Allow price updates into the Pair table (prices_update_worker)")

    ai_algorithm = models.BooleanField(default=False)
    crypto_passive = models.BooleanField(default=False)
    assist_leverage = models.BooleanField(default=False)
    assist_altcoin = models.BooleanField(default=False)
    assist_origin = models.BooleanField(default=False)
    margin_whale = models.BooleanField(default=False)
    white_bull = models.BooleanField(default=False)
    simple_future = models.BooleanField(default=False)
    lucrative_recommendations = models.BooleanField(default=False)
    lucrative = models.BooleanField(default=False)
    raticoin = models.BooleanField(default=False)
    bull_exclusive = models.BooleanField(default=False)
    crypto_zone = models.BooleanField(default=False)
    wcse = models.BooleanField(default=False)
    klondike = models.BooleanField(default=False)
    server = models.BooleanField(default=False)

    balance_to_signal_perc = models.FloatField(
        default=default_balance_percentage_by_signal,
        help_text='how percent for one signal from the balance'
    )
    slip_delta_sl_perc = models.FloatField(
        default=_default_slip_delta_stop_loss_percentage,
        help_text='slip delta stop loss percentage'
    )

    objects = models.Manager()

    # def __str__(self):
    #     return f"{self.symbol}"

    def change_balance_coefficient(self, value: float):
        self.balance_to_signal_perc += value
        self.save()
