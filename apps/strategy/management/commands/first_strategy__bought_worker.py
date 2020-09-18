import logging
from typing import List

from apps.signal.models import Signal
from apps.signal.utils import SignalStatus
from apps.market.models import Market
# from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Buy orders worker. If buy order has worked, we form sell orders'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--market_name', type=str, help='Market name')
        parser.add_argument('--without_checking', action='store_true')

    def handle(self, *args, **options):
        market_name = options['market_name']
        outer_signal_id = options['outer_signal_id']

        if outer_signal_id:
            logger.debug(f"Buy orders will be formed by '{outer_signal_id}' signal")
        else:
            signal_status = SignalStatus.NEW.value
            logger.debug(f"Buy orders will be formed by all {signal_status} signals")
        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()

        Signal.bought_orders_worker(outer_signal_id=outer_signal_id)

