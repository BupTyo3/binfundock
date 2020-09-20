import logging

from telethon import TelegramClient

from apps.signal.models import Signal
from apps.telegram.models import Telegram
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

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

    def handle(self, *args, **options):
        channel = options['channel']
        china_matches = ["China", "china", 'AI', 'ai']
        angel_matches = ["angel", "Angel", 'cryptoangel', 'CryptoAngel']
        if any(x in channel for x in china_matches):
            self.collect_info_from_china_channel()
        if any(x in channel for x in angel_matches):
            self.collect_info_from_angel_channel()

