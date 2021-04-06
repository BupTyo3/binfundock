import logging
from telethon import TelegramClient
import traceback

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
        self._client_xy = None
        self._telegram_xy = None
        super().__init__()

    def init_telegram(self, session_name):
        self._client = TelegramClient(session_name, conf_obj.api_id, conf_obj.api_hash)
        self._client.start()
        self._telegram = Telegram(self._client)

    def init_telegram_luck(self, session_name):
        self._client_luck = TelegramClient(session_name, conf_obj.api_id_luck, conf_obj.api_hash_luck)
        self._client_luck.start()
        self._telegram_luck = Telegram(self._client_luck)

    def init_telegram_xy(self, session_name):
        self._client_xy = TelegramClient(session_name, conf_obj.api_id_xy, conf_obj.api_hash_xy)
        self._client_xy.start()
        self._telegram_xy = Telegram(self._client_xy)

    def add_arguments(self, parser):
        pass
        parser.add_argument('--channel', type=str, help='Type a channel name')

    def collect_info_from_china_channel(self):
        session_name = 'Artificial_Intelligence'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_china_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_angel_channel(self):
        session_name = 'CryptoAngel'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_crypto_angel_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_tca_altcoin_channel(self):
        session_name = 'TCA_Altcoin'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_tca_channel('altcoin'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_tca_leverage_channel(self):
        session_name = 'TCA'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_tca_channel('leverage'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_cf_trader_channel(self):
        session_name = 'CF_Trader'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_cf_trader_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_white_bull_channel(self):
        session_name = 'White_Bull'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_white_bull_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()

    def collect_info_from_lucrative_recommend_channel(self):
        session_name = 'LucrativeRecommendations'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_lucrative_recommend_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_luck_channel(self):
        session_name = 'Luck'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_luck_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_wcse_channel(self):
        session_name = 'WCSE'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_wcse_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_klondike_channel(self):
        session_name = 'klondike_margin'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_klondike_channel('margin'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_klondike_scalp_channel(self):
        session_name = 'klondike_scalp'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_klondike_channel('scalp'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_klondike_altcoin_channel(self):
        session_name = 'klondike_altcoin'
        self.init_telegram_luck(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client_luck:
                self._client_luck.loop.run_until_complete(self._telegram_luck.parse_klondike_channel('altcoin'))
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client_luck.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_server_channel(self):
        session_name = 'Server'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_server_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_fsvzo_channel(self):
        session_name = 'fsvzo'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_fsvzo_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_margin_whales_channel(self):
        session_name = 'MarginWhales'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_margin_whale_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def collect_info_from_crypto_futures_channel(self):
        session_name = 'CryptoFutures'
        self.init_telegram(session_name)
        logger.debug(f'Session {session_name} initialized')
        try:
            with self._client:
                self._client.loop.run_until_complete(self._telegram.parse_crypto_futures_channel())
        except Exception as e:
            logger.error(f'Session {session_name} ERROR: {e}')
            traceback.print_exc()
        finally:
            self._client.disconnect()
            logger.debug(f'Session {session_name} disconnected')

    def handle(self, *args, **options):
        channel = options['channel']
        china_matches = ["China", "china"]
        angel_matches = ["angel", "Angel", 'cryptoangel', 'crypto_angel', 'CryptoAngel']
        crypto_futures_matches = ["crypto_futures"]
        tca_altcoin_matches = ["tca_altcoin", "altcoin", "altcoins"]
        tca_leverage_matches = ["tca_leverage", "leverage"]
        tca_origin_matches = ["tca_origin", "origin"]
        white_bull_matches = ["white_bulls", "whitebull", "white"]
        lucrative_recommendation_matches = ["recommend"]
        luck_matches = ["luck"]
        wcse_matches = ["wcse"]
        klondike_margin_matches = ["klondike_margin"]
        klondike_scalp_matches = ["klondike_scalp"]
        klondike_altcoin_matches = ["klondike_altcoin"]
        margin_whale_matches = ["marginwhale"]
        server_matches = ["server"]
        fsvzo_matches = ["fsvzo"]

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
            self.collect_info_from_cf_trader_channel()

        if not get_or_create_crontask().white_bull:
            pass
        elif any(x in channel for x in white_bull_matches):
            self.collect_info_from_white_bull_channel()

        if not get_or_create_crontask().lucrative_recommendations:
            pass
        elif any(x in channel for x in lucrative_recommendation_matches):
            self.collect_info_from_lucrative_recommend_channel()

        if not get_or_create_crontask().luck8414:
            pass
        elif any(x in channel for x in luck_matches):
            # self.collect_info_from_luck_channel()
            pass
        
        if not get_or_create_crontask().wcse:
            pass
        elif any(x in channel for x in wcse_matches):
            self.collect_info_from_wcse_channel()

        if not get_or_create_crontask().klondike_margin:
            pass
        elif any(x in channel for x in klondike_margin_matches):
            self.collect_info_from_klondike_channel()

        if not get_or_create_crontask().klondike_scalp:
            pass
        elif any(x in channel for x in klondike_scalp_matches):
            self.collect_info_from_klondike_scalp_channel()

        if not get_or_create_crontask().klondike_altcoin:
            pass
        elif any(x in channel for x in klondike_altcoin_matches):
            self.collect_info_from_klondike_altcoin_channel()

        if not get_or_create_crontask().margin_whale:
            pass
        elif any(x in channel for x in margin_whale_matches):
            self.collect_info_from_margin_whales_channel()

        if not get_or_create_crontask().crypto_futures:
            pass
        elif any(x in channel for x in crypto_futures_matches):
            self.collect_info_from_crypto_futures_channel()

        if not get_or_create_crontask().fsvzo:
            pass
        elif any(x in channel for x in fsvzo_matches):
            self.collect_info_from_fsvzo_channel()
