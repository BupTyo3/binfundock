import logging
from typing import List, Optional

from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)


class Command(SystemCommand):
    help = 'Create Telegram channels'

    def add_arguments(self, parser):
        parser.add_argument('--techannel', nargs='+', type=str, help='Telegram channel: channel_abbr')

    def __create_techannel(self, techannel, append_msg=''):
        exists = Techannel.objects.filter(abbr=techannel).exists()
        if exists:
            return
        new_techannel = Techannel.create_techannel(abbr=techannel)
        self.log_success(f"Telegram channel {new_techannel} created successfully. {append_msg}")

    def _create_techannel_from_arguments(self, techannels, append_msg=''):
        if not techannels:
            return
        for techannel in techannels:
            self.__create_techannel(techannel, append_msg)

    def handle(self, *args, **options):
        techannels: Optional[List[str]] = options['techannel']
        self._create_techannel_from_arguments(techannels)

