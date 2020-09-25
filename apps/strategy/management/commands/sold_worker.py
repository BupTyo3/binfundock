import logging

from apps.crontask.utils import get_or_create_crontask
from apps.signal.models import Signal
from apps.signal.utils import SignalStatus
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Buy orders worker. If buy order has worked, we form sell orders'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--without_checking', action='store_true')
        parser.add_argument('--techannel', type=str,
                            help='Unique abbreviation of Telegram channel in lowercase')

    def handle(self, *args, **options):
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']

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

        if not get_or_create_crontask().sold_worker_enabled:
            return

        Signal.sold_orders_worker(
            outer_signal_id=outer_signal_id,
            techannel_abbr=techannel)

