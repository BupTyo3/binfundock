import logging
from typing import List

from apps.signal.models import SignalOrig
# from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('symbol', type=str, help='Pair of coins')
        parser.add_argument('--entry_points', nargs='+', type=float, required=True, help='Entry points values')
        parser.add_argument('--take_profits', nargs='+', type=float, required=True, help='Take profits values')
        parser.add_argument('--stop_loss', type=float, required=True, help='Stop loss value')
        parser.add_argument('--leverage', type=int, default=1, help='Leverage for futures')
        parser.add_argument('--techannel', type=str, required=True,
                            help='Unique abbreviation of Telegram channel in lowercase')
        parser.add_argument('--outer_signal_id', type=int, required=True)
        parser.add_argument('--market_name', type=str, help='Market name')
        parser.add_argument('--without_checking', action='store_true')

    def check_signal_input(self, entry_points: List[float],
                           take_profits: List[float], stop_loss: float):
        error_flag = False
        if sorted(entry_points) != entry_points:
            self.log_error('Wrong order of entry_points')
            error_flag = True
        if sorted(take_profits) != take_profits:
            self.log_error('Wrong order of take_profits')
            error_flag = True
        if stop_loss > min(entry_points):
            self.log_error('Stop loss > entry_points')
            error_flag = True
        if max(entry_points) >= min(take_profits):
            self.log_error('entry_points > take_profits')
            error_flag = True
        if error_flag:
            self.log_error('Wrong Signal!!!')
            quit()

    def handle(self, *args, **options):
        # sm_obj = SignalModel('LTCUSDT', [110, 130, 150], [200, 250, 300, 350], 90, 1357)
        # sm_obj = SignalModel('ZECETH', [0.1600, 0.1550, 0.1500], [0.17, 0.172, ], 0.166, 1357)
        symbol = options['symbol']
        entry_points = options['entry_points']
        take_profits = options['take_profits']
        stop_loss = options['stop_loss']
        leverage = options['leverage']
        outer_signal_id = options['outer_signal_id']
        techannel = options['techannel']

        # self.check_signal_input(entry_points, take_profits, stop_loss)
        logger.debug(f"Signal:{symbol}:EntryPoints:{entry_points}:"
                     f"TakeProfits:{take_profits}:StopLoss:{stop_loss}"
                     f":SignalId:{outer_signal_id}")
        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                logger.debug('You are agreed! Continue...')
            else:
                logger.debug("You typed No - The End")
                quit()
        sm_obj = SignalOrig.create_signal(techannel_name=techannel,
                                          symbol=symbol,
                                          stop_loss=stop_loss,
                                          entry_points=entry_points,
                                          take_profits=take_profits,
                                          leverage=leverage,
                                          outer_signal_id=outer_signal_id)

        if sm_obj:
            self.log_success(f"Signal '{outer_signal_id}':'{techannel}' created successfully")
        else:
            self.log_error(f"Signal '{outer_signal_id}':'{techannel}' has not been created")
