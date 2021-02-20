import logging
import urllib.request
import json

logger = logging.getLogger(__name__)


class SignalVerification:
    def get_active_pairs_info(self, pairs):
        pairs_info = []
        signals = []
        for pair_object in pairs:
            if pair_object.entry_points is None or pair_object.take_profits is None:
                return False
            price_json = ''
            try:
                price_json = urllib.request.urlopen(
                    'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_object.pair))
            except:
                usdt_position = pair_object.pair.rfind('USDT')
                btc_position = pair_object.pair.rfind('BTC')
                if btc_position > 0:
                    pair_corrected = pair_object.pair[0: btc_position - 1:] + pair_object.pair[btc_position::]
                    price_json = urllib.request.urlopen(
                        'https://api.binance.com/api/v3/ticker/price?symbol={}'.format(pair_corrected))

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

            current_pair = json.load(price_json)
            pairs_info.append(current_pair)

            entries = self.verify_entry(pair_object, current_pair)
            profits = self.verify_profits(pair_object, current_pair)
            stop_loss = self.verify_stop(pair_object, current_pair)

            logger.debug(f"Pair: {current_pair['symbol']}")
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
            from .models import SignalModel
            signals.append(
                SignalModel(current_pair['symbol'], current_pair['price'], '',
                            pair_object.position, pair_object.leverage, entries, profits, stop_loss,
                            pair_object.msg_id))
        return signals

    def verify_entry(self, pair_object, current_pair_info):
        verified_entries = []
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.entry_points:
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
        pair_object.take_profits = [price for price in pair_object.take_profits if price != '00']
        dot_position = current_pair_info['price'].index('.')
        if dot_position:
            for price in pair_object.take_profits:
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
        if pair_object.stop_loss.find('.') > 0:
            return pair_object.stop_loss
        if dot_position:
            if pair_object.stop_loss.find('.') != dot_position:
                stop_loss = pair_object.stop_loss[:dot_position] + "." + pair_object.stop_loss[dot_position:]
            else:
                stop_loss = pair_object.stop_loss
        return stop_loss
