import logging

from celery import shared_task, group
from celery.schedules import crontab

from .models import Pair
from apps.crontask.utils import get_or_create_crontask

logger = logging.getLogger(__name__)


# UPDATE PRICES
@shared_task(ignore_result=True)
def update_prices_task():
    if not get_or_create_crontask().prices_update_worker_enabled:
        return
    Pair.last_prices_update()


