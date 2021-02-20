import numpy as np
import regex
import os
import shutil
import time
from PIL import Image
from django.conf import settings
from pytesseract import image_to_string
from datetime import datetime

leverage_matches = ["LATHFFA", "EFA", "FFA", "EEA", "LETHEFA", "LATHEFA", "LETHFFA", "#LAT", "#LET", "HFFA"]
regexp_numbers = '\d+\.?\d+'
regexp_stop = '\d+\.?\d+$'


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
        from .models import SignalModel
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