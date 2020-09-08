from django.core.management.base import BaseCommand, CommandError
from apps.signal.models import SignalModel
from apps.market.models import BiMarket, TestMarket


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('poll_ids', nargs='+', type=int)

    def handle(self, *args, **options):
        sm_obj = SignalModel('LTCUSDT', [110, 130, 150], [200, 250, 300, 350], 90, 1357)

        market_obj = TestMarket()
        # market_obj = BiMarket(conf_obj.market_api_key, conf_obj.market_api_secret)

        sm_obj.create_buy_orders(market_obj)
        sm_obj.create_sell_orders(market_obj)

        self.stdout.write(self.style.SUCCESS('Successfully closed poll "%s"' % sm_obj))

