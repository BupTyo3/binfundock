import regex
import os
import time
import shutil
from datetime import datetime, timedelta
import pytesseract
import json
import urllib.request
import pytz
import logging

from asgiref.sync import sync_to_async

from apps.signal.models import Signal, EntryPoint, TakeProfit
from .base_model import BaseTelegram
from .init_client import ShtClient
from pytesseract import image_to_string
from PIL import Image
from binfun.settings import conf_obj
from utils.framework.models import SystemCommand

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
directory = 'D:/Frameworks/binfundock/'
regexp_numbers = '\d+\.?\d+'
regexp_stop = '\d+\.?\d+$'


class SignalModel:
    def __init__(self, pair, current_price, is_margin, position, leverage, entry_points, take_profits, stop_loss,
                 msg_id):
        self.pair = pair
        self.current_price = current_price
        self.is_margin = is_margin
        self.position = position
        self.leverage = leverage
        self.entry_points = entry_points
        self.take_profits = take_profits
        self.stop_loss = stop_loss
        self.msg_id = msg_id


class Telegram(BaseTelegram):
    def __init__(self, client, *args, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)

    """
    Model of Telegram entity
    """
    name = 'Telegram'

    async def parse_china_channel(self):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()
        chat_id = int(conf_obj.chat_china_id)
        async for message in self.client.iter_messages(chat_id, limit=3):
            should_handle_msg = False
            # TODO: Read from DB message id to skip handled messages
            should_handle_msg = True
            if should_handle_msg and message.photo:
                print(message.id, message.text)
                await message.download_media()
                pairs = info_getter.iterate_files(message.id)
                signal = verify_signal.get_active_pairs_info(pairs)
                await self.write_signal_to_db(signal, message.id)

    @sync_to_async
    def write_signal_to_db(self, signal, message_id):
        sm_obj = Signal.objects.filter(outer_signal_id=message_id).first()
        if sm_obj:
            logger.debug(f"Signal {message_id} already exists")
            quit()
        sm_obj = Signal.objects.create(
            symbol=signal[0].pair, stop_loss=signal[0].stop_loss, outer_signal_id=message_id)
        for entry_point in signal[0].entry_points:
            ep = EntryPoint.objects.create(signal=sm_obj, value=entry_point)
        for take_profit in signal[0].take_profits:
            tp = TakeProfit.objects.create(signal=sm_obj, value=take_profit)

        logger.debug(f"Signal {message_id} created successfully")

    async def parse_crypto_angel_channel(self):
        chat_id = int(conf_obj.crypto_angel_id)
        async for message in self.client.iter_messages(chat_id, limit=4):
            should_handle_msg = False
            # TODO: Read from DB message id to skip the handled ones
            should_handle_msg = True
            if message.text and should_handle_msg:
                # print(message.id, message.text)
                signal = self.parse_angel_message(message.text, message.id)
                if signal[0].pair:
                    await self.write_signal_to_db(signal, message.id)

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
        leverage = None
        entries = ''
        profits = ''
        stop_loss = ''
        for item in splitted_info:
            if item.startswith(buy_label):
                position = 'Buy'
                pair = ''.join(filter(str.isalpha, splitted_info[0]))
                print(pair)
        for line in splitted_info:
            if line.startswith(buy_label):
                fake_entries = line[18:]
                splitted_entries = fake_entries.split('-')
                key_numbers = len(splitted_entries[-1])
                prefix = splitted_entries[0][:-key_numbers]
                entries = [f'{prefix}{n}' for n in splitted_entries][1:]
                entries.insert(0, splitted_entries[0])
            if line.startswith(goals_label):
                fake_profits = line[6:]
                splitted_profits = fake_profits.split('-')
                key_numbers = len(splitted_profits[-1])
                prefix = splitted_profits[0][:-key_numbers]
                profits = [f'{prefix}{n}' for n in splitted_profits][1:]
                profits.insert(0, splitted_profits[0])
            if line.startswith(stop_label):
                stop_loss = line[4:]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals



#
#     # send messages to yourself...
#     async def send_message_to_yourself(self):
#         await self.client.send_message('me', 'Hello, myself!')
#
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
        matches = ["USDT", "BTC", "U20"]

        for item in array:
            if any(x in item for x in matches):
                usdt_position = item.rfind('USDT')
                btc_position = item.rfind('BTC')
                utwenty_position = item.rfind('U20')
                if usdt_position > 0:
                    pair = item[0:usdt_position + 4]
                if btc_position > 0:
                    pair = item[0:btc_position + 3]
                if utwenty_position > 0:
                    pair_utwenty = item[0:utwenty_position + 3]
                    pair = pair_utwenty.replace("U20", "BTC")
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
        matches = ["LATHFFA", "EFA", "FFA", "EEA", "LETHEFA", "LATHEFA", "LETHFFA", "#LAT", "#LET", "HFFA"]

        for item in array:
            if any(x in item for x in matches):
                if item.rfind(': ') > 0:
                    leverage = item.split(': ', 1)[-1]
                if item.rfind('= ') > 0:
                    leverage = item.split('= ', 1)[-1]
                leverage = leverage.strip()
        return leverage

    def find_entry_points(self, array, action, leverage):
        for item in array:
            result = regex.findall(regexp_numbers, item)
            if len(result) > 1:
                if not action:
                    action = 'Buy'
                if not leverage:
                    action = '{}: '.format(action, leverage)
                else:
                    action = '{} {}: '.format(action, leverage)
                # print(action, " - ".join(str(x) for x in result))
                return result

    def find_profits(self, array):
        for item in array:
            result = regex.findall(regexp_numbers, item)
            if len(result) > 3:
                # TODO: verify whether the dot is missing in each take profit (loop + conditions)
                # print('Take profits: ', result)
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
        profits = self.find_profits(array)
        stop_loss = self.find_stop(array)
        return SignalModel(pair, None, None, position, leverage, entry_points, profits, stop_loss, message_id)

    def iterate_files(self, message_id):
        pairs = []
        for filename in os.listdir(directory):
            if filename.endswith(".jpg"):
                pair_info = self.get_parsed(filename, message_id)
                pairs.append(pair_info)
                now = str(datetime.now())[:19]
                now = now.replace(":", "_")
                shutil.move("D:/Frameworks/binfundock/{}".format(filename),
                            "D:/Frameworks/binfundock/apps/telegram/media/" + str(now) + ".jpg")
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
            # TODO: Futures https: // binanceapitest.github.io / Binance - Futures - API - doc / market_data /  # symbol-price-ticker-market_data
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
                    pair_corrected = pair_object.pair[0: usdt_position - 1:] + pair_object.pair[usdt_position::]
                    price_json = urllib.request.urlopen(
                        'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_corrected))
                    pair_info_object = self.client.get_symbol_info(pair_corrected)

            current_pair = json.load(price_json)
            pairs_info.append(current_pair)

            entries = self.verify_entry(pair_object, current_pair)
            profits = self.verify_profits(pair_object, current_pair)
            stop_loss = self.verify_stop(pair_object, current_pair)

            print('Pair: {}'.format(current_pair['symbol']))
            print('Margin allowed: {}'.format(pair_info_object['isMarginTradingAllowed']))
            print('Current price: {}'.format(current_pair['price']))
            print('Position: {}'.format(pair_object.action))
            if pair_object.leverage:
                print('Leverage: {}'.format(pair_object.leverage))
            print('Entries: {}'.format(entries))
            print('Take profits: {}'.format(profits))
            print('Stop-loss: {}'.format(stop_loss))
            print('==========================================')
            signals.append(
                SignalModel(current_pair['symbol'], pair_info_object['isMarginTradingAllowed'], current_pair['price'],
                            pair_object.action, pair_object.leverage, entries, profits, stop_loss,
                            pair_object.message_id))
        return signals

    def verify_entry(self, pair_object, current_pair_info):
        import math

        verified_entries = []
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.entry_points:
                # frac, whole = math.modf(int(price))
                if price.startswith('0') and price.find('.') != dot_position:
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
                if price.find('.') > 0 and price.find('.') != dot_position:
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
