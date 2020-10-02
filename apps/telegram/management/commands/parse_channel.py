import logging

from telethon import TelegramClient

from apps.signal.models import Signal
from apps.telegram.models import Telegram
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand
from apps.crontask.utils import get_or_create_crontask

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Closes the specified poll for voting'
    client = TelegramClient('lucrativetrend', conf_obj.api_id, conf_obj.api_hash)
    client.start()
    telegram = Telegram(client)

    def add_arguments(self, parser):
        pass
        parser.add_argument('--channel', type=str, help='Type a channel name')

    def collect_info_from_china_channel(self):
        with self.client:
            self.client.loop.run_until_complete(self.telegram.parse_china_channel())

    def collect_info_from_angel_channel(self):
        with self.client:
            self.client.loop.run_until_complete(self.telegram.parse_crypto_angel_channel())

    def collect_info_from_tca_altcoin_channel(self):
        with self.client:
            self.client.loop.run_until_complete(self.telegram.parse_tca_channel('altcoin'))

    def collect_info_from_tca_leverage_channel(self):
        with self.client:
            self.client.loop.run_until_complete(self.telegram.parse_tca_channel('leverage'))

    def collect_info_from_tca_origin_channel(self):
        with self.client:
            self.client.loop.run_until_complete(self.telegram.parse_tca_origin_channel())

    def handle(self, *args, **options):
        channel = options['channel']
        china_matches = ["China", "china"]
        angel_matches = ["angel", "Angel", 'cryptoangel', 'crypto_angel', 'CryptoAngel']
        tca_altcoin_matches = ["tca_altcoin", "altcoin", "altcoins"]
        tca_leverage_matches = ["tca_leverage", "leverage"]
        tca_origin_matches = ["tca_origin", "origin"]
        if not get_or_create_crontask().ai_algorithm:
            pass
        elif any(x in channel for x in china_matches):
            self.collect_info_from_china_channel()
        if not get_or_create_crontask().crypto_passive:
            pass
        elif any(x in channel for x in angel_matches):
            self.collect_info_from_angel_channel()
        if not get_or_create_crontask().assist_altcoin:
            pass
        elif any(x in channel for x in tca_altcoin_matches):
            self.collect_info_from_tca_altcoin_channel()
        if not get_or_create_crontask().assist_leverage:
            pass
        elif any(x in channel for x in tca_leverage_matches):
            self.collect_info_from_tca_leverage_channel()
        if not get_or_create_crontask().assist_origin:
            pass
        elif any(x in channel for x in tca_origin_matches):
            self.collect_info_from_tca_origin_channel()

