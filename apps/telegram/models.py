import logging

from datetime import timedelta
from sys import platform
import pytesseract

from asgiref.sync import sync_to_async
from telethon.tl.types import User

from apps.signal.models import SignalOrig, Signal, EntryPoint, TakeProfit
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import countdown
from utils.parse_channels.str_parser import left_numbers, check_pair
from .base_model import BaseTelegram
from .image_parser import ChinaImageToSignal

from .verify_signal import SignalVerification
from ..signal.utils import MarginType

logger = logging.getLogger(__name__)

if platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


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

    async def parse_cf_trader_channel(self):
        channel_abbr = 'cf_tr'
        tca = int(conf_obj.CFTrader)
        async for message in self.client.iter_messages(tca, limit=18):
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
        splitted_info = message_text.splitlines()
        # possible_entry_label = ['Entry at: ', 'Entry : ', 'Еntry :', 'Entrу :', 'Get in  ', 'Get in : ', 'Gеt in :',
        #                         'Get  in : ', 'Entry: ']
        possible_entry_label = 'Entry:'
        possible_take_profits_label = ['Sell at', 'Targets', 'Тargets', 'Targеts', 'Tаrgets']
        possible_take_profits_label2 = ['Take profit', 'Takе profit', 'Tаkе profit', 'Tаke profit']
        possible_stop_label = ['SL: ', 'SL : ', 'Stop loss:']
        # pair_label = ['Pair: ', 'Рair: ', 'Аssеt:', 'Asset']
        pair_label = ['Аssеt:', 'Asset']
        pair = ''
        position_label = 'Position:'
        current_price = ''
        margin_type = MarginType.CROSSED.value
        position = None
        leverage_label = ['Leverage:', 'Levеrage:', 'Leveragе:', 'Leverаge:', 'Lеverage:']
        leverage = ''
        entries = []
        profits = ''
        stop_loss = ['']
        try:
            should_entry = [i for i, s in enumerate(splitted_info) if 'Stop loss:' in s]
        except ValueError as e:
            return signals.append(SignalModel(pair, current_price, margin_type, position,
                                              leverage, entries, profits, stop_loss, message_id))
        if not should_entry:
            return signals.append(SignalModel(pair, current_price, margin_type, position,
                                              leverage, entries, profits, stop_loss, message_id))
        for line in splitted_info:
            if pair_label[0] or pair_label[1] in line:
                if not pair:
                    pair_info = line.split(' ')
                    # position_info = list(filter(None, possible_position_info))
                    pair = ''.join(filter(str.isalpha, pair_info[1]))
            if position_label in line:
                possible_position_info = line.split('#')
                position = ''.join(filter(str.isalpha, possible_position_info[1]))
            if possible_entry_label in line:
                splitted_entries = line.split(' - ')
                possible_entries = splitted_entries[0].split(' ')
                entries.append(possible_entries[-1])
                entries.append(splitted_entries[1])
            if line.startswith(possible_take_profits_label[0]) or line.startswith(possible_take_profits_label[1]) \
                    or line.startswith(possible_take_profits_label[2]) or line.startswith(
                possible_take_profits_label[3]) \
                    or line.startswith(possible_take_profits_label[4]):
                fake_profits = line[9:]
                possible_profits = fake_profits.split('-')
                profits = left_numbers(possible_profits)
            if line.startswith(possible_take_profits_label2[0]) or line.startswith(possible_take_profits_label2[1]) \
                    or line.startswith(possible_take_profits_label2[2]) or line.startswith(
                possible_take_profits_label2[3]):
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
            if line.startswith(leverage_label[0]) or line.startswith(leverage_label[1]) \
                    or line.startswith(leverage_label[2]) or line.startswith(leverage_label[3]) \
                    or line.startswith(leverage_label[4]):
                possible_leverage = line.split(' ')
                possible_leverage = list(filter(None, possible_leverage))
                try:
                    leverage = ''.join(filter(str.isdigit, possible_leverage[2]))
                except IndexError:
                    leverage = ''.join(filter(str.isdigit, possible_leverage[1]))
        """ Take only first 4 take profits: """
        profits = profits[:4]
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss[0], message_id))
        return signals

    async def parse_lucrative_trend_channel(self):
        chat_id = int(conf_obj.lucrative_channel)
        # channel_abbr = 'lucrative_trend'
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
                current_price = current_price + '+02:00'
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
        async for message in self.client.iter_messages(chat_id, limit=6):
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
        if 'LONG' in splitted_info[1]:
            position = 'LONG'
        if 'SHORT' in splitted_info[1]:
            position = 'SHORT'
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

        # entity = await self.client.get_entity('@WCSEBot')
        # access_hash = 4349140352664297866
        # channel_entity = User(id=channel_id, access_hash=access_hash)
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
        long_label = 'LONG'
        sell_label = 'SHORT'
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
                position = 'LONG'
            if sell_label in splitted_info[price_index]:
                position = 'SHORT'
            if sell_label or long_label not in splitted_info[price_index]:
                position = 'LONG'
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
            if alt_leverage_label and 'X' and cross_leverage_label not in splitted_info[price_index]:
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
        access_hash = 4349140352664297866
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
                            await self.send_message_by_template(int(conf_obj.lucrative_trend), signal[0],
                                                                message.date, channel_abbr, message.id)
                            await self.send_message_by_template(int(conf_obj.lucrative), signal[0],
                                                                message.date, channel_abbr, message.id)
                    urgent_action = signal[0].current_price
                    obj = SignalOrig.objects.filter(
                        symbol=signal[0].pair, techannel__name=channel_abbr).order_by('id').last()
                    if urgent_action == 'activate':
                        'obj buy by market'
                    if urgent_action == 'cancel':
                        'obj sell by market'

    def parse_wcse_message(self, message_text, message_id):
        signals = []
        splitted_info = message_text.splitlines()
        is_new_signal = 'New Signal Created'
        is_signal_activated = 'Signal Activated'
        is_signal_cancelled = 'Signal Cancelled'
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
                possible_entries = splitted_info[entry_index + 1:entry_index + 4]
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

                """ Take only first 6 take profits: """
                profits = profits[:6]
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
        buy_label = 'Entry at: '
        possible_take_profits = ['Sell at: ', 'Targets: ']
        stop_label = 'Stop Loss: '
        pair = 'Coin: '
        current_price = ''
        margin_type = MarginType.CROSSED.value
        position = None
        leverage = 100
        entries = ''
        profits = ''
        stop_loss = ''
        signal_identification = ['Exchange: Binance', 'Exchange: Binance Futures', 'Exchange: ByBit']
        is_signal = any(x in signal_identification for x in splitted_info)
        if not is_signal:
            return
        for line in splitted_info:
            if 'SHORT' in line:
                position = 'SHORT'
            if 'LONG' in line:
                position = 'LONG'
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
        """ Take only first 6 take profits: """
        profits = profits[:6]
        signals.append(SignalModel(pair, current_price, margin_type, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals

    async def parse_margin_whale_channel(self):
        chat_id = int(conf_obj.margin_whales)
        channel_abbr = 'margin_whale'
        async for message in self.client.iter_messages(chat_id, limit=5):
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
        pair = ''
        current_price = ''
        is_margin = False
        position = None
        leverage = 'Leverage : '
        entries = ''
        profits = []
        stop_loss = ''
        if margin_label not in splitted_info[0]:
            return signals.append(SignalModel(pair, current_price, is_margin, position,
                                              leverage, entries, profits, stop_loss, message_id))
        for line in splitted_info:
            if 'LONG' in splitted_info[3]:
                position = 'LONG'
            if 'SHORT' in splitted_info[3]:
                position = 'SHORT'
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
        """ Take only first 5 take profits: """
        profits = profits[:5]
        signals.append(SignalModel(pair, current_price, is_margin, position,
                                   leverage, entries, profits, stop_loss, message_id))
        return signals


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
