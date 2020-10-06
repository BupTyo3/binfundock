import logging
from random import random
import asyncio
from telethon import TelegramClient

from apps.signal.models import Signal
from apps.telegram.models import Telegram
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand
from apps.crontask.utils import get_or_create_crontask

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    def __init__(self):
        self._client = None
        self._telegram = None
        super().__init__()

    def init_telegram(self):
        self._client = TelegramClient(f'lucrativetrend-{random()}', conf_obj.api_id, conf_obj.api_hash)
        self._client.start()
        self._telegram = Telegram(self._client)

    def add_arguments(self, parser):
        pass
        parser.add_argument('--channel', type=str, help='Type a channel name')

    def collect_info_from_china_channel(self):
        self.init_telegram()
        with self._client:
            self._client.loop.run_until_complete(self._telegram.parse_china_channel())

    def collect_info_from_angel_channel(self):
        self.init_telegram()
        with self._client:
            self._client.loop.run_until_complete(self._telegram.parse_crypto_angel_channel())

    def collect_info_from_tca_altcoin_channel(self):
        self.init_telegram()
        with self._client:
            self._client.loop.run_until_complete(self._telegram.parse_tca_channel('altcoin'))

    def collect_info_from_tca_leverage_channel(self):
        self.init_telegram()
        with self._client:
            self._client.loop.run_until_complete(self._telegram.parse_tca_channel('leverage'))

    def collect_info_from_tca_origin_channel(self):
        self.init_telegram()
        with self._client:
            self._client.loop.run_until_complete(self._telegram.parse_tca_origin_channel())

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

