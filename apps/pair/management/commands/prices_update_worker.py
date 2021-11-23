import logging

from apps.crontask.utils import get_or_create_crontask
from apps.pair.models import Pair
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Update last_ticker_price field into the Pair table'

    def add_arguments(self, parser):
        parser.add_argument('--without_checking', action='store_true')

    def handle(self, *args, **options):

        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()

        if not get_or_create_crontask().prices_update_worker_enabled:
            return

        Pair.last_prices_update()
