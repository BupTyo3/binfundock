import logging

from apps.crontask.utils import get_or_create_crontask
from apps.signal.models import Signal
from apps.signal.utils import SignalStatus
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Try to Trail SL if price has become above near EP (LONG) or lower (SHORT)'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--without_checking', action='store_true')
        parser.add_argument('--techannel', type=str,
                            help='Unique abbreviation of Telegram channel in lowercase')
        parser.add_argument('--fake_price', type=float,
                            help='Fake Current price for debugging')

    def handle(self, *args, **options):
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']
        fake_price = options['fake_price']

        if outer_signal_id:
            logger.debug(f"Try to spoil '{outer_signal_id}' signal")
        else:
            signal_statuses = [
                SignalStatus.BOUGHT.value,
                SignalStatus.SOLD.value,
            ]
            logger.debug(f"Try to Trail Stop for all {signal_statuses} signals")
        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()

        if not get_or_create_crontask().trailing_stop_enabled:
            return

        Signal.trailing_stop_worker(
            outer_signal_id=outer_signal_id,
            techannel_abbr=techannel,
            fake_price=fake_price)
