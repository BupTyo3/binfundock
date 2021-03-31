import logging

from datetime import timedelta
from sys import platform
import pytesseract

from asgiref.sync import sync_to_async
from telethon.tl.types import User

from apps.signal.models import SignalOrig, Signal, EntryPoint, TakeProfit
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import rounded_result
from utils.parse_channels.str_parser import left_numbers, check_pair, replace_rus_to_eng
from .base_model import BaseTelegram
from .image_parser import ChinaImageToSignal
from apps.market.models import get_or_create_async_futures_market

from .verify_signal import SignalVerification
from ..pair.models import Pair
from ..signal.utils import MarginType, calculate_position

logger = logging.getLogger(__name__)

if platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class SignalModel:
    short_label = 'SHORT'
    long_label = 'LONG'

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

    async def parse_cf_trader_channel(self):
        channel_abbr = 'cf_tr'
        tca = int(conf_obj.CFTrader)
        async for message in self.client.iter_messages(tca, limit=7):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if message.text and should_handle_msg:
                signal = self.parse_cf_trader_message(message.text, message.id)
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
                else:
                    attention_to_close = self.is_urgent_close_position(message.text, channel_abbr)
                    correct_position = self.is_urgent_correct_position(message.text, channel_abbr)
                    if attention_to_close or correct_position:
                        logger.error('A SIGNAL REQUIRES ATTENTION!')

    def parse_cf_trader_message(self, message_text, message_id):
        signals = []
        text = replace_rus_to_eng(message_text)
        splitted_info = text.splitlines()
        possible_entry_label = ['Entry', 'Get', '**Entry']
        possible_take_profits_label = ['Sell at', 'Targets']
        possible_take_profits_label2 = 'Take profit'
        possible_stop_label = ['SL: ', 'SL : ', 'Stop loss:']
        pair_label = ['Pair: ', 'Asset', '**Asset']
        pair = ''
        position_label = '#'
        current_price = ''
        margin_type = MarginType.CROSSED.value
        position = None
        leverage_label = 'Leverage:'
        leverage = ''
        entries = []
        profits = ''
        stop_loss = ['']
        signal_identification = 'CF Leverage Trading Signal'
        should_entry = [i for i, s in enumerate(splitted_info) if 'Stop loss:' in s]
        if not should_entry:
            should_entry = [i for i, s in enumerate(splitted_info) if 'SL:' in s]
        if not should_entry:
            return signals.append(SignalModel(pair, current_price, margin_type, position,
                                              leverage, entries, profits, stop_loss, message_id))
        for line in splitted_info:
            if line.startswith(pair_label[0]) or line.startswith(pair_label[1])  or line.startswith(pair_label[2]):
                if not pair:
                    possible_position_info = line.split(' ')
                    pair = ''.join(filter(str.isalpha, possible_position_info[1]))
                    if signal_identification:
                        position_info = list(filter(None, possible_position_info))
                        pair = ''.join(filter(str.isalpha, position_info[1]))
            if position_label in line:
                position_info = line.split(position_label)
                position = ''.join(filter(str.isalpha, position_info[1]))
            if line.startswith(possible_entry_label[0]) or line.startswith(possible_entry_label[1])\
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
            if line.startswith(leverage_label):
                possible_leverage = line.split(' ')
                possible_leverage = list(filter(None, possible_leverage))
                try:
                    leverage = ''.join(filter(str.isdigit, possible_leverage[2]))
                except IndexError:
                    leverage = ''.join(filter(str.isdigit, possible_leverage[1]))

        entries = self.extend_nearest_ep(position, entries)

        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss[0], message_id))
        return signals

    async def parse_lucrative_trend_channel(self):
        chat_id = int(conf_obj.lucrative_channel)
        async for message in self.client.iter_messages(chat_id, limit=7):
            signal = self.parse_lucrative_trend_message(message.text)
            exists = await self.is_signal_handled(signal[0].msg_id, signal[0].algorithm)
            if not exists and signal[0].entry_points != '':
                inserted_to_db = await self.write_signal_to_db(
                    signal[0].algorithm, signal, signal[0].msg_id, signal[0].current_price)
                if inserted_to_db != 'success':
                    await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                        f"please check logs for '{signal[0].pair}' "
                                                        f"related to the '{signal[0].algorithm}' algorithm: "
                                                        f"{inserted_to_db}")

    async def parse_luck_channel(self):
        chat_id = int(conf_obj.Luck8414)
        async for message in self.client.iter_messages(chat_id, limit=6):
            if message.text:
                signal = self.parse_lucrative_trend_message(message.text)
                is_shared = await self.is_signal_shared(signal[0].msg_id, signal[0].algorithm)
                if not is_shared:
                    await self.send_shared_message(int(conf_obj.lucrative), signal[0],
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
        margin_type_label = 'Margin type:'
        margin_type = ''
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
            if line.startswith(margin_type_label):
                margin_type = line[12:]
                margin_type = margin_type.replace('\'', '')
                margin_type = margin_type.replace(' ', '')
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
                current_price = current_price + '+02:00'
            if line.startswith(algorithm):
                algorithm = line[len(algorithm):].replace('\'', '')
            if line.startswith(outer_id_label):
                message_id = line[4:].replace('\'', '')
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss, message_id, algorithm=algorithm))
        return signals

    async def parse_china_channel(self):
        info_getter = ChinaImageToSignal()
        verify_signal = SignalVerification()
        chat_id = int(conf_obj.chat_china_id)
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
                    await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                        f"please check logs for '{signal[0].pair}' "
                                                        f"related to the '{channel_abbr}' algorithm: "
                                                        f"{inserted_to_db}")
                else:
                    await self.send_shared_message(int(conf_obj.lucrative), signal[0],
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.lucrative_channel), signal[0],
                                                   message.date, channel_abbr, message.id)
                    await self.send_shared_message(int(conf_obj.lucrative_trend), signal[0],
                                                   message.date, channel_abbr, message.id)

    async def parse_crypto_angel_channel(self):
        chat_id = int(conf_obj.crypto_angel_id)
        channel_abbr = 'crypto_passive'
        async for message in self.client.iter_messages(chat_id, limit=5):
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
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
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
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
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
        if buy_label not in splitted_info[2]:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        for line in splitted_info:
            if line.startswith(buy_label):
                position = splitted_info[1]
                pair = ''.join(filter(str.isalpha, splitted_info[0]))
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

    def parse_crypto_futures_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = 'Вход'
        cross_label = 'Cross'
        long_label = SignalModel.long_label
        short_label = SignalModel.short_label
        goals_label = 'Цели: '
        stop_label = 'Sl: '
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 5
        entries = ''
        profits = ''
        stop_loss = ''
        try:
            entry_index = [i for i, s in enumerate(splitted_info) if buy_label in s]
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        if not entry_index:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        pair = ''.join(filter(str.isalpha, splitted_info[0]))
        if long_label in splitted_info[1]:
            position = long_label
        if short_label in splitted_info[1]:
            position = short_label
        for line in splitted_info:
            if line.startswith(buy_label):
                fake_entries = line.split(buy_label)
                entries = self.handle_ca_recommend_to_array(fake_entries[1])
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
        access_hash = -2290079952106309008
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
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
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
                    position = SignalModel.long_label
                if line.startswith(buy_label[1]) or line.startswith(buy_label[2]):
                    position = SignalModel.short_label
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

    def parse_klondike_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        is_new_signal = '#SIGNAL'
        price_between_label = 'price between'
        long_label = SignalModel.long_label
        sell_label = SignalModel.short_label
        goals_label = 'Targets:'
        stop_label = 'STOP LOSS'
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = ''
        cross_leverage_label = 'cross leverage'
        alt_leverage_label = 'x leverage'
        entries = []
        profits = []
        stop_loss = ''
        if is_new_signal in splitted_info[0]:
            pair_info = splitted_info[0].split(' ')
            pair = ''.join(filter(str.isalpha, pair_info[1]))

        try:
            price_index = [i for i, s in enumerate(splitted_info) if price_between_label in s]
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))

        if price_index:
            price_index = price_index[0]
            if long_label in splitted_info[price_index]:
                position = SignalModel.long_label
            if sell_label in splitted_info[price_index]:
                position = SignalModel.short_label
            if sell_label or long_label not in splitted_info[price_index]:
                position = SignalModel.long_label
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
            if alt_leverage_label not in splitted_info[price_index] and 'X' not in splitted_info[price_index]\
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
                return signals.append(SignalModel(pair, current_price, is_margin, position,
                                                  leverage, entries, profits, stop_loss, message_id))
            possible_targets = splitted_info[goals_index[0] + 2: goals_index[0] + 7]
            for possible_target in possible_targets:
                target = possible_target.split('$')
                profits.append(target[1])

            if stop_label in splitted_info[-1]:
                possible_stop = splitted_info[-1].split(': ')
                stop_loss = possible_stop[1]
                stop_loss = stop_loss.replace('$', '')

        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_wcse_channel(self):
        channel_id = int(conf_obj.wcse)
        channel_abbr = 'wc_se'
        # entity = await self.client.get_entity('@WCSEBot')
        access_hash = 7265387611438966175
        channel_entity = User(id=channel_id, access_hash=access_hash)
        async for message in self.client.iter_messages(entity=channel_entity, limit=6):
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
                    urgent_action = signal[0].current_price
                    signal = SignalOrig.objects.filter(
                        symbol=signal[0].pair, techannel__name=channel_abbr).order_by('id').last()
                    if urgent_action == 'activate':
                        logger.warning('BUY BY MARKET')
                    if urgent_action == 'cancel':
                        logger.warning('SELL BY MARKET')
                        signal.try_to_spoil_by_one_signal()


    def parse_wcse_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        is_new_signal = 'New Signal Created'
        is_signal_activated = 'Signal Activated'
        is_signal_cancelled = 'Signal Cancelled'
        is_futures_label = 'BinanceFutures'
        buy_label = '🔀 Entry Zone 🔀'
        long_label = SignalModel.long_label
        sell_label = SignalModel.short_label
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

        if is_signal_activated in splitted_info[0]:
            pair_info = splitted_info[0].split('#')
            pair_info = pair_info[1].split('** **')
            pair = ''.join(filter(str.isalpha, pair_info[0]))
            current_price = 'activate'
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        if is_signal_cancelled in splitted_info[0]:
            pair_info = splitted_info[0].split('#')
            pair_info = pair_info[1].split('** **')
            pair = ''.join(filter(str.isalpha, pair_info[0]))
            current_price = 'cancel'
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        if is_new_signal in splitted_info[0]:
            pair_info = splitted_info[1].split('#')
            pair = ''.join(filter(str.isalpha, pair_info[1]))
            if is_futures_label in splitted_info[2]:
                if long_label in splitted_info[2]:
                    position = SignalModel.long_label
                elif sell_label in splitted_info[2]:
                    position = SignalModel.short_label
                possible_leverage = splitted_info[2].split('(')
                leverage = left_numbers([possible_leverage[1].split(' ')[1]])
                leverage = leverage[0]
                try:
                    entry_index = splitted_info.index(buy_label)
                except ValueError as e:
                    return signals.append(SignalModel(pair, current_price, is_margin, position,
                                                      leverage, entries, profits, stop_loss, message_id))
                possible_entries = splitted_info[entry_index + 1:entry_index + 4]
                for possible_entry in possible_entries:
                    entry = possible_entry.split(' ')
                    entries.append(entry[1])

                try:
                    goals_index = splitted_info.index(goals_label)
                except ValueError as e:
                    return signals.append(SignalModel(pair, current_price, is_margin, position,
                                                      leverage, entries, profits, stop_loss, message_id))
                possible_targets = splitted_info[goals_index + 1:goals_index + 9]
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

                """ Take only first 6 take profits: """
                # profits = profits[:6]
                signals.append(SignalModel(pair, current_price, is_margin, position,
                                           leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_server_channel(self):
        """
        The method must be used only when the automatic processing of a signal to Futures market is turned off!
        """
        channel_id = int(conf_obj.server)
        channel_abbr = 'server'
        async for message in self.client.iter_messages(channel_id, limit=5):
            if message.text:
                signal = self.parse_server_message(message.text)
                exists = await self.is_signal_handled(signal[0].msg_id, channel_abbr)
                if signal[0].pair and not exists and signal[0].current_price != 'close':
                    inserted_to_db = await self.write_signal_to_db(channel_abbr, signal, signal[0].msg_id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{channel_abbr}' algorithm: "
                                                            f"{inserted_to_db}")
                if signal[0].pair and exists and 'close' in signal[0].current_price:
                    not_served_signal = await self.get_not_served_signal(signal[0].msg_id, signal[0].algorithm)
                    if not_served_signal and type(not_served_signal) is not bool:
                        await not_served_signal.try_to_aync_spoil()
                        await not_served_signal.make_signal_served(techannel_name=signal[0].algorithm,
                                                                   outer_signal_id=signal[0].msg_id)
                    if not not_served_signal and type(not_served_signal) is bool:
                        pass

    async def parse_fsvzo_channel(self):
        channel_id = int(conf_obj.fsvzo)
        channel_abbr = 'diver_'
        # entity = await self.client.get_entity('@alertatron_bot')
        access_hash = 475713384967520097
        channel_entity = User(id=channel_id, access_hash=access_hash)
        async for message in self.client.iter_messages(entity=channel_entity, limit=7):
            if message.text:
                signal = await self.parse_fsvzo_message(message.text, message.id)
                exists = await self.is_signal_handled(message.id, signal[0].algorithm)
                if signal and not exists:
                    inserted_to_db = await self.write_signal_to_db(signal[0].algorithm, signal, message.id, message.date)
                    if inserted_to_db != 'success':
                        await self.send_message_to_yourself(f"Error during processing the signal to DB, "
                                                            f"please check logs for '{signal[0].pair}' "
                                                            f"related to the '{signal[0].algorithm}' algorithm: "
                                                            f"{inserted_to_db}")
                    else:
                        await self.send_message_by_template(int(conf_obj.lucrative_channel), signal[0],
                                                                message.date, signal[0].algorithm, message.id)

    async def parse_fsvzo_message(self, message_text, message_id):
        algorithm = 'diver_'
        signals = []
        position = ''
        margin_type = 'ISOLATED'
        leverage = 15
        if 'Bear' in message_text:
            position = 'SHORT'
        if 'Bull' in message_text:
            position = 'LONG'
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

        signals.append(SignalModel(symbol, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss, message_id, algorithm=algorithm))
        return signals

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
                current_price = line[6:].replace('\'', '')
                if 'close' in current_price:
                    current_price = current_price
                else:
                    current_price = current_price + '+02:00'
            if line.startswith(algorithm):
                algorithm = line[len(algorithm):].replace('\'', '')
            if line.startswith(outer_id_label):
                message_id = line[4:].replace('\'', '')
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id, algorithm=algorithm))
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
        async for message in self.client.iter_messages(chat_id, limit=5):
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

    def parse_tca_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        long_label = SignalModel.long_label
        short_label = SignalModel.short_label
        buy_label = 'Entry at: '
        possible_take_profits = ['Sell at: ', 'Targets: ']
        stop_label = 'Stop Loss: '
        pair = 'Coin: '
        current_price = ''
        margin_type = MarginType.ISOLATED.value
        position = None
        leverage = 25
        entries = ''
        profits = ''
        stop_loss = ''
        signal_identification = ['Exchange: Binance', 'Exchange: Binance Futures', 'Exchange: ByBit']
        is_signal = any(x in signal_identification for x in splitted_info)
        if not is_signal:
            return
        for line in splitted_info:
            if short_label in line:
                position = short_label
            if long_label in line:
                position = long_label
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

        entries = self.extend_nearest_ep(position, entries)
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_margin_whale_channel(self):
        chat_id = int(conf_obj.margin_whales)
        channel_abbr = 'margin_whale'
        async for message in self.client.iter_messages(chat_id, limit=8):
            exists = await self.is_signal_handled(message.id, channel_abbr)
            should_handle_msg = not exists
            if should_handle_msg:
                signal = self.parse_margin_whale_message(message.text, message.id)
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

    def parse_margin_whale_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        buy_label = ['ENTRY  : ', 'ENTRY : ']
        margin_label = '#MARGIN'
        goals_label = 'Target'
        stop_label = 'STOP LOSS: '
        long_label = SignalModel.long_label
        short_label = SignalModel.short_label
        pair = ''
        current_price = ''
        margin_type = 'ISOLATED'
        position = None
        leverage = 15
        entries = ''
        profits = []
        stop_loss = ''
        should_entry = [i for i, s in enumerate(splitted_info) if margin_label in s]
        if not should_entry:
            return signals.append(SignalModel(pair, current_price, margin_type, position,
                                              leverage, entries, profits, stop_loss, message_id))
        for line in splitted_info:
            if long_label in line:
                position = long_label
            if short_label in line:
                position = short_label
            if line.startswith(margin_label):
                fake_pair = line.split(' ')
                possible_pair = fake_pair[2]
                if 'XBT' in possible_pair or 'BTC' in possible_pair:
                    pair = 'BTCUSDT'
            if line.startswith(buy_label[0]) or line.startswith(buy_label[1]):
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

        entries = self.extend_nearest_ep(position, entries)

        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals


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
        signal[0].pair = '1INCHUSDT' if signal[0].pair == 'INCHUSDT' else signal[0].pair
        sm_obj = SignalOrig.objects.filter(outer_signal_id=message_id, techannel__name=channel_abbr).first()
        if sm_obj:
            logger.debug(f"Signal '{message_id}':'{channel_abbr}' already exists")
            quit()
        if signal[0].pair[-3:] == 'USD':
            signal[0].pair = signal[0].pair.replace('USD', 'USDT')
        logger.debug(f"Attempt to write into DB the following signal: "
                     f" Pair: '{signal[0].pair}'\n"
                     f" Leverage: '{signal[0].leverage}'\n"
                     f" Margin type: '{signal[0].margin_type}'\n"
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
        position = calculate_position(signal.stop_loss, signal.entry_points, signal.take_profits)
        if not signal.leverage:
            signal.leverage = 1
        if signal.margin_type != 'CROSSED':
            signal.margin_type = 'ISOLATED'
        message = f"Pair: '{signal.pair}'\n" \
                  f"Position: '{position}'\n" \
                  f"Leverage: '{signal.leverage}'\n" \
                  f"Margin type: '{signal.margin_type}'\n" \
                  f"Entry Points: '{signal.entry_points}'\n" \
                  f"Take Profits: '{signal.take_profits}'\n" \
                  f"Stop Loss: '{signal.stop_loss}'\n" \
                  f"Time: '{message_date.replace(tzinfo=None) + timedelta(hours=3)}'\n" \
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
