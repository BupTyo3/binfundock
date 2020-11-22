import logging
from typing import List

from apps.crontask.utils import get_or_create_crontask
from apps.signal.models import Signal
from apps.signal.utils import SignalStatus
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Form Buy orders'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--without_checking', action='store_true')
        parser.add_argument('--techannel', type=str,
                            help='Unique abbreviation of Telegram channel in lowercase')
        parser.add_argument('--fake_balance', type=float,
                            help='Fake balance for debugging')

    def handle(self, *args, **options):
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']
        fake_balance = options['fake_balance']

        if outer_signal_id and techannel:
            logger.debug(f"FIRST_FORMING for '{outer_signal_id}':'{techannel}' signal")
        else:
            signal_status = SignalStatus.NEW.value
            logger.debug(f"FIRST_FORMING for all {signal_status} signals")

        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()

        if not get_or_create_crontask().first_forming_enabled:
            return

        Signal.handle_new_signals(
            outer_signal_id=outer_signal_id,
            techannel_abbr=techannel,
            fake_balance=fake_balance)

