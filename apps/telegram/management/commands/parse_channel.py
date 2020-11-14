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

    def init_telegram(self, session_name):
        self._client = TelegramClient(session_name, conf_obj.api_id, conf_obj.api_hash)
        self._client.start()
        self._telegram = Telegram(self._client)

    def add_arguments(self, parser):
        pass
        parser.add_argument('--channel', type=str, help='Type a channel name')

    def collect_info_from_china_channel(self):
        session_name = 'Lucrative-AI'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_china_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_angel_channel(self):
        session_name = 'Lucrative-Passive'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_crypto_angel_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_tca_altcoin_channel(self):
        session_name = 'Lucrative-altcoin'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_tca_channel('altcoin'))
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_tca_leverage_channel(self):
        session_name = 'Lucrative-leverage'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_tca_channel('leverage'))
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_tca_origin_channel(self):
        session_name = 'Lucrative-origin'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_tca_origin_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_margin_whales_channel(self):
        session_name = 'Lucrative-Whales'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_margin_whale_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_white_bull_channel(self):
        session_name = 'White-Bulls'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_white_bull_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def collect_info_from_simple_future_channel(self):
        session_name = 'Simple-Future'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_simple_future_channel())
        except Exception as e:
            logger.error(f'The following Error appeared during the attempt to start Telegram for {session_name}: {e}')
        finally:
            self._client.disconnect()

    def handle(self, *args, **options):
        channel = options['channel']
        china_matches = ["China", "china"]
        angel_matches = ["angel", "Angel", 'cryptoangel', 'crypto_angel', 'CryptoAngel']
        tca_altcoin_matches = ["tca_altcoin", "altcoin", "altcoins"]
        tca_leverage_matches = ["tca_leverage", "leverage"]
        tca_origin_matches = ["tca_origin", "origin"]
        margin_whale_matches = ["margin", "whale", "marginwhale", "margin_whale"]
        white_bull_matches = ["white_bulls", "whitebull", "white", "margin_whale"]
        simple_future_matches = ["simple_future"]
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

        if not get_or_create_crontask().margin_whale:
            pass
        elif any(x in channel for x in margin_whale_matches):
            self.collect_info_from_margin_whales_channel()

        if not get_or_create_crontask().white_bull:
            pass
        elif any(x in channel for x in white_bull_matches):
            self.collect_info_from_white_bull_channel()

        if not get_or_create_crontask().simple_future:
            pass
        elif any(x in channel for x in simple_future_matches):
            self.collect_info_from_simple_future_channel()
