from typing import List

from apps.signal.models import SignalModel
from apps.market.models import BiMarket, TestMarket
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand


class Command(SystemCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('pair', type=str, help='Pair of coins')
        parser.add_argument('--entry_points', nargs='+', type=float, required=True, help='Entry points values')
        parser.add_argument('--take_profits', nargs='+', type=float, required=True, help='Take profits values')
        parser.add_argument('--stop_loss', type=float, required=True, help='Stop loss value')
        parser.add_argument('--signal_id', type=int, required=True)
        parser.add_argument('--market_name', type=str, help='Market name')
        parser.add_argument('--without_checking', action='store_true')

    def check_signal_input(self, pair: str, entry_points: List[float],
                           take_profits: List[float], stop_loss: float, signal_id: int):
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
        pair = options['pair']
        market_name = options['market_name']
        entry_points = options['entry_points']
        take_profits = options['take_profits']
        stop_loss = options['stop_loss']
        signal_id = options['signal_id']
        sm_obj = SignalModel(pair=pair,
                             entry_points=entry_points,
                             take_profits=take_profits,
                             stop_loss=stop_loss,
                             signal_id=signal_id)
        print(sm_obj.__dict__)
        self.check_signal_input(pair, entry_points, take_profits, stop_loss, signal_id)
        if not options['without_checking']:
            key = input('y/n: ')
            if key.lower() in ['y', 'yes']:
                print('You are agreed! Continue...')
            else:
                print("You typed No - The End")
                quit()

        if market_name == BiMarket.name:
            market_obj = BiMarket(conf_obj.market_api_key, conf_obj.market_api_secret)
        else:
            market_obj = TestMarket()

        sm_obj.create_buy_orders(market_obj)
        sm_obj.create_sell_orders(market_obj)

        self.log_success('The command is done')

