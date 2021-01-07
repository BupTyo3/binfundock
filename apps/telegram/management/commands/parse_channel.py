import logging
from random import random
import asyncio
from telethon import TelegramClient
import traceback

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
        self._client_luck = None
        self._telegram_luck = None
        super().__init__()

    def init_telegram(self, session_name):
        self._client = TelegramClient(session_name, conf_obj.api_id, conf_obj.api_hash)
        self._client.start()
        self._telegram = Telegram(self._client)

    def init_telegram_luck(self, session_name):
        self._client_luck = TelegramClient(session_name, conf_obj.api_id_luck, conf_obj.api_hash_luck)
        self._client_luck.start()
        self._telegram_luck = Telegram(self._client_luck)

    def add_arguments(self, parser):
        pass
        parser.add_argument('--channel', type=str, help='Type a channel name')

    def collect_info_from_china_channel(self):
        session_name = 'ArtificialIntelligence'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_china_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_angel_channel(self):
        session_name = 'CryptoAngel'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_crypto_angel_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_tca_altcoin_channel(self):
        session_name = 'Lucrative-altcoin'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_tca_channel('altcoin'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_tca_leverage_channel(self):
        session_name = 'Lucrative-leverage'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_tca_channel('leverage'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_tca_origin_channel(self):
        session_name = 'CFTrader'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_tca_origin_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_margin_whales_channel(self):
        session_name = 'Lucrative-Whales'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_margin_whale_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_white_bull_channel(self):
        session_name = 'White_Bull'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_white_bull_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_simple_future_channel(self):
        session_name = 'Simple-Future'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_simple_future_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_lucrative_trend_channel(self):
        session_name = 'LucrativeRecommendations'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_lucrative_trend_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_luck_channel(self):
        session_name = 'Luck'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_luck_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_raticoin_channel(self):
        session_name = 'RatiCoin'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_raticoin_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_crypto_zone_channel(self):
        session_name = 'CryptoZone'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_crypto_zone_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_bull_exclusive_channel(self):
        session_name = 'BullExclusive'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_bull_exclusive_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_wcse_channel(self):
        session_name = 'WCSE'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_wcse_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()

    def collect_info_from_klondike_channel(self):
        session_name = 'klondike'
        self.init_telegram_luck(session_name)
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_klondike_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_server_channel(self):
        session_name = 'Server'
        self.init_telegram(session_name)
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_server_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
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
        lucrative_recommendation_matches = ["recommend"]
        luck_matches = ["luck"]
        raticoin_matches = ["raticoin"]
        bull_exclusive_matches = ["bull_exclusive"]
        crypto_zone_matches = ["crypto_zone"]
        wcse_matches = ["wcse"]
        klondike_matches = ["klondike"]
        server_matches = ["server"]

        if not get_or_create_crontask().server:
            pass
        elif any(x in channel for x in server_matches):
            self.collect_info_from_server_channel()

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

        if not get_or_create_crontask().lucrative_recommendations:
            pass
        elif any(x in channel for x in lucrative_recommendation_matches):
            self.collect_info_from_lucrative_trend_channel()

        if not get_or_create_crontask().luck8414:
            pass
        elif any(x in channel for x in luck_matches):
            self.collect_info_from_luck_channel()

        if not get_or_create_crontask().raticoin:
            pass
        elif any(x in channel for x in raticoin_matches):
            self.collect_info_from_raticoin_channel()

        if not get_or_create_crontask().crypto_zone:
            pass
        elif any(x in channel for x in crypto_zone_matches):
            self.collect_info_from_crypto_zone_channel()

        if not get_or_create_crontask().bull_exclusive:
            pass
        elif any(x in channel for x in bull_exclusive_matches):
            self.collect_info_from_bull_exclusive_channel()

        if not get_or_create_crontask().wcse:
            pass
        elif any(x in channel for x in wcse_matches):
            self.collect_info_from_wcse_channel()

        if not get_or_create_crontask().klondike:
            pass
        elif any(x in channel for x in klondike_matches):
            self.collect_info_from_klondike_channel()
