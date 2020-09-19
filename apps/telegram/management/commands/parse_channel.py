import logging

from telethon import TelegramClient
from apps.telegram.models import Telegram
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        pass

    def collect_info_from_channel(self):
        client = TelegramClient('lucrativetrend', conf_obj.api_id, conf_obj.api_hash)
        client.start()
        telegram = Telegram(client)
        with client:
            client.loop.run_until_complete(telegram.parse_china_channel())

    def handle(self, *args, **options):
        self.collect_info_from_channel()

