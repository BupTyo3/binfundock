import json
import logging
import random
import os
import shutil
import time
import urllib.request
from datetime import datetime, timedelta
from sys import platform

import numpy as np
import pytesseract
import regex
from PIL import Image
from asgiref.sync import sync_to_async
from django.conf import settings
from pytesseract import image_to_string
from telethon.tl.types import User, PeerUser, PeerChannel

from apps.signal.models import SignalOrig, EntryPoint, TakeProfit
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import countdown
from utils.parse_channels.str_parser import left_numbers, check_pair, find_number_in_list
from .base_model import BaseTelegram
from .init_client import ShtClient
from ..signal.utils import MarginType

logger = logging.getLogger(__name__)

if platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

leverage_matches = ["LATHFFA", "EFA", "FFA", "EEA", "LETHEFA", "LATHEFA", "LETHFFA", "#LAT", "#LET", "HFFA"]
regexp_numbers = '\d+\.?\d+'
regexp_stop = '\d+\.?\d+$'


class SignalModel:
    def __init__(self, pair, current_price, margin_type, position, leverage, entry_points, take_profits, stop_loss,
                 msg_id, algorithm=None, is_shared=False):
        self.pair = pair
        self.current_price = current_price
        self.margin_type = margin_type
        self.position = position
        self.leverage = leverage
        self.entry_points = entry_points
        self.take_profits = take_profits
        self.stop_loss = stop_loss
        self.msg_id = msg_id
        self.algorithm = algorithm
        self.is_shared = is_shared


class Telegram(BaseTelegram):
    def __init__(self, client, *args, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)

    """
    Model of Telegram entity
    """
    name = 'Telegram'

    def is_urgent_close_position(self, message, channel_abbr):
        should_close_label = ['closing', 'closed', 'close']
        should_close = any(x in should_close_label for x in message)
        if should_close:
            if 'BTC' in message.text:
                obj = SignalOrig.objects.filter(
                    symbol='BTCUSDT', techannel__name=channel_abbr).order_by('id').last()
                if obj:
                    logger.debug(f'please close the position: {obj}')
            if 'ETH' in message.text:
                obj = SignalOrig.objects.filter(
                    symbol='ETHUSDT', techannel__name=channel_abbr).order_by('id').last()
                if obj:
                    logger.debug(f'please close the position: {obj}')
            return True
        return False

    def is_urgent_correct_position(self, message, channel_abbr):
        # TODO: add logic here as it is not relevant --->>> TRY_TO_SPOIL()
        should_move_label = ['move']
        should_move = any(x in should_move_label for x in message)
        if should_move:
            if 'BTC' in message.text:
                obj = SignalOrig.objects.filter(
                    symbol='BTCUSDT', techannel__name=channel_abbr).order_by('id').last()
                if obj:
                    logger.debug(f'please close the position: {obj}')
            if 'ETH' in message.text:
                obj = SignalOrig.objects.filter(
                    symbol='ETHUSDT', techannel__name=channel_abbr).order_by('id').last()
                if obj:
                    logger.debug(f'please close the position: {obj}')
            return True
        return False

    async def parse_tca_origin_channel(self):
        channel_abbr = 'cf_tr'
        from telethon import errors
        try:
            tca = int(conf_obj.CFTrader)

            async for message in self.client.iter_messages(tca, limit=15):
                exists = await self.is_signal_handled(message.id, channel_abbr)
                should_handle_msg = not exists
                if message.text and should_handle_msg:
                    signal = self.parse_tca_origin_message(message.text, message.id)
                    if signal[0].pair:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                                f"please check logs for '{signal[0].pair}' "
                                                                f"related to the '{channel_abbr}' algorithm: "
                                                                f"{inserted_to_db}")
                        else:
                            await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                                message.date, channel_abbr, message.id)
                    else:
                        attention_to_close = self.is_urgent_close_position(message.text, channel_abbr)
                        correct_position = self.is_urgent_correct_position(message.text, channel_abbr)
                        if attention_to_close or correct_position:
                            logger.error('A SIGNAL REQUIRES ATTENTION!')
        except errors.FloodWaitError as e:
            logger.debug(f'Have to sleep {e.seconds} seconds')
            countdown(e.seconds)

    def parse_tca_origin_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        possible_entry_label = ['Entry at: ', 'Entry : ', 'Еntry :', 'Entrу :', 'Get in  ', 'Get in : ', 'Gеt in :',
                                'Get  in : ']
        possible_take_profits_label = ['Sell at', 'Targets', 'Тargets', 'Targеts', 'Tаrgets']
        possible_take_profits_label2 = ['Take profit', 'Takе profit', 'Tаkе profit', 'Tаke profit']
        possible_stop_label = ['SL: ', 'SL : ']
        pair_label = ['Pair: ', 'Рair: ']
        pair = ''
        current_price = ''
        margin_type = MarginType.CROSSED.value
        position = None
        leverage_label = ['Leverage:', 'Levеrage:', 'Leveragе:', 'Leverаge:', 'Lеverage:']
        leverage = ''
        entries = ''
        profits = ''
        stop_loss = ['']
        signal_identification = 'CF Leverage  Trading Signal'
        for line in splitted_info:
            if line.startswith(pair_label[0]) or line.startswith(pair_label[1]):
                possible_position_info = line.split(' ')
                position_info = list(filter(None, possible_position_info))
                pair = ''.join(filter(str.isalpha, position_info[1]))
                position = ''.join(filter(str.isalpha, position_info[2]))
            if line.startswith(possible_entry_label[0]) or line.startswith(possible_entry_label[1]) \
                    or line.startswith(possible_entry_label[2]) or line.startswith(possible_entry_label[3]) \
                    or line.startswith(possible_entry_label[4]) or line.startswith(possible_entry_label[5]) \
                    or line.startswith(possible_entry_label[6]) or line.startswith(possible_entry_label[7]):
                fake_entries = line[8:]
                possible_entries = fake_entries.split('-')
                if '(' in line:
                    last_entry = possible_entries[- 1].split('(')
                    entries = left_numbers(possible_entries[:-1] + last_entry[:-1])
                else:
                    entries = left_numbers(possible_entries)
            if line.startswith(possible_take_profits_label[0]) or line.startswith(possible_take_profits_label[1]) \
                    or line.startswith(possible_take_profits_label[2]) or line.startswith(
                possible_take_profits_label[3]) \
                    or line.startswith(possible_take_profits_label[4]):
                fake_profits = line[9:]
                possible_profits = fake_profits.split('-')
                profits = left_numbers(possible_profits)
            if line.startswith(possible_take_profits_label2[0]) or line.startswith(possible_take_profits_label2[1])\
                    or line.startswith(possible_take_profits_label2[2]) or line.startswith(possible_take_profits_label2[3]):
                fake_profits = line[11:]
                possible_profits = fake_profits.split('-')
                profits = left_numbers(possible_profits)
            if line.startswith(possible_stop_label[0]) or line.startswith(possible_stop_label[1]):
                if '(' in line:
                    possible_stop_loss = line.split('(')
                    stop_loss = possible_stop_loss[0].split(' ')
                    stop_loss = left_numbers([stop_loss[1]])
                else:
                    stop_loss = line[4:]
                    stop_loss = left_numbers([stop_loss])
            if line.startswith(leverage_label[0]) or line.startswith(leverage_label[1]) \
                    or line.startswith(leverage_label[2]) or line.startswith(leverage_label[3]) \
                    or line.startswith(leverage_label[4]):
                possible_leverage = line.split(' ')
                possible_leverage = list(filter(None, possible_leverage))
                leverage = ''.join(filter(str.isdigit, possible_leverage[2]))
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss[0], message_id))
        return signals

    async def parse_margin_whale_channel(self):
        chat_id = int(conf_obj.margin_whales)
        channel_abbr = 'margin_whale'
        async for message in self.client.iter_messages(chat_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_margin_whale_message(message.text, message.id)
                if not signal[0].pair:
                    return
                inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                if inserted_to_db != 'success':
                    await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                        f"please check logs for '{signal[0].pair}' "
                                                        f"related to the '{channel_abbr}' algorithm: "
                                                        f"{inserted_to_db}")
                else:
                    await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                        message.date, channel_abbr, message.id)
                    await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                                                        message.date, channel_abbr, message.id)
                    await self.send_message_by_template(int(conf_obj.xlucrative), signal[0],
                                                        message.date, channel_abbr, message.id)

    def parse_margin_whale_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = ['ENTRY  : ', 'ENTRY : ']
        margin_label = '#MARGIN'
        goals_label = 'Target'
        stop_label = 'STOP LOSS: '
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 'Leverage : '
        entries = ''
        profits = []
        stop_loss = ''
        for line in splitted_info:
            if line.startswith(margin_label):
                fake_pair = line.split(' ')
                possible_pair = fake_pair[2]
                if 'XBT' in possible_pair:
                    pair = 'BTCUSDT'
            if line.startswith(buy_label[0]) or line.startswith(buy_label[1]):
                fake_entries = line[8:]
                possible_entries = fake_entries.split('-')
                entries = left_numbers(possible_entries)
            if line.startswith(leverage):
                possible_leverage = line.split(':')
                leverage = ''.join(filter(str.isdigit, possible_leverage[1]))
            if line.startswith(goals_label):
                possible_profits = line.split('-')
                profits.append(possible_profits[1].replace(' ', ''))
            if line.startswith(stop_label):
                stop_loss = line[11:]
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_simple_future_channel(self):
        chat_id = int(conf_obj.simple_future)
        channel_abbr = 'simple_future'
        async for message in self.client.iter_messages(chat_id, limit=15):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_simple_future_message(message.text, message.id)
                if signal[0].entry_points != '':
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                            message.date, channel_abbr, message.id)
                        await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                                                            message.date, channel_abbr, message.id)
                        await self.send_message_by_template(int(conf_obj.xlucrative), signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_simple_future_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = ['🔸Short:', '🔹Buy:']
        pair_label = '#'
        goals_label = '📈Target'
        stop_label = '📉Stop Loss:'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 'Leverage: '
        entries = ''
        profits = []
        stop_loss = ''
        for line in splitted_info:
            if line.startswith(pair_label):
                possible_pair = line.split(' ')
                pair = ''.join(filter(str.isalpha, possible_pair[0]))
            if line.startswith(leverage):
                possible_leverage = line.split(':')
                leverage = ''.join(filter(str.isdigit, possible_leverage[1]))
            if line.startswith(buy_label[0]) or line.startswith(buy_label[1]):
                if line.startswith(buy_label[0]):
                    position = 'Short'
                    possible_entry = line[7:]
                    entries = [possible_entry.replace(' ', '')]
                if line.startswith(buy_label[1]):
                    position = 'Long'
                    possible_entry = line[5:]
                    entries = [possible_entry.replace(' ', '')]
            if line.startswith(goals_label):
                possible_profits = line.split(':')
                profits.append(possible_profits[1].replace(' ', ''))
            if line.startswith(stop_label):
                stop_loss = line[11:]
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_raticoin_channel(self):
        chat_id = int(conf_obj.raticoin)
        channel_abbr = 'recoin'
        async for message in self.client.iter_messages(chat_id, limit=15):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_raticoin_message(message.text, message.id)
                if signal:
                    if signal[0].entry_points:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                                f"please check logs for '{signal[0].pair}' "
                                                                f"related to the '{channel_abbr}' algorithm: "
                                                                f"{inserted_to_db}")
                        else:
                            await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                                message.date, channel_abbr, message.id)

    def parse_raticoin_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = '(LONG)'
        short_label = '(SHORT)'
        pair_label = '#'
        entry_label = 'Entry Zone:'
        goals_label = 'Take-Profit Targets:'
        stop_label = 'Stop Targets:'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage_label = 'Leverage: '
        leverage = ''
        entries = []
        profits = []
        stop_loss = ''
        for line in splitted_info:
            if pair_label in line:
                possible_pair = line.split(' ')
                pair = ''.join(filter(str.isalpha, possible_pair[1]))
            if line.startswith(leverage_label) and 'X)' in line:
                possible_leverage = line.split(' ')
                leverage = left_numbers([possible_leverage[2]])
                leverage = leverage[0].split('.')
                leverage = leverage[0]
            if buy_label in line:
                position = 'Long'
            if short_label in line:
                position = 'Short'
        try:
            entry_index = splitted_info.index(entry_label)
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        possible_entries = splitted_info[entry_index + 1:entry_index + 2]
        for possible_entry in possible_entries:
            entry = possible_entry.split('-')
            for entr in entry:
                entries.append(entr)

        try:
            take_profits_index = splitted_info.index(goals_label)
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        possible_take_profits = splitted_info[take_profits_index + 1:take_profits_index + 6]
        for possible_take in possible_take_profits:
            take_profit = possible_take.split(' ')
            profits.append(take_profit[1].replace('-',''))

        try:
            stop_index = splitted_info.index(stop_label)
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        possible_stop = splitted_info[stop_index + 1:stop_index + 2]
        stop_loss = possible_stop[0].split(' ')
        stop_loss = stop_loss[1].replace('-', '')

        """ Take only first 4 take profits: """
        if profits: profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_lucrative_trend_channel(self):
        chat_id = int(conf_obj.lucrative_channel)
        channel_abbr = 'lucrative_trend'
        async for message in self.client.iter_messages(chat_id, limit=15):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_lucrative_trend_message(message.text)
                if signal[0].entry_points != '':
                    inserted_to_db = await self.write_signal_to_db(
                        f"{channel_abbr}__{signal[0].algorithm}", signal, message.id, signal[0].current_price)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")

    async def parse_lucrative_channel(self):
        chat_id = int(conf_obj.lucrative)
        async for message in self.client.iter_messages(chat_id, limit=15):
            signal = self.parse_lucrative_trend_message(message.text)
            is_shared = await self.is_signal_shared(signal[0].msg_id, signal[0].algorithm)
            if not is_shared:
                await self.send_shared_message(int(conf_obj.xlucrative), signal[0],
                                               signal[0].current_price, signal[0].algorithm, signal[0].msg_id)
                await self.send_shared_message(int(conf_obj.lucrative_channel), signal[0],
                                               signal[0].current_price, signal[0].algorithm, signal[0].msg_id)
                await self.send_shared_message(int(conf_obj.lucrative_trend), signal[0],
                                               signal[0].current_price, signal[0].algorithm, signal[0].msg_id)
                await self.update_shared_signal(signal[0])

    @sync_to_async
    def update_shared_signal(self, signal):
        is_updated = SignalOrig.update_shared_signal(is_shared=True, techannel_name=signal.algorithm,
                                                     outer_signal_id=signal.msg_id)

    def parse_lucrative_trend_message(self, message_text):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = 'Entry Points: '
        pair_label = 'Pair:'
        goals_label = 'Take Profits: '
        stop_label = 'Stop Loss: '
        pair = ''
        current_price = ''
        is_margin = False
        position_label = 'Position: '
        position = None
        leverage = 'Leverage: '
        entries = ''
        message_id = ''
        profits = []
        stop_loss = ''
        datetime_label = 'Time:'
        algorithm = 'Algorithm: '
        outer_id_label = 'ID: '
        for line in splitted_info:
            if line.startswith(pair_label):
                possible_pair = line.split(' ')
                pair = ''.join(filter(str.isalpha, possible_pair[1]))
            if line.startswith(position_label):
                position = line[10:]
                position = position.replace('\'', '')
            if line.startswith(leverage):
                possible_leverage = line.split(' ')
                leverage = ''.join(filter(str.isdigit, possible_leverage[1]))
            if line.startswith(buy_label):
                possible_entries = line[14:]
                entries = left_numbers(possible_entries.split(','))
            if line.startswith(goals_label):
                possible_profits = line[14:]
                profits = left_numbers(possible_profits.split(','))
            if line.startswith(stop_label):
                stop_loss = line[11:].replace('\'', '')
            if line.startswith(datetime_label):
                current_price = line[7:].replace('\'', '')
                current_price = current_price+'+02:00'
            if line.startswith(algorithm):
                algorithm = line[len(algorithm):].replace('\'', '')
            if line.startswith(outer_id_label):
                message_id = line[4:].replace('\'', '')
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id, algorithm=algorithm))
        return signals

    async def parse_china_channel(self):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()
        chat_id = int(conf_obj.chat_china_id)
        channel_abbr = 'ai'
        async for message in self.client.iter_messages(chat_id, limit=12):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg and message.photo:
                await message.download_media()
                pairs = info_getter.iterate_files(message.id)
                signal = verify_signal.get_active_pairs_info(pairs)
                if not signal:
                    return
                inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                if inserted_to_db != 'success':
                    await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                        f"please check logs for '{signal[0].pair}' "
                                                        f"related to the '{channel_abbr}' algorithm: "
                                                        f"{inserted_to_db}")
                else:
                    await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                        message.date, channel_abbr, message.id)

    async def parse_crypto_angel_channel(self):
        chat_id = int(conf_obj.crypto_angel_id)
        channel_abbr = 'crypto_passive'
        async for message in self.client.iter_messages(chat_id, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_angel_message(message.text, message.id)
                if signal[0].pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_angel_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = 'Покупаем по цене: '
        goals_label = 'Цели: '
        stop_label = 'Sl: '
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 1
        entries = ''
        profits = ''
        stop_loss = ''
        for item in splitted_info:
            if item.startswith(buy_label):
                position = 'Buy'
                pair = ''.join(filter(str.isalpha, splitted_info[0]))
        for line in splitted_info:
            if line.startswith(buy_label):
                fake_entries = line[18:]
                entries = self.handle_ca_recommend_to_array(fake_entries)
            if line.startswith(goals_label):
                fake_profits = line[6:]
                profits = self.handle_ca_recommend_to_array(fake_profits)
            if line.startswith(stop_label):
                stop_loss = line[4:]
                stop_loss = self.handle_ca_recommend_to_array(stop_loss)
                try:
                    stop_loss = f'{min(float(s) for s in stop_loss)}'
                except:
                    stop_loss = '0'
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_white_bull_channel(self):
        channel_id = int(conf_obj.white_bull)
        access_hash = -4326493311717887790
        # entity = await self.client.get_entity('@WhiteBullsVip_bot')
        channel_entity = User(id=channel_id, access_hash=access_hash)
        channel_abbr = 'white_bull'
        async for message in self.client.iter_messages(entity=channel_entity, limit=7):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_white_bull_message(message.text, message.id)
                if signal[0].entry_points and signal[0].pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_white_bull_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        pair_label = '#'
        buy_label = ['Buy: ', 'Short', 'short', 'buy']
        goals_label = ['Sell', 'sell']
        stop_label = 'SL'
        stop_label_2 = 'Sl'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 1
        entries = ''
        profits = ''
        stop_loss = ''
        for item in splitted_info:
            if item.startswith(pair_label):
                possible_pair = item.split(' ')
                pair = ''.join(filter(str.isalpha, possible_pair[0]))
                if pair.endswith('BTC'):
                    leverage = 1
        for line in splitted_info:
            line = line.strip()
            if line.startswith(buy_label[0]) or line.startswith(buy_label[1]) \
                    or line.startswith(buy_label[2]) or line.startswith(buy_label[3]):
                fake_entries = line[4:]
                possible_entries = fake_entries.split('-')
                entries = left_numbers(possible_entries)
                if line.startswith(buy_label[0]) or line.startswith(buy_label[1]):
                    position = 'Buy'
                if line.startswith(buy_label[1]) or line.startswith(buy_label[2]):
                    position = 'Short'
            if line.startswith(goals_label[0]) or line.startswith(goals_label[1]):
                fake_entries = line[5:]
                possible_take_profits = fake_entries.split('-')
                profits = left_numbers(possible_take_profits)
            if line.startswith(stop_label) or line.startswith(stop_label_2):
                possible_stop_loss = line[3:]
                stop_loss = possible_stop_loss.strip().split(' ')
                if len(stop_loss) > 1:
                    stop_loss = stop_loss[1]
                else:
                    stop_loss = stop_loss[0]
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_bull_exclusive_channel(self):
        channel_id = int(conf_obj.bull_exclusive)
        channel_abbr = 'bull_excl'
        async for message in self.client.iter_messages(channel_id, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_bull_exclusive_message(message.text, message.id)
                last_chars = signal[0].pair[-3:]
                is_btc_pair = last_chars == 'BTC'
                if signal[0].entry_points and signal[0].pair and not is_btc_pair:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                                f"please check logs for '{signal[0].pair}' "
                                                                f"related to the '{channel_abbr}' algorithm: "
                                                                f"{inserted_to_db}")
                        else:
                            await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                                message.date, channel_abbr, message.id)
                #TODO: CONSIDER TO BUILD LEVELS ON USDT PAIR ACCORDING TO THE BTC PAIR:
                # elif signal[0].entry_points and signal[0].pair and is_btc_pair:
                #     signal[0].position = 'Buy'
                #     await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                #                                         message.date, channel_abbr, message.id)
                #     await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                #                                         message.date, channel_abbr, message.id)
                #     await self.send_message_to_yourself(f"Good signal for '{signal[0].pair}'\n"
                #                                         f"Consider to process it to USDT manually")


    def parse_bull_exclusive_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = 'ENTRY'
        goals_label = 'TARGETS'
        stop_label = 'STOP LOSS'
        pair = ''
        current_price = ''
        is_margin = False
        position = 'Long'
        leverage = 5
        entries = ''
        profits = ''
        stop_loss = ''
        if '/USDT' in splitted_info[0] or '/BTC' in splitted_info[0]:
            pair_info = splitted_info[0].split(' ')
            pair = ''.join(filter(str.isalpha, pair_info[0]))
        for line in splitted_info:
            line = line.strip()
            if line.startswith(buy_label):
                fake_entries = line[5:]
                possible_entries = fake_entries.split('-')
                entries = left_numbers(possible_entries)
            if line.startswith(goals_label):
                fake_profits = line[7:]
                possible_take_profits = fake_profits.split(' - ')
                profits = left_numbers(possible_take_profits)
            if line.startswith(stop_label):
                possible_stop_losses = line[9:]
                possible_stop = possible_stop_losses.split(' ')
                stop_loss = find_number_in_list(possible_stop)

        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_crypto_zone_channel(self):
        channel_id = int(conf_obj.crypto_zone)
        channel_abbr = 'crop_zone'
        async for message in self.client.iter_messages(channel_id, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_crypto_zone_message(message.text, message.id)
                if signal[0].entry_points and signal[0].pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template('Eugene_Povetkin', signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_crypto_zone_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        is_futures_label = '💠#Binance Futures Signals'
        buy_label = ['Long/Buy', 'Buy', 'Sell']
        goals_label = 'Targets'
        stop_label = 'Stop Loss'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = random.randint(5, 10)
        entries = ''
        profits = ''
        stop_loss = ''
        if is_futures_label in splitted_info[0]:
            pair_info = splitted_info[1].split(' ')
            pair = ''.join(filter(str.isalpha, pair_info[1]))
            entries = [pair_info[2]]
            if buy_label[0] in splitted_info[1] or buy_label[1] in splitted_info[1]:
                position = 'LONG'
            elif buy_label[2] in splitted_info[1]:
                position = 'SHORT'
        for line in splitted_info:
            if line.startswith(goals_label):
                fake_profits = line[7:]
                possible_take_profits = fake_profits.split('-')
                profits = left_numbers(possible_take_profits)
            if line.startswith(stop_label):
                stop_loss = line[9:]

        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_wcse_channel(self):
        channel_id = int(conf_obj.wcse)
        channel_abbr = 'wc_se'
        # entity = await self.client.get_entity('@WCSEBot')
        access_hash = 4349140352664297866
        channel_entity = User(id=channel_id, access_hash=access_hash)
        async for message in self.client.iter_messages(entity=channel_entity, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_wcse_message(message.text, message.id)
                if signal:
                    if signal[0].entry_points and signal[0].pair:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                                f"please check logs for '{signal[0].pair}' "
                                                                f"related to the '{channel_abbr}' algorithm: "
                                                                f"{inserted_to_db}")
                        else:
                            await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                               message.date, channel_abbr, message.id)
                            await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                                                               message.date, channel_abbr, message.id)
                            await self.send_message_by_template(int(conf_obj.xlucrative), signal[0],
                                                                message.date, channel_abbr, message.id)


    def parse_wcse_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        is_new_signal = 'New Signal Created'
        is_futures_label = 'BinanceFutures'
        buy_label = '🔀 Entry Zone 🔀'
        long_label = 'Long'
        sell_label = 'Short'
        goals_label = '🔆 Exit Targets:🔆'
        stop_label = '⛔ StopLoss ⛔'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = ''
        entries = []
        profits = []
        stop_loss = ''
        if is_new_signal in splitted_info[0]:
            pair_info = splitted_info[1].split('#')
            pair = ''.join(filter(str.isalpha, pair_info[1]))
            if is_futures_label in splitted_info[2]:
                if long_label in splitted_info[2]:
                    position = 'Long'
                elif sell_label in splitted_info[2]:
                    position = 'Short'
                possible_leverage = splitted_info[2].split('(')
                leverage = left_numbers([possible_leverage[1].split(' ')[1]])
                leverage = leverage[0]
                try:
                    entry_index = splitted_info.index(buy_label)
                except ValueError as e:
                    return signals.append(SignalModel(pair, current_price, is_margin, position,
                                                      leverage, entries, profits, stop_loss, message_id))
                possible_entries = splitted_info[entry_index + 1:entry_index + 3]
                for possible_entry in possible_entries:
                    entry = possible_entry.split(' ')
                    entries.append(entry[1])

                try:
                    goals_index = splitted_info.index(goals_label)
                except ValueError as e:
                    return signals.append(SignalModel(pair, current_price, is_margin, position,
                                                      leverage, entries, profits, stop_loss, message_id))
                possible_targets = splitted_info[goals_index + 1:goals_index + 5]
                for possible_target in possible_targets:
                    target = possible_target.split(' ')
                    profits.append(target[1])

                try:
                    stop_index = splitted_info.index(stop_label)
                except ValueError as e:
                    return signals.append(SignalModel(pair, current_price, is_margin, position,
                                           leverage, entries, profits, stop_loss, message_id))
                possible_stop = splitted_info[stop_index + 1:stop_index + 2]
                stop_loss = possible_stop[0].split(' ')
                stop_loss = stop_loss[1]

                """ Take only first 4 take profits: """
                profits = profits[:4]
                signals.append(SignalModel(pair, current_price, is_margin, position,
                                           leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_server_channel(self):
        channel_id = int(conf_obj.server)
        channel_abbr = 'server'
        async for message in self.client.iter_messages(channel_id, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_server_message(message.text, message.id)
                if signal[0].entry_points and signal[0].pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")


    def parse_server_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = ['Long', 'Buy', 'Sell']
        goals_label = 'Targets'
        stop_label = 'Stop Loss'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = random.randint(5, 10)
        entries = ''
        profits = ''
        stop_loss = ''
        if buy_label[0] in splitted_info or buy_label[1] in splitted_info:
            position = 'LONG'
        elif buy_label[2] in splitted_info[1]:
            position = 'SHORT'
        for line in splitted_info:
            if line.startswith(goals_label):
                fake_profits = line[7:]
                possible_take_profits = fake_profits.split('-')
                profits = left_numbers(possible_take_profits)
            if line.startswith(stop_label):
                stop_loss = line[9:]

        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    def handle_ca_recommend_to_array(self, message_line):
        splitted_info = message_line.split('-')
        last_element = ''.join(filter(str.isdigit, splitted_info[-1]))
        splitted_info[-1] = splitted_info[-1].replace('+', '')
        if len(splitted_info[0]) == len(splitted_info[-1]):
            return splitted_info
        key_numbers = len(last_element)
        prefix = splitted_info[0][:-key_numbers]
        array = [f'{prefix}{n}' for n in splitted_info][1:]
        array.insert(0, splitted_info[0])
        return array

    async def parse_tca_channel(self, sub_type: str):
        chat_id = int
        channel_abbr = ''
        if sub_type == 'altcoin':
            channel_abbr = 'assist_altcoin'
            chat_id = int(conf_obj.tca_altcoin)
        if sub_type == 'leverage':
            channel_abbr = 'assist_leverage'
            chat_id = int(conf_obj.tca_leverage)
        async for message in self.client.iter_messages(chat_id, limit=10):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_tca_message(message.text, message.id)
                if signal:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                            message.date, channel_abbr, message.id)
                        await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                                                            message.date, channel_abbr, message.id)
                        await self.send_message_by_template(int(conf_obj.xlucrative), signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_tca_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = 'Entry at: '
        possible_take_profits = ['Sell at: ', 'Targets: ']
        stop_label = 'Stop Loss: '
        pair = 'Coin: '
        current_price = ''
        is_margin = False
        position = None
        leverage = None
        entries = ''
        profits = ''
        stop_loss = ''
        signal_identification = ['Exchange: Binance', 'Exchange: Binance Futures', 'Exchange: ByBit']
        is_signal = any(x in signal_identification for x in splitted_info)
        if not is_signal:
            return
        for line in splitted_info:
            if 'SHORT' in line:
                position = 'Sell'
            if 'LONG' in line:
                position = 'Buy'
            if line.startswith(pair):
                pair = ''.join(filter(str.isalpha, line[6:]))
            if line.startswith(buy_label):
                fake_entries = line[10:]
                possible_entries = fake_entries.split('-')
                entries = left_numbers(possible_entries)
            if line.startswith(possible_take_profits[0]) or line.startswith(possible_take_profits[1]):
                fake_profits = line[9:]
                possible_profits = fake_profits.split('-')
                profits = left_numbers(possible_profits)
            if line.startswith(stop_label):
                stop_loss = line[11:]
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    @sync_to_async
    def is_signal_handled(self, message_id, channel_abbr):
        is_exist = SignalOrig.objects.filter(outer_signal_id=message_id, techannel__name=channel_abbr).exists()
        if is_exist:
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' already exists in DB")
        return is_exist\

    @sync_to_async
    def is_signal_shared(self, message_id, channel_abbr):
        is_shared = SignalOrig.objects.filter(is_shared=True, outer_signal_id=message_id,
                                              techannel__name=channel_abbr).exists()
        return is_shared

    @sync_to_async
    def is_lucrative_signal_handled(self, pair, channel_abbr, date_time):
        date_time = date_time.split('+')
        date_time = date_time[0]
        is_exist = False
        signals_by_channel = SignalOrig.objects.filter(techannel__name=channel_abbr, symbol=pair)
        for signal in signals_by_channel:
            utc_time = signal.message_date.replace(microsecond=0, tzinfo=None)
            signal_time = utc_time + timedelta(hours=2)
            if date_time == signal_time.strftime('%Y-%m-%d %H:%M:%S'):
                is_exist = True
        if is_exist:
            logger.debug(f"Signal '{channel_abbr}' already exists in DB")
        return is_exist

    @sync_to_async
    def write_signal_to_db(self, channel_abbr: str, signal, message_id, message_date):
        if not signal[0].pair:
            return
        signal[0].pair = check_pair(signal[0].pair)
        sm_obj = SignalOrig.objects.filter(outer_signal_id=message_id, techannel__name=channel_abbr).first()
        if sm_obj:
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' already exists")
            quit()
        if signal[0].pair[-3:] == 'USD':
            signal[0].pair = signal[0].pair.replace('USD', 'USDT')
        logger.debug(f"Attempt to write into DB the following signal: "
                     f" Pair: '{signal[0].pair}'\n"
                     f" Leverage: '{signal[0].leverage}'\n"
                     f" Entry Points: '{signal[0].entry_points}'\n"
                     f" Take Profits: '{signal[0].take_profits}'\n"
                     f" Stop Loss: '{signal[0].stop_loss}'\n"
                     f" Algorithm: '{channel_abbr}'\n"
                     f" Message ID: '{message_id}'")
        try:
            SignalOrig.create_signal(techannel_name=channel_abbr,
                                     leverage=signal[0].leverage,
                                     symbol=signal[0].pair,
                                     stop_loss=signal[0].stop_loss,
                                     entry_points=signal[0].entry_points,
                                     take_profits=signal[0].take_profits,
                                     outer_signal_id=message_id,
                                     message_date=message_date,
                                     margin_type=signal[0].margin_type)
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' created successfully")
            return 'success'
        except Exception as e:
            logger.error(f"Write into DB failed: {e}")
            return e

    # send messages to yourself...
    async def send_message_to_yourself(self, message):
        await self.client.send_message('me', message)

    async def send_message_to_someone(self, name, message):
        await self.client.send_message(name, message)

    async def send_message_by_template(self, channel_name, signal, message_date, channel_abbr, message_id):
        if not signal.leverage:
            signal.leverage = 1
        message = f"Pair: '{signal.pair}'\n" \
                  f"Position: '{signal.position}'\n" \
                  f"Leverage: '{signal.leverage}'\n" \
                  f"Entry Points: '{signal.entry_points}'\n" \
                  f"Take Profits: '{signal.take_profits}'\n" \
                  f"Stop Loss: '{signal.stop_loss}'\n" \
                  f"Time: '{message_date.replace(tzinfo=None) + timedelta(hours=2)}'\n" \
                  f"Algorithm: '{channel_abbr}'\n" \
                  f"ID: '{message_id}'"
        await self.client.send_message(channel_name, message)

    async def send_shared_message(self, channel_name, signal, message_date, channel_abbr, message_id):
        message_date = message_date.split('+')
        message_date = message_date[0]
        if not signal.leverage:
            signal.leverage = 1
        message = f"Pair: '{signal.pair}'\n" \
                  f"Position: '{signal.position}'\n" \
                  f"Leverage: '{signal.leverage}'\n" \
                  f"Entry Points: '{signal.entry_points}'\n" \
                  f"Take Profits: '{signal.take_profits}'\n" \
                  f"Stop Loss: '{signal.stop_loss}'\n" \
                  f"Time: '{message_date}'\n" \
                  f"Algorithm: '{channel_abbr}'\n" \
                  f"ID: '{message_id}'"
        await self.client.send_message(channel_name, message)


#     # @client.on(events.NewMessage)
#     # async def my_event_handler(event):
#     #     if 'hello' in event.raw_text:
#     #         await event.reply('hi!')
#
#     # async def handler(event):
#     #     chat = await event.get_chat()
#     #     sender = await event.get_sender()
#     #     chat_id = event.chat_id
#     #     sender_id = event.sender_id


class ChinaImageToSignal:

    def read_image(self, image):
        self.wait_for_file(image)
        buffered_image = Image.open(image)
        text_in_image = image_to_string(buffered_image)
        splitted_info = text_in_image.splitlines()
        return splitted_info

    def find_pair(self, array):
        pair = ''
        matches = ["USDT", "USD", "BTC", "U20", "Z20"]

        for item in array:
            if any(x in item for x in matches):
                usdt_position = item.rfind('USDT')
                usd_position = item.rfind('USD')
                btc_position = item.rfind('BTC')
                utwenty_position = item.rfind('U20')
                ztwenty_position = item.rfind('Z20')
                if usd_position > 0:
                    pair = item[0:usd_position + 3]
                    pair = pair.replace('USD', 'USDT')
                if usdt_position > 0:
                    pair = item[0:usdt_position + 4]
                if btc_position > 0:
                    pair = item[0:btc_position + 3]
                if utwenty_position > 0:
                    pair_utwenty = item[0:utwenty_position + 3]
                    pair = pair_utwenty.replace("U20", "BTC")
                if ztwenty_position > 0:
                    pair_ztwenty = item[0:ztwenty_position + 3]
                    pair = pair_ztwenty.replace("Z20", "BTC")
        return ''.join(filter(str.isalpha, pair))

    def get_action(self, array):
        action = None
        for item in array:
            if item.rfind('Buy') > 0:
                action = 'Buy'
                return action
            if item.rfind('Sell') > 0:
                action = 'Sell'
                return action
            if item.rfind('LONG') > 0:
                action = 'LONG'
                return action
            if item.rfind('SHORT') > 0:
                action = 'SHORT'
                return action
            else:
                action = 'Buy'
        return action

    def get_leverage(self, array):
        leverage = None
        for item in array:
            if any(x in item for x in leverage_matches):
                if item.rfind(': ') > 0:
                    leverage = item.split(': ', 1)[-1]
                if item.rfind('= ') > 0:
                    leverage = item.split('= ', 1)[-1]
                leverage = leverage.strip()
        return leverage

    def find_entry_points(self, array, action, leverage):
        for item in array:
            result = regex.findall(regexp_numbers, item)
            is_leverage = any(x in item for x in leverage_matches)
            if len(result) >= 1 and not is_leverage:
                if not action:
                    action = 'Buy'
                if not leverage:
                    action = '{}: '.format(action, leverage)
                else:
                    action = '{} {}: '.format(action, leverage)
                # print(action, " - ".join(str(x) for x in result))
                return result

    def find_profits(self, array, entry_points):
        for item in array:
            result = regex.findall(regexp_numbers, item)
            array_equal = np.array_equal(result, entry_points)
            if len(result) >= 3 and not array_equal:
                return result

    def find_stop(self, array):
        for item in reversed(array):
            result = regex.findall(regexp_stop, item)
            if len(result) > 0:
                # print('Stop loss: ', result[0])
                return result[0]

    def get_parsed(self, image_name, message_id):
        array = self.read_image(image_name)
        position = self.get_action(array)
        leverage = self.get_leverage(array)

        pair = self.find_pair(array)
        entry_points = self.find_entry_points(array, position, leverage)
        profits = self.find_profits(array, entry_points)
        stop_loss = self.find_stop(array)
        return SignalModel(pair, None, None, position, leverage, entry_points, profits, stop_loss, message_id)

    def iterate_files(self, message_id):
        pairs = []
        directory = settings.BASE_DIR
        for filename in os.listdir(directory):
            if filename.endswith(".jpg"):
                pair_info = self.get_parsed(filename, message_id)
                pairs.append(pair_info)
                now = str(datetime.now())[:19]
                now = now.replace(":", "_")
                shutil.move(f"{directory}/{filename}",
                            f"{settings.PARSED_IMAGES_STORAGE}/" + str(now) + ".jpg")
        return pairs

    def is_locked(self, filepath):
        locked = None
        file_object = None
        if os.path.exists(filepath):
            try:
                buffer_size = 8
                # Opening file in append mode and read the first 8 characters.
                file_object = open(filepath, 'a', buffer_size)
                if file_object:
                    locked = False
            except IOError as message:
                locked = True
            finally:
                if file_object:
                    file_object.close()
        return locked

    def wait_for_file(self, filepath):
        wait_time = 1
        while self.is_locked(filepath):
            time.sleep(wait_time)


class SignalVerification:
    client = ShtClient(api_key=conf_obj.market_api_key, api_secret=conf_obj.market_api_secret)

    def get_active_pairs_info(self, pairs):
        pairs_info = []
        signals = []
        for pair_object in pairs:
            if pair_object.entry_points is None or pair_object.take_profits is None:
                return False
            price_json = ''
            pair_info_object = ''
            try:
                pair_info_object = self.client.get_symbol_info(pair_object.pair)
                # pair_info_object = self.client.get_avg_price(symbol=pair_object.pair)
                price_json = urllib.request.urlopen(
                    'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_object.pair))
            except:
                usdt_position = pair_object.pair.rfind('USDT')
                btc_position = pair_object.pair.rfind('BTC')
                if btc_position > 0:
                    pair_corrected = pair_object.pair[0: btc_position - 1:] + pair_object.pair[btc_position::]
                    price_json = urllib.request.urlopen(
                        'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_corrected))

                    pair_info_object = self.client.get_symbol_info(pair_corrected)
                if usdt_position > 0:
                    pair_corrected = pair_object.pair[0: usdt_position:] + pair_object.pair[usdt_position::]
                    if pair_corrected == 'COTVUSDT':
                        pair_corrected = 'COTIUSDT'
                    if pair_corrected == 'lOSTUSDT':
                        pair_corrected = 'IOSTUSDT'
                    if pair_corrected == 'ZILIUSDT':
                        pair_corrected = 'ZILUSDT'
                    price_json = urllib.request.urlopen(
                        'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_corrected))
                    pair_info_object = self.client.get_symbol_info(pair_corrected)

            current_pair = json.load(price_json)
            pairs_info.append(current_pair)

            entries = self.verify_entry(pair_object, current_pair)
            profits = self.verify_profits(pair_object, current_pair)
            stop_loss = self.verify_stop(pair_object, current_pair)

            logger.debug(f"Pair: {current_pair['symbol']}")
            logger.debug(f"Margin allowed: {pair_info_object['isMarginTradingAllowed']}")
            logger.debug(f"Current price: {current_pair['price']}")
            logger.debug(f"Position: {pair_object.position}")
            if pair_object.leverage:
                pair_object.leverage = pair_object.leverage.split('.')
                pair_object.leverage = ''.join(filter(str.isdigit, pair_object.leverage[0]))
                logger.debug(f"Leverage: {pair_object.leverage}")
            logger.debug(f"Entries: {entries}")
            logger.debug(f"Take profits: {profits}")
            logger.debug(f"Stop-loss: {stop_loss}")
            logger.debug('==========================================')
            signals.append(
                SignalModel(current_pair['symbol'], current_pair['price'], pair_info_object['isMarginTradingAllowed'],
                            pair_object.position, pair_object.leverage, entries, profits, stop_loss,
                            pair_object.msg_id))
        return signals

    def verify_entry(self, pair_object, current_pair_info):

        verified_entries = []
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.entry_points:
                # frac, whole = math.modf(int(price))
                # if price.startswith('0') and price.find('.') != dot_position:
                if price.find('.') != dot_position:
                    if current_pair_info['price'].startswith('0') and not price.startswith('0'):
                        price = '0' + price
                    price = price[:dot_position] + "." + price[dot_position:]
                    verified_entries.append(price)
                else:
                    verified_entries.append(price)
        return verified_entries

    def verify_profits(self, pair_object, current_pair_info):
        verified_profits = []
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.take_profits:
                # if price.find('.') > 0 and price.find('.') != dot_position:
                if price.find('.') != dot_position and '.' not in price:
                    if current_pair_info['price'].startswith('0') and not price.startswith('0'):
                        price = '0' + price
                    price = price[:dot_position] + "." + price[dot_position:]
                    verified_profits.append(price)
                else:
                    verified_profits.append(price)
        return verified_profits

    def verify_stop(self, pair_object, current_pair_info):
        dot_position = current_pair_info['price'].index('.')
        stop_loss = ''
        if dot_position:
            if pair_object.stop_loss.find('.') > 0 and pair_object.stop_loss.find('.') != dot_position:
                stop_loss = pair_object.stop_loss[:dot_position] + "." + pair_object.stop_loss[dot_position:]
            else:
                stop_loss = pair_object.stop_loss
        return stop_loss
