import logging
from typing import List

from apps.crontask.utils import get_or_create_crontask
from apps.signal.models import Signal
from apps.signal.utils import SignalStatus
from apps.market.models import Market
from apps.market.utils import get_or_create_market
# from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Form Buy orders'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--without_checking', action='store_true')
        parser.add_argument('--techannel', type=str,
                            help='Unique abbreviation of Telegram channel in lowercase')

    def handle(self, *args, **options):
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']

        if outer_signal_id and techannel:
            logger.debug(f"Buy orders will be formed by '{outer_signal_id}':'{techannel}' signal")
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

        market_obj = get_or_create_market()

        if not get_or_create_crontask().form_buy_orders_enabled:
            return

        Signal.handle_new_signals(
            market_obj,
            outer_signal_id=outer_signal_id,
            techannel_abbr=techannel)

