import logging

from datetime import timedelta
from sys import platform
import pytesseract
import time

from asgiref.sync import sync_to_async
from telethon.tl.types import User

from apps.signal.models import SignalOrig, Signal, EntryPoint, TakeProfit
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import rounded_result
from utils.parse_channels.str_parser import left_numbers, replace_rus_to_eng, handle_crypto_angel_to_array
from .base_model import BaseTelegram
from .image_parser import ChinaImageToSignal
from apps.market.models import get_or_create_async_futures_market

from .verify_signal import SignalVerification
from ..pair.models import Pair
from ..signal.utils import MarginType, calculate_position, CANCELING__SIG_STATS, \
    NEW_FORMED_PUSHED_BOUGHT_SOLD__SIG_STATS

logger = logging.getLogger(__name__)

if platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class SignalModel:
    short_label = 'short'
    long_label = 'long'

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
    one_satoshi = 0.00000001

    async def parse_cf_trader_channel(self):
        channel_abbr = 'cf_tr'
        tca = int(conf_obj.CFTrader)
        async for message in self.client.iter_messages(tca, limit=7):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            if message.text and not exists:
                signal = self.parse_cf_trader_message(message.text, message.id)
                if signal.pair:
                    urgent_action = signal.current_price
                    if urgent_action == 'cancel':
                        await self._recreate_signal(urgent_action, signal, signal.algorithm, message)
                    else:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_error_message_to_yourself(signal, inserted_to_db)
                        else:
                            await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                                message.date, channel_abbr, message.id)

    def parse_cf_trader_message(self, message_text, message_id):
        text = replace_rus_to_eng(message_text)
        lower_text = text.lower()
        lower_info = lower_text.splitlines()
        splitted_info = text.splitlines()
        possible_entry_label = ['Entry', 'Get', '**Entry']
        possible_take_profits_label = ['Sell at', 'Targets']
        possible_take_profits_label2 = 'Take profit'
        possible_stop_label = ['SL: ', 'SL : ', 'Stop loss:']
        pair_label = ['Pair: ', 'Asset', '**Asset']
        leverage_label = 'Leverage:'
        margin_type = MarginType.ISOLATED.value
        current_price = ''
        position = ''
        leverage = 25
        pair = ''
        entries = []
        profits = []
        stop_loss = ['']
        signal_identification = 'CF Leverage Trading Signal'
        should_entry = [i for i, s in enumerate(splitted_info) if 'Stop loss:' in s]
        should_close = [i for i, s in enumerate(lower_info) if 'close' in s or 'closing' in s or 'closed' in s]
        if should_close:
            reached_label = [i for i, s in enumerate(splitted_info) if 'reached' in s]
            coin = ''
            if reached_label:
                coin = splitted_info[0].split()[0]
            if 'close position' in lower_info:
                coin = splitted_info[1].split()[0]
            if 'closing' in lower_info[0]:
                coin = splitted_info[0].split()[1]
            pair = coin + 'USDT'
            current_price = 'cancel'
            signal = SignalModel(pair, current_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        if not should_entry:
            should_entry = [i for i, s in enumerate(splitted_info) if 'SL:' in s]
        if not should_entry:
            signal = SignalModel(pair, current_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal

        for line in splitted_info:
            if line.startswith(pair_label[0]) or line.startswith(pair_label[1]) or line.startswith(pair_label[2]):
                if not pair:
                    possible_position_info = line.split(' ')
                    pair = ''.join(filter(str.isalpha, possible_position_info[1]))
                    if signal_identification:
                        position_info = list(filter(None, possible_position_info))
                        pair = ''.join(filter(str.isalpha, position_info[1]))
            if line.startswith(possible_entry_label[0]) or line.startswith(possible_entry_label[1]) \
                    or line.startswith(possible_entry_label[2]):
                splitted_entries = line.split(' - ')
                possible_entries = splitted_entries[0].split(' ')
                entries.append(possible_entries[-1])
                entries.append(splitted_entries[1])
            if line.startswith(possible_take_profits_label[0]) or line.startswith(possible_take_profits_label[1]):
                fake_profits = line[9:]
                possible_profits = fake_profits.split('-')
                profits = left_numbers(possible_profits)
            if line.startswith(possible_take_profits_label2):
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
            if line.startswith(possible_stop_label[2]):
                stop_loss = line[10:]
                stop_loss = left_numbers([stop_loss])
            # if line.startswith(leverage_label):
            #     possible_leverage = line.split(' ')
            #     possible_leverage = list(filter(None, possible_leverage))
            #     try:
            #         leverage = ''.join(filter(str.isdigit, possible_leverage[2]))
            #     except IndexError:
            #         leverage = ''.join(filter(str.isdigit, possible_leverage[1]))

        position = calculate_position(stop_loss[0], entries, profits)
        entries = self.extend_nearest_ep(position, entries)
        profits = profits[:3]

        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss[0], message_id)
        return signal

    async def parse_lucrative_recommend_channel(self):
        chat_id = int(conf_obj.lucrative_channel)
        async for message in self.client.iter_messages(chat_id, limit=16):
            signal = self.parse_lucrative_recommend_message(message.text)
            exists = await self.is_signal_handled(signal.msg_id, signal.algorithm)
            if not exists and signal.pair:
                urgent_action = signal.current_price
                if urgent_action == 'activate' or urgent_action == 'cancel':
                    await self._recreate_signal(urgent_action, signal, signal.algorithm, message)
                else:
                    inserted_to_db = await self.write_signal_to_db(signal.algorithm, signal, signal.msg_id,
                                                                   signal.current_price)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)


    async def parse_luck_channel(self):
        chat_id = int(conf_obj.Luck8414)
        async for message in self.client.iter_messages(chat_id, limit=6):
            if message.text:
                signal = self.parse_lucrative_recommend_message(message.text)
                is_shared = await self.is_signal_shared(signal.msg_id, signal.algorithm)
                if not is_shared:
                    await self.send_shared_message(int(conf_obj.lucrative_channel), signal,
                                                   signal.current_price, signal.algorithm, signal.msg_id)
                    await self.send_shared_message(int(conf_obj.lucrative_trend), signal,
                                                   signal.current_price, signal.algorithm, signal.msg_id)
                    await self.update_shared_signal(signal)

    @sync_to_async
    def update_shared_signal(self, signal):
        is_updated = SignalOrig.update_shared_signal(is_shared=True, techannel_name=signal.algorithm,
                                                     outer_signal_id=signal.msg_id)

    def parse_lucrative_recommend_message(self, message_text):
        splitted_info = message_text.splitlines()
        buy_label = 'Entry Points: '
        pair_label = 'Pair:'
        goals_label = 'Take Profits: '
        stop_label = 'Stop Loss: '
        pair = ''
        current_price = ''
        margin_type_label = 'Margin type:'
        margin_type = ''
        leverage = 'Leverage: '
        entries = ''
        position = ''
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
            if line.startswith(margin_type_label):
                margin_type = line[12:]
                margin_type = margin_type.replace('\'', '')
                margin_type = margin_type.replace(' ', '')
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
                if 'cancel' in current_price or 'activate' in current_price:
                    current_price = current_price
                else:
                    current_price = current_price + '+02:00'
            if line.startswith(algorithm):
                algorithm = line[len(algorithm):].replace('\'', '')
            if line.startswith(outer_id_label):
                message_id = line[4:].replace('\'', '')
        if stop_loss and entries and profits:
            position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id, algorithm)
        return signal

    async def parse_china_channel(self):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()
        chat_id = int(conf_obj.china_channel)
        channel_abbr = 'ai'
        async for message in self.client.iter_messages(chat_id, limit=6):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg and message.media:
                await message.download_media()
                pairs = info_getter.iterate_files(message.id)
                signal = verify_signal.get_active_pairs_info(pairs)
                if not signal:
                    return
                inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                if inserted_to_db != 'success':
                    await self.send_error_message_to_yourself(signal, inserted_to_db)

                else:
                    await self.send_shared_message(int(conf_obj.lucrative_channel), signal,
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.lucrative_trend), signal,
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.token_fast_signals), signal,
                                                   message.date, channel_abbr, message.id)

    async def parse_china_chat(self):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()
        chat_id = int(conf_obj.china_chat)
        channel_abbr = 'ai_se'
        async for message in self.client.iter_messages(chat_id, limit=6):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg and message.media:
                await message.download_media()
                pairs = info_getter.iterate_files(message.id)
                signal = verify_signal.get_active_pairs_info(pairs)
                if not signal:
                    return
                inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                if inserted_to_db != 'success':
                    await self.send_error_message_to_yourself(signal, inserted_to_db)

                else:
                    await self.send_shared_message(int(conf_obj.lucrative_channel), signal,
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.lucrative_trend), signal,
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.token_fast_signals), signal,
                                                   message.date, channel_abbr, message.id)

    async def parse_crypto_angel_channel(self):
        chat_id = int(conf_obj.crypto_angel_id)
        channel_abbr = 'crypto_passive'
        async for message in self.client.iter_messages(chat_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_angel_message(message.text, message.id)
                if signal.pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, channel_abbr, message.id)

    async def parse_crypto_futures_channel(self):
        chat_id = int(conf_obj.crypto_futures)
        channel_abbr = 'crypto_futures'
        async for message in self.client.iter_messages(chat_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_crypto_futures_message(message.text, message.id)
                if signal:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal[0], inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                            message.date, channel_abbr, message.id)

    def parse_angel_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        buy_label = 'Покупаем по цене: '
        goals_label = 'Цели: '
        stop_label = 'Sl: '
        pair = ''
        current_price = ''
        is_margin = False
        position = ''
        leverage = 1
        entries = ''
        profits = ''
        stop_loss = ''
        if buy_label not in splitted_info[2]:
            signal = SignalModel(pair, current_price, is_margin, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal

        for line in splitted_info:
            if line.startswith(buy_label):
                pair = ''.join(filter(str.isalpha, splitted_info[0]))
            if line.startswith(buy_label):
                fake_entries = line[18:]
                entries = handle_crypto_angel_to_array(fake_entries)
            if line.startswith(goals_label):
                fake_profits = line[6:]
                profits = handle_crypto_angel_to_array(fake_profits)
            if line.startswith(stop_label):
                stop_loss = line[4:]
                stop_loss = handle_crypto_angel_to_array(stop_loss)
                try:
                    stop_loss = f'{min(float(s) for s in stop_loss)}'
                except:
                    stop_loss = '0'
        """ Take only first 4 take profits: """
        profits = profits[:4]
        position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, is_margin, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    def parse_crypto_futures_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        buy_label = 'Вход'
        goals_label = 'Цели: '
        stop_label = 'Sl: '
        pair = ''
        current_price = ''
        margin_type = ''
        position = ''
        leverage = 5
        entries = ''
        profits = ''
        stop_loss = ''
        try:
            entry_index = [i for i, s in enumerate(splitted_info) if buy_label in s]
        except ValueError as e:
            signal = SignalModel(pair, current_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        if not entry_index:
            signal = SignalModel(pair, current_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        pair = ''.join(filter(str.isalpha, splitted_info[0]))
        for line in splitted_info:
            if line.startswith(buy_label):
                fake_entries = line.split(buy_label)
                entries = handle_crypto_angel_to_array(fake_entries[1])
            if line.startswith(goals_label):
                fake_profits = line[6:]
                profits = handle_crypto_angel_to_array(fake_profits)
            if line.startswith(stop_label):
                stop_loss = line[4:]
                stop_loss = handle_crypto_angel_to_array(stop_loss)
                try:
                    stop_loss = f'{min(float(s) for s in stop_loss)}'
                except:
                    stop_loss = '0'
        """ Take only first 4 take profits: """
        profits = profits[:4]
        position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    async def parse_white_bull_channel(self):
        channel_id = int(conf_obj.white_bull)
        access_hash = -2290079952106309008
        channel_entity = User(id=channel_id, access_hash=access_hash)
        channel_abbr = 'white_bull'
        async for message in self.client.iter_messages(entity=channel_entity, limit=7):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_white_bull_message(message.text, message.id)
                if signal.entry_points and signal.pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, channel_abbr, message.id)

    def parse_white_bull_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        pair_label = '#'
        buy_label = ['Buy: ', 'Short', 'short', 'buy']
        goals_label = ['Sell', 'sell']
        stop_label = 'SL'
        stop_label_2 = 'Sl'
        pair = ''
        current_price = ''
        margin_type = ''
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
        position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    async def parse_klondike_channel(self, name):
        if name == 'scalp':
            channel_id = int(conf_obj.klondike_scalp)
            channel_abbr = 'kl_sc'
        if name == 'altcoin':
            channel_id = int(conf_obj.klondike_altcoin)
            channel_abbr = 'kl_al'
        if name == 'margin':
            channel_id = int(conf_obj.klondike_margin)
            channel_abbr = 'kl_mg'

        async for message in self.client.iter_messages(channel_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_klondike_message(message.text, message.id)
                if signal.entry_points and signal.pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, channel_abbr, message.id)

    def parse_klondike_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        is_new_signal = '#SIGNAL'
        price_between_label = 'price between'
        goals_label = 'Targets:'
        stop_label = 'STOP LOSS'
        pair = ''
        current_price = ''
        margin_type = ''
        position = ''
        leverage = ''
        cross_leverage_label = 'cross leverage'
        alt_leverage_label = 'x leverage'
        entries = []
        profits = []
        stop_loss = ''
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id)
        if '❌DELETED❌' in splitted_info[0]:
            return signal
        try:
            pair_index = [i for i, s in enumerate(splitted_info) if is_new_signal in s]
            pair_index = pair_index[0]
        except Exception as e:
            return signal
        if is_new_signal in splitted_info[pair_index]:
            pair_info = splitted_info[pair_index].split(' ')
            pair = ''.join(filter(str.isalpha, pair_info[1]))

        try:
            price_index = [i for i, s in enumerate(splitted_info) if price_between_label in s]
        except ValueError as e:
            return signal

        if price_index:
            price_index = price_index[0]
            if cross_leverage_label in splitted_info[price_index]:
                leverage = 20
            if 'X' in splitted_info[price_index]:
                possible_leverage = splitted_info[price_index].split('X')
                leverage = possible_leverage[1].split(' ')
                leverage = leverage[0]
            if alt_leverage_label in splitted_info[price_index]:
                possible_leverage = splitted_info[price_index].split(alt_leverage_label)
                leverage = possible_leverage[0].split(' ')
                leverage = leverage[-1]
            if alt_leverage_label not in splitted_info[price_index] and 'X' not in splitted_info[price_index] \
                    and cross_leverage_label not in splitted_info[price_index]:
                leverage = 3

            possible_entries = splitted_info[price_index].split(' - ')
            possible_entry1 = possible_entries[0].split(' ')
            possible_entry2 = possible_entries[1].split(' ')
            entries.append(possible_entry1[-1].replace('$', ''))
            entries.append(possible_entry2[0].replace('$', ''))

            try:
                goals_index = [i for i, s in enumerate(splitted_info) if goals_label in s]
            except ValueError as e:
                return signal
            possible_targets = splitted_info[goals_index[0] + 2: goals_index[0] + 7]
            for possible_target in possible_targets:
                target = possible_target.split('$')
                profits.append(target[1])

            if stop_label in splitted_info[-1]:
                possible_stop = splitted_info[-1].split(': ')
                stop_loss = possible_stop[1]
                stop_loss = stop_loss.replace('$', '')

            position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    async def parse_wcse_channel(self):
        channel_id = int(conf_obj.wcse)
        channel_abbr = 'wc_se'
        # entity = await self.client.get_entity('@WCSEBot')
        access_hash = 7265387611438966175
        channel_entity = User(id=channel_id, access_hash=access_hash)
        async for message in self.client.iter_messages(entity=channel_entity, limit=15):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            if message.text and not exists:
                signal = self.parse_wcse_message(message.text, message.id)
                if signal.pair:
                    if signal.entry_points:
                        inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                        if inserted_to_db != 'success':
                            await self.send_error_message_to_yourself(signal, inserted_to_db)
                        else:
                            await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                                message.date, channel_abbr, message.id)
                    else:
                        urgent_action = signal.current_price
                        # Works only for signals located in table Signal with status NEW, FORMED, PUSHED, BOUGHT, SOLD
                        await self._recreate_signal(urgent_action, signal, channel_abbr, message, True)

    async def _recreate_signal(self, urgent_action, old_signal, channel_abbr, message, distribution=False):
        if urgent_action == 'activate':
            signal_object = await self._get_async_processing_signal(symbol=old_signal.pair, channel_abbr=channel_abbr)
            if signal_object:
                await self._close_signal(signal_object)
            if not signal_object:
                return
            signal = await self._form_signal(old_signal, signal_object, old_signal.msg_id, channel_abbr)
            if distribution:
                await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                    message.date, channel_abbr, message.id, urgent_action)
            inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, signal.msg_id, message.date)
            if inserted_to_db != 'success':
                await self.send_error_message_to_yourself(signal, inserted_to_db)
        if urgent_action == 'cancel':
            signal_object = await self._get_async_processing_signal(symbol=old_signal.pair, channel_abbr=channel_abbr)
            if signal_object and int(old_signal.msg_id) > int(signal_object.outer_signal_id):
                await self._close_signal(signal_object)
                if distribution:
                    await self.send_message_by_template(int(conf_obj.lucrative_channel), old_signal,
                                                        message.date, channel_abbr, message.id, urgent_action)
            if not signal_object:
                return

    async def _form_signal(self, old_signal, signal_object, message_id, channel_abbr):
        current_price = signal_object.market.logic.get_current_price(old_signal.pair)
        pair = await Pair.get_async_pair(old_signal.pair, signal_object.market)
        step_quantity = pair.step_price

        profits = await self._get_profits_from_signal(signal_object)
        entries = self._form_divergence_entries(signal_object.position, current_price, step_quantity)
        if signal_object.position == SignalModel.long_label and max(entries) > min(profits):
            while max(entries) > min(profits):
                nearest_profit_index = profits.index(min(profits))
                del profits[nearest_profit_index]
        if signal_object.position == SignalModel.short_label and min(entries) > max(profits):
            while min(entries) > max(profits):
                nearest_profit_index = profits.index(max(profits))
                del profits[nearest_profit_index]
        signal = SignalModel(signal_object.symbol, current_price, signal_object.margin_type,
                             signal_object.position, signal_object.leverage, entries,
                             profits, signal_object.stop_loss, message_id, channel_abbr)
        return signal

    @sync_to_async
    def _get_profits_from_signal(self, signal_object):
        profits = []
        for take_profit in signal_object.take_profits.all():
            profits.append(take_profit.value)
        return profits

    async def _close_signal(self, signal):
        counter = 1
        cancelled_signal = False
        while not cancelled_signal and counter < 301:
            logger.info(f'Trying to close the signal: {signal.symbol}, id:{signal.id}, Attempt #{counter}')
            await signal.async_try_to_spoil_by_one_signal(True)
            cancelled_signal = await self._is_signal_cancelled(signal)
            logger.info(f'Is signal {signal.symbol} with id:{signal.id} cancelled: {cancelled_signal}')
            time.sleep(1)
            counter += 1

    def parse_wcse_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        is_new_signal = 'New Signal Created'
        signal_activated = 'Signal Activated'
        signal_cancelled = 'Signal Cancelled'
        signal_closed = 'Signal Closed'
        is_label = 'Binance'
        buy_label = '🔀 Entry Zone 🔀'
        goals_label = '🔆 Exit Targets:🔆'
        stop_label = '⛔ StopLoss ⛔'
        pair = ''
        action_price = ''
        is_margin = False
        position = ''
        leverage = ''
        entries = []
        profits = []
        stop_loss = ''

        if signal_activated in splitted_info[0]:
            pair_info = splitted_info[0].split('#')
            pair_info = pair_info[1].split('** **')
            pair = ''.join(filter(str.isalpha, pair_info[0]))
            action_price = 'activate'
            signal = SignalModel(pair, action_price, is_margin, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        if signal_cancelled in splitted_info[0] or signal_closed in splitted_info[0]:
            pair_info = splitted_info[0].split('#')
            pair_info = pair_info[1].split('** **')
            pair = ''.join(filter(str.isalpha, pair_info[0]))
            action_price = 'cancel'
            signal = SignalModel(pair, action_price, is_margin, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        if is_new_signal in splitted_info[0]:
            pair_info = splitted_info[1].split('#')
            pair = ''.join(filter(str.isalpha, pair_info[1]))
            if is_label in splitted_info[2]:
                possible_leverage = splitted_info[2].split('(')
                leverage = left_numbers([possible_leverage[1].split(' ')[1]])
                leverage = leverage[0]
                try:
                    entry_index = splitted_info.index(buy_label)
                except ValueError as e:
                    signal = SignalModel(pair, action_price, is_margin, position,
                                         leverage, entries, profits, stop_loss, message_id)
                    return signal
                possible_entries = splitted_info[entry_index + 1:entry_index + 3]
                for possible_entry in possible_entries:
                    entry = possible_entry.split(' ')
                    entries.append(entry[1])

                try:
                    goals_index = splitted_info.index(goals_label)
                except ValueError as e:
                    signal = SignalModel(pair, action_price, is_margin, position,
                                         leverage, entries, profits, stop_loss, message_id)
                    return signal
                possible_targets = splitted_info[goals_index + 1:goals_index + 6]
                for possible_target in possible_targets:
                    target = possible_target.split(' ')
                    if target != ['']:
                        profits.append(target[1])

                try:
                    stop_index = splitted_info.index(stop_label)
                except ValueError as e:
                    signal = SignalModel(pair, action_price, is_margin, position,
                                         leverage, entries, profits, stop_loss, message_id)
                    return signal
                possible_stop = splitted_info[stop_index + 1:stop_index + 2]
                stop_loss = possible_stop[0].split(' ')
                stop_loss = stop_loss[1]
                position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, action_price, is_margin, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    async def parse_server_channel(self):
        """
        The method must be used only when the automatic processing of a signal to Futures market is turned off!
        """
        channel_id = int(conf_obj.server)
        channel_abbr = 'server'
        async for message in self.client.iter_messages(channel_id, limit=5):
            if message.text:
                signal = self.parse_server_message(message.text)
                exists = await self.is_signal_handled(signal.msg_id, channel_abbr)
                if signal.pair and not exists and signal.current_price != 'close':
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, signal.msg_id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                if signal.pair and exists and 'close' in signal.current_price:
                    cancelled_signal = False
                    signal_object = await self._get_async_processing_signal(signal.pair, channel_abbr, signal.msg_id)
                    while not cancelled_signal:
                        time.sleep(0.2)
                        await signal_object.async_try_to_spoil_by_one_signal(True)
                        cancelled_signal = await self._is_signal_cancelled()

    async def parse_fsvzo_channel(self):
        channel_id = int(conf_obj.fsvzo)
        # entity = await self.client.get_entity('@alertatron_bot')
        access_hash = 475713384967520097
        channel_entity = User(id=channel_id, access_hash=access_hash)
        async for message in self.client.iter_messages(entity=channel_entity, limit=7):
            if message.text:
                signal = await self.parse_fsvzo_message(message.text, message.id)
                exists = await self.is_signal_handled(message.id, signal.algorithm)
                if signal.pair and not exists:
                    inserted_to_db = await self.write_signal_to_db(signal.algorithm, signal, message.id,
                                                                   message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, signal.algorithm, message.id)

    async def parse_fsvzo_message(self, message_text, message_id):
        algorithm = 'diver_'
        position = ''
        margin_type = 'ISOLATED'
        leverage = 10
        if 'Bear' in message_text:
            position = SignalModel.short_label
        if 'Bull' in message_text:
            position = SignalModel.long_label
        splitted_text = message_text.split(' ')
        algorithm = algorithm + splitted_text[-1]
        algorithm = algorithm.lower()
        symbol = splitted_text[-2] + 'USDT'

        futures_market = await get_or_create_async_futures_market()
        current_price = futures_market.logic.get_current_price(symbol)

        pair = await Pair.get_async_pair(symbol, futures_market)
        step_quantity = pair.step_price

        entries = self._form_divergence_entries(position, current_price, step_quantity)
        stop_loss = self._form_divergence_stop(position, current_price, step_quantity)
        profits = self._form_divergence_profits(position, current_price, step_quantity)

        signal = SignalModel(pair.symbol, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id, algorithm)
        return signal

    def _form_divergence_entries(self, position, current_price, step_quantity):
        entries = []
        first_entry = ''
        second_entry = ''
        delta_first_entry = (current_price * conf_obj.market_entry_deviation_perc) / conf_obj.one_hundred_percent
        delta_second_entry = (current_price * conf_obj.second_entry_deviation_perc) / conf_obj.one_hundred_percent
        if position == SignalModel.short_label:
            first_entry = current_price - delta_first_entry
            second_entry = current_price + delta_second_entry
        if position == SignalModel.long_label:
            first_entry = current_price + delta_first_entry
            second_entry = current_price - delta_second_entry

        entries.append(self._round_price(first_entry, step_quantity))
        entries.append(self._round_price(second_entry, step_quantity))

        return entries

    @rounded_result
    def _round_price(self, price, step_quantity):
        price += self.one_satoshi
        return (price // step_quantity) * step_quantity

    def _form_divergence_profits(self, position, current_price, step_quantity):
        profits = []
        first_profit = ''
        second_profit = ''
        third_profit = ''
        fourth_profit = ''
        fifth_profit = ''
        delta_first_profit = (current_price * conf_obj.first_profit_deviation_perc) / conf_obj.one_hundred_percent
        delta_second_profit = (current_price * conf_obj.second_profit_deviation_perc) / conf_obj.one_hundred_percent
        delta_third_profit = (current_price * conf_obj.third_profit_deviation_perc) / conf_obj.one_hundred_percent
        delta_fourth_profit = (current_price * conf_obj.fourth_profit_deviation_perc) / conf_obj.one_hundred_percent
        delta_fifth_profit = (current_price * conf_obj.fifth_profit_deviation_perc) / conf_obj.one_hundred_percent
        if position == SignalModel.short_label:
            first_profit = current_price - delta_first_profit
            second_profit = current_price - delta_second_profit
            third_profit = current_price - delta_third_profit
            fourth_profit = current_price - delta_fourth_profit
            fifth_profit = current_price - delta_fifth_profit
        if position == SignalModel.long_label:
            first_profit = current_price + delta_first_profit
            second_profit = current_price + delta_second_profit
            third_profit = current_price + delta_third_profit
            fourth_profit = current_price + delta_fourth_profit
            fifth_profit = current_price + delta_fifth_profit

        profits.append(self._round_price(first_profit, step_quantity))
        profits.append(self._round_price(second_profit, step_quantity))
        profits.append(self._round_price(third_profit, step_quantity))
        profits.append(self._round_price(fourth_profit, step_quantity))
        profits.append(self._round_price(fifth_profit, step_quantity))

        return profits

    def _form_divergence_stop(self, position, current_price, step_quantity):
        stop_loss = ''
        if position == SignalModel.short_label:
            delta_stop = (current_price * conf_obj.delta_stop_deviation_perc) / conf_obj.one_hundred_percent
            stop_loss = current_price + delta_stop
        if position == SignalModel.long_label:
            delta_stop = (current_price * conf_obj.delta_stop_deviation_perc) / conf_obj.one_hundred_percent
            stop_loss = current_price - delta_stop
        stop_loss = self._round_price(stop_loss, step_quantity)
        return stop_loss

    def parse_server_message(self, message_text):
        splitted_info = message_text.splitlines()
        buy_label = 'Entry Points: '
        pair_label = 'Pair:'
        goals_label = 'Take Profits: '
        stop_label = 'Stop Loss: '
        pair = ''
        current_price = ''
        margin_type = False
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
                current_price = line[6:].replace('\'', '')
                if 'close' in current_price:
                    current_price = current_price
                else:
                    current_price = current_price + '+02:00'
            if line.startswith(algorithm):
                algorithm = line[len(algorithm):].replace('\'', '')
            if line.startswith(outer_id_label):
                message_id = line[4:].replace('\'', '')
        position = calculate_position(stop_loss, entries, profits)
        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id, algorithm)
        return signal

    async def parse_tca_channel(self, sub_type: str):
        chat_id = int
        channel_abbr = ''
        if sub_type == 'altcoin':
            channel_abbr = 'assist_altcoin'
            chat_id = int(conf_obj.tca_altcoin)
        if sub_type == 'leverage':
            channel_abbr = 'assist_leverage'
            chat_id = int(conf_obj.tca_leverage)
        async for message in self.client.iter_messages(chat_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            if message.text and not exists:
                signal = self.parse_tca_message(message.text, message.id, channel_abbr)
                if signal.pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, channel_abbr, message.id)

    def parse_tca_message(self, message_text, message_id, channel_abbr):
        splitted_info = message_text.splitlines()
        buy_label = 'Entry at: '
        possible_take_profits = ['Sell at: ', 'Targets: ']
        stop_label = 'Stop Loss: '
        pair_label = ['Coin: ', 'Pair']
        action_price = ''
        margin_type = MarginType.ISOLATED.value
        leverage = 25
        entries = ''
        position = ''
        pair = ''
        profits = ''
        stop_loss = ''
        signal_identification = ['Exchange: Binance', 'Exchange: Binance Futures', 'Exchange: ByBit']
        is_signal = any(x in signal_identification for x in splitted_info)
        if not is_signal:
            signal = SignalModel(pair, action_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        for line in splitted_info:
            if line.startswith(pair_label[0]) or line.startswith(pair_label[1]):
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
        position = calculate_position(stop_loss, entries, profits)
        entries = self.extend_nearest_ep(position, entries)
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signal = SignalModel(pair, action_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id, channel_abbr)
        return signal

    async def parse_margin_whale_channel(self):
        chat_id = int(conf_obj.margin_whales)
        channel_abbr = 'margin_whale'
        async for message in self.client.iter_messages(chat_id, limit=5):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_margin_whale_message(message.text, message.id)
                if signal.pair:
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_error_message_to_yourself(signal, inserted_to_db)
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal,
                                                            message.date, channel_abbr, message.id)

    def parse_margin_whale_message(self, message_text, message_id):
        splitted_info = message_text.splitlines()
        buy_label = 'ENTRY'
        margin_label = '#MARGIN'
        goals_label = 'Target'
        stop_label = 'STOP LOSS: '
        pair = ''
        current_price = ''
        margin_type = 'ISOLATED'
        position = ''
        leverage = 15
        entries = ''
        profits = []
        stop_loss = ''
        should_entry = [i for i, s in enumerate(splitted_info) if margin_label in s]
        if not should_entry:
            signal = SignalModel(pair, current_price, margin_type, position,
                                 leverage, entries, profits, stop_loss, message_id)
            return signal
        for line in splitted_info:
            if line.startswith(margin_label):
                fake_pair = line.split(' ')
                possible_pair = fake_pair[2]
                if 'XBT' in possible_pair or 'BTC' in possible_pair:
                    pair = 'BTCUSDT'
            if line.startswith(buy_label):
                fake_entries = line[8:]
                possible_entries = fake_entries.split('-')
                entries = left_numbers(possible_entries)
            # if line.startswith(leverage):
            #     possible_leverage = line.split(':')
            #     leverage = ''.join(filter(str.isdigit, possible_leverage[1]))
            if line.startswith(goals_label):
                possible_profits = line.split('-')
                profits.append(possible_profits[1].replace(' ', ''))
            if line.startswith(stop_label):
                stop_loss = line[11:]
        """ Take only first 5 take profits: """
        profits = profits[:5]
        position = calculate_position(stop_loss, entries, profits)
        entries = self.extend_nearest_ep(position, entries)

        signal = SignalModel(pair, current_price, margin_type, position,
                             leverage, entries, profits, stop_loss, message_id)
        return signal

    def extend_nearest_ep(self, position, entries):
        if position == SignalModel.short_label:
            min_entry = min(entries)
            delta_entry = (float(min_entry) * conf_obj.market_entry_deviation_perc) / conf_obj.one_hundred_percent
            new_entry = float(min_entry) - delta_entry
            entries = [str(new_entry) if i == min_entry else i for i in entries]
        if position == SignalModel.long_label:
            max_entry = max(entries)
            delta_entry = (float(max_entry) * conf_obj.market_entry_deviation_perc) / conf_obj.one_hundred_percent
            new_entry = float(max_entry) + delta_entry
            entries = [str(new_entry) if i == max_entry else i for i in entries]

        return entries

    @sync_to_async
    def _is_signal_cancelled(self, signal_object):
        cancelled_signal = Signal.objects.filter(id=signal_object.id, _status__in=CANCELING__SIG_STATS)
        return cancelled_signal.exists()

    @sync_to_async
    def is_signal_handled(self, message_id, channel_abbr):
        is_exist = SignalOrig.objects.filter(outer_signal_id=message_id, techannel__name=channel_abbr).exists()
        if is_exist:
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' already exists in DB")
        return is_exist

    @sync_to_async
    def is_signal_shared(self, message_id, channel_abbr):
        is_shared = SignalOrig.objects.filter(is_shared=True, outer_signal_id=message_id,
                                              techannel__name=channel_abbr).exists()
        return is_shared

    @sync_to_async
    def get_not_served_signal(self, message_id, channel_abbr):
        signal = Signal.objects.filter(techannel__name=channel_abbr,
                                       outer_signal_id=message_id).first()
        if signal:
            is_served = getattr(signal, 'is_served')
            if not is_served:
                return signal
            if is_served:
                return True
        else:
            return None

    @sync_to_async
    def _get_async_processing_signal(self, symbol, channel_abbr, message_id=None) -> Signal:
        params = {'symbol': symbol, 'techannel__name': channel_abbr,
                  '_status__in': NEW_FORMED_PUSHED_BOUGHT_SOLD__SIG_STATS}
        if message_id:
            params.update({'outer_signal_id': message_id})
        signal = Signal.objects.filter(**params).order_by('id').last()
        return signal

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
        if not signal.pair:
            return
        signal.pair = '1INCHUSDT' if 'INCHUSDT' in signal.pair else signal.pair
        sm_obj = SignalOrig.objects.filter(outer_signal_id=message_id, techannel__name=channel_abbr).first()
        if sm_obj:
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' already exists")
            quit()
        if signal.pair[-3:] == 'USD':
            signal.pair = signal.pair.replace('USD', 'USDT')
        logger.debug(f"Attempt to write into DB the following signal: "
                     f" Pair: '{signal.pair}'\n"
                     f" Leverage: '{signal.leverage}'\n"
                     f" Margin type: '{signal.margin_type}'\n"
                     f" Entry Points: '{signal.entry_points}'\n"
                     f" Take Profits: '{signal.take_profits}'\n"
                     f" Stop Loss: '{signal.stop_loss}'\n"
                     f" Algorithm: '{channel_abbr}'\n"
                     f" Message ID: '{message_id}'")
        try:
            SignalOrig.create_signal(techannel_name=channel_abbr,
                                     leverage=signal.leverage,
                                     symbol=signal.pair,
                                     stop_loss=signal.stop_loss,
                                     entry_points=signal.entry_points,
                                     take_profits=signal.take_profits,
                                     outer_signal_id=message_id,
                                     message_date=message_date,
                                     margin_type=signal.margin_type)
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' created successfully")
            return 'success'
        except Exception as e:
            logger.error(f"Write into DB failed: {e}")
            return e

    async def send_error_message_to_yourself(self, signal, inserted_to_db):
        is_shared = await self.is_signal_shared(signal.msg_id, signal.algorithm)
        if is_shared:
            return
        message = "Failed to create the signal into DB:\n" \
                  f"Pair: '{signal.pair}'\n" \
                  f"Leverage: '{signal.leverage}'\n" \
                  f"Margin type: '{signal.margin_type}'\n" \
                  f"Entry Points: '{signal.entry_points}'\n" \
                  f"Take Profits: '{signal.take_profits}'\n" \
                  f"Stop Loss: '{signal.stop_loss}'\n" \
                  f"Algorithm: '{signal.algorithm}'\n" \
                  f"ID: '{signal.msg_id}'\n" \
                  f"ERROR: '{inserted_to_db}'\n"
        await self.client.send_message('me', message)
        # await self.update_shared_signal(signal) it does not work as we doesn't have the signal in DB, due to the ERROR

    async def send_message_by_template(self, channel_name, signal, message_date, channel_abbr, message_id,
                                       urgent_action=None):
        if not signal.leverage:
            signal.leverage = 1
        if signal.margin_type != 'CROSSED':
            signal.margin_type = 'ISOLATED'
        time_to_action = message_date.replace(tzinfo=None) + timedelta(hours=3) if not urgent_action else urgent_action
        message = f"Pair: '{signal.pair}'\n" \
                  f"Position: '{signal.position}'\n" \
                  f"Leverage: '{signal.leverage}'\n" \
                  f"Margin type: '{signal.margin_type}'\n" \
                  f"Entry Points: '{signal.entry_points}'\n" \
                  f"Take Profits: '{signal.take_profits}'\n" \
                  f"Stop Loss: '{signal.stop_loss}'\n" \
                  f"Time: '{time_to_action}'\n" \
                  f"Algorithm: '{channel_abbr}'\n" \
                  f"ID: '{message_id}'"
        await self.client.send_message(channel_name, message)

    async def send_shared_message(self, channel_name, signal, message_date, channel_abbr, message_id):
        if 'ai' in channel_abbr:
            utc_time = message_date.replace(microsecond=0, tzinfo=None)
            message_date = utc_time + timedelta(hours=2)
            message_date = message_date.strftime('%Y-%m-%d %H:%M:%S')
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
