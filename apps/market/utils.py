import logging

from apps.market.models import Market

logger = logging.getLogger(__name__)


def get_or_create_market() -> Market:
    market_obj, created = Market.objects.get_or_create()
    if created:
        logger.debug(f"Market '{market_obj}' has been created")
    return market_obj
