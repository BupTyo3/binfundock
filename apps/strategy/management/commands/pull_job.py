import logging

from apps.crontask.utils import get_or_create_crontask
from apps.signal.models import Signal
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Update Order info from the Market'

    def add_arguments(self, parser):
        parser.add_argument('--outer_signal_id', type=int)
        parser.add_argument('--without_checking', action='store_true')
        parser.add_argument('--techannel', type=str,
                            help='Unique abbreviation of Telegram channel in lowercase')

    def handle(self, *args, **options):
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']

        if outer_signal_id:
            logger.debug(f"Info will be updated only for '{outer_signal_id}' signal")
        else:
            logger.debug(f"Info will be updated only for all signals")
        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()

        if not get_or_create_crontask().pull_job_enabled:
            return

        Signal.update_signals_info_by_api(
            outer_signal_id=outer_signal_id,
            techannel_abbr=techannel)

