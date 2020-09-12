import regex
import os
import time
import shutil
import datetime
import pytesseract

from .init_client import ShtClient
from pytesseract import image_to_string
from PIL import Image
from telethon import TelegramClient, events
from binfun.settings import conf_obj
import json
import urllib.request

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
directory = 'D:/Frameworks/LucrativeTrend'
regexp_numbers = '\d+\.?\d+'
regexp_stop = '\d+\.?\d+$'
file_name = 'apps/telegram/message_id.txt'


def main():
    client = TelegramClient('lucrativetrend', conf_obj.api_id, conf_obj.api_hash)
    client.start()
    telegram = Telegram(client, conf_obj.chat_china_id)
    with client:
        client.loop.run_until_complete(telegram.main(client))


main()


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


class PairModel:
    def __init__(self, pair, action, leverage, entry_points, take_profits, stop_loss, message_id):
        self.action = action
        self.pair = pair
        self.leverage = leverage
        self.entry_points = entry_points
        self.take_profits = take_profits
        self.stop_loss = stop_loss
        self.message_id = message_id


class Telegram:
    """
    Model of Telegram entity
    """
    name = 'Telegram'

    def __init__(self, client, chat_id):
        self.client = client
        self.chat_id = chat_id

    async def main(self, client):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()

        async for message in client.iter_messages(self.chat_id, limit=2):
            should_handle_msg = False
            info_from_file = open(file_name).read()
            if ',{},'.format(message.id) not in info_from_file:
                should_handle_msg = True
            if should_handle_msg and message.photo:
                print(message.id, message.text)
                # print(message.)
                await message.download_media()
                pairs = info_getter.iterate_files(message.id)
                verify_signal.get_active_pairs_info(pairs)
                # if is_signal_obtained:
                file = open(file_name, 'a+')
                file.write(',{},'.format(message.id))
                file.close()

    # send messages to yourself...
    async def send_message_to_yourself(self):
        await self.client.send_message('me', 'Hello, myself!')

    # @client.on(events.NewMessage)
    # async def my_event_handler(event):
    #     if 'hello' in event.raw_text:
    #         await event.reply('hi!')

    # async def handler(event):
    #     chat = await event.get_chat()
    #     sender = await event.get_sender()
    #     chat_id = event.chat_id
    #     sender_id = event.sender_id


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
        action = self.get_action(array)
        leverage = self.get_leverage(array)

        pair = self.find_pair(array)
        entry_points = self.find_entry_points(array, action, leverage)
        profits = self.find_profits(array)
        stop_loss = self.find_stop(array)
        return PairModel(pair, action, leverage, entry_points, profits, stop_loss, message_id)

    def iterate_files(self, message_id):
        pairs = []
        for filename in os.listdir(directory):
            if filename.endswith(".jpg"):
                pair_info = self.get_parsed(filename, message_id)
                pairs.append(pair_info)
                now = str(datetime.datetime.now())[:19]
                now = now.replace(":", "_")
                shutil.move("D:/Frameworks/LucrativeTrend/{}".format(filename),
                            "D:/Frameworks/LucrativeTrend/archive/" + str(now) + ".jpg")
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
    client = ShtClient(api_key=conf_obj.api_key, api_secret=conf_obj.api_secret)

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
                price_json = urllib.request.urlopen('https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_object.pair))
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
            signals.append(SignalModel(current_pair['symbol'], pair_info_object['isMarginTradingAllowed'], current_pair['price'], pair_object.action, pair_object.leverage, entries, profits, stop_loss, pair_object.message_id))
        return signals

    def verify_entry(self, pair_object, current_pair_info):
        verified_entries = []
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.entry_points:
                if price.find('.') > 0 and price.find('.') != dot_position:
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

