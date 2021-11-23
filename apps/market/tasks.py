import logging

from celery import shared_task

from .models import get_or_create_market, get_or_create_futures_market

logger = logging.getLogger(__name__)


# UPDATE PAIRS INFO API
@shared_task(ignore_result=True)
def update_pairs_info_api_task():
    get_or_create_market().logic.update_pairs_info_api()
    get_or_create_futures_market().logic.update_pairs_info_api()
