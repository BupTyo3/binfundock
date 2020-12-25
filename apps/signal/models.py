import logging

from typing import Optional, List, Set, Union, TYPE_CHECKING

from django.db import models, transaction
from django.db.models import QuerySet, Sum, F
from django.utils import timezone

from utils.framework.models import (
    SystemBaseModel,
    get_increased_leading_number,
)
from .base_model import (
    BaseSignal, BaseHistorySignal,
    BaseEntryPoint, BaseTakeProfit,
    BaseSignalOrig, BasePointOrig,
)
from .utils import (
    SignalStatus,
    SignalPosition,
    MarginType,
    calculate_position,
    FORMED_PUSHED__SIG_STATS, SOLD__SIG_STATS,
    FORMED_PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS, PUSHED_BOUGHT_SOLD__SIG_STATS,
    PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS, BOUGHT_SOLD__SIG_STATS, BOUGHT__SIG_STATS,
    ERROR__SIG_STATS,
)
from .exceptions import (
    MainCoinNotServicedError,
    ShortSpotCombinationError,
)
from apps.crontask.utils import get_or_create_crontask
from apps.market.base_model import BaseMarket
from apps.market.models import Market
from apps.market.utils import MarketType
from apps.pair.exceptions import PairNotExistsError
from apps.pair.models import Pair
from apps.techannel.models import Techannel
from binfun.settings import conf_obj
from tools.tools import (
    rou,
    rounded_result,
    debug_input_and_returned,
    subtract_fee,
)

if TYPE_CHECKING:
    from apps.order.models import SellOrder, BuyOrder
    from apps.order.base_model import BaseOrder

logger = logging.getLogger(__name__)

# For typing

QSSellO = Union[QuerySet, List['SellOrder']]
QSBuyO = Union[QuerySet, List['BuyOrder']]
QSBaseO = Union[QuerySet, List['BaseOrder']]


class SignalOrig(BaseSignalOrig):
    _default_leverage = 1
    _default_margin_type = MarginType.ISOLATED.value
    conf = conf_obj

    techannel = models.ForeignKey(to=Techannel,
                                  related_name='signals_orig',
                                  on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField()
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    is_shared = models.BooleanField(default=False)
    is_served = models.BooleanField(default=False)
    position = models.CharField(max_length=32,
                                choices=SignalPosition.choices(),
                                default=SignalPosition.LONG.value, )
    leverage = models.PositiveIntegerField(default=_default_leverage)
    margin_type = models.CharField(max_length=9,
                                   choices=MarginType.choices(),
                                   default=_default_margin_type)
    message_date = models.DateTimeField(default=timezone.now, blank=True)

    techannel: Techannel
    entry_points: 'EntryPoint.objects'
    take_profits: 'TakeProfit.objects'
    symbol: str
    is_shared: bool
    is_served: bool

    objects = models.Manager()

    def __str__(self):
        return f"SignalOrig:{self.pk}:{self.symbol}:{self.techannel.abbr}" \
               f":{self.outer_signal_id}:{self.position}"

    class Meta:
        unique_together = ['techannel', 'outer_signal_id', ]

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.main_coin = self._get_main_coin(self.symbol)
        super().save(*args, **kwargs)

    def _check_if_pair_does_not_exist_in_market(self, market: BaseMarket) -> None:
        pair = Pair.get_pair(self.symbol, market)
        if not pair:
            raise PairNotExistsError(symbol=self.symbol, market=market)

    def _check_inappropriate_position_to_market_type(self, market: BaseMarket) -> None:
        if market.is_spot_market() and self.is_position_short():
            raise ShortSpotCombinationError(signal=self)

    def _create_into_markets_if_auto(self) -> List['Signal']:
        """
        Create Signal for special Markets (if the corresponding flags are enabled)
        """
        res = []
        for market_method in self.techannel.get_market_auto_methods():
            market = market_method()
            if market:
                try:
                    res.append(self.create_market_signal(
                        market=market, trail_stop=self.techannel.auto_trailing_stop))
                except PairNotExistsError as err:
                    logger.warning(f"Signal '{self}' was not created: '{err}'")
        return res

    @classmethod
    def create_signal(cls, symbol: str, techannel_name: str,
                      stop_loss: float, outer_signal_id: int,
                      entry_points: List[float], take_profits: List[float],
                      margin_type: Optional[str] = None,
                      leverage: Optional[int] = None,
                      message_date=timezone.now()):
        """
        Create signal
        """
        sig_orig = cls._create_signal(
            symbol=symbol, techannel_name=techannel_name,
            stop_loss=stop_loss, outer_signal_id=outer_signal_id,
            entry_points=entry_points, take_profits=take_profits,
            leverage=leverage, message_date=message_date, margin_type=margin_type)
        if not sig_orig:
            return
        sig_market_list = sig_orig._create_into_markets_if_auto()
        logger.debug(f"SignalOrig created: '{sig_orig}' and next '{len(sig_market_list)}' "
                     f"Signals: '{sig_market_list}'")
        return sig_orig

    @classmethod
    def update_shared_signal(cls, is_shared: Optional[bool] = False,
                      techannel_name: Optional[str] = None,
                      outer_signal_id: Optional[int] = None):
        """
        Update signal
        """
        techannel, created = Techannel.objects.get_or_create(name=techannel_name)
        sm_obj = SignalOrig.objects.filter(outer_signal_id=outer_signal_id,
                                           techannel=techannel).update(is_shared=is_shared)
        if not sm_obj:
            return
        logger.debug(f"SignalOrig updated: '{sm_obj}'")
        return True

    @classmethod
    @transaction.atomic
    def _create_signal(cls, symbol: str, techannel_name: str,
                       stop_loss: float, outer_signal_id: int,
                       entry_points: List[float], take_profits: List[float],
                       margin_type: Optional[str] = None,
                       leverage: Optional[int] = None,
                       message_date=timezone.now()) -> Optional['SignalOrig']:
        """
        Create signal
        """
        techannel, created = Techannel.objects.get_or_create(name=techannel_name)
        if created:
            logger.debug(f"Telegram channel '{techannel}' was created")
        sm_obj = Signal.objects.filter(outer_signal_id=outer_signal_id, techannel=techannel).first()
        if sm_obj:
            logger.warning(f"SignalOrig '{outer_signal_id}':'{techannel_name}' already exists")
            return
        position = calculate_position(stop_loss, entry_points, take_profits)
        sm_obj = cls.objects.create(
            techannel=techannel,
            symbol=symbol,
            stop_loss=stop_loss,
            outer_signal_id=outer_signal_id,
            position=position,
            leverage=leverage if leverage else cls._default_leverage,
            message_date=message_date,
            margin_type=margin_type if margin_type else cls._default_margin_type)
        for entry_point in entry_points:
            EntryPointOrig.objects.create(signal=sm_obj, value=entry_point)
        for take_profit in take_profits:
            TakeProfitOrig.objects.create(signal=sm_obj, value=take_profit)
        logger.debug(f"SignalOrig '{sm_obj}' has been created successfully")
        return sm_obj

    @transaction.atomic
    def create_market_signal(self, market: BaseMarket, trail_stop: bool = False) -> 'Signal':
        self._check_if_pair_does_not_exist_in_market(market)
        # ValueError if SPOT & SHORT
        self._check_inappropriate_position_to_market_type(market)
        # Set leverage = 1 for Spot Market
        leverage = self._default_leverage if market.is_spot_market() else self.leverage
        signal = Signal.objects.create(
            techannel=self.techannel,
            symbol=self.symbol,
            stop_loss=self.stop_loss,
            outer_signal_id=self.outer_signal_id,
            position=self.position,
            leverage=leverage,
            margin_type=self.margin_type,
            message_date=self.message_date,
            trailing_stop_enabled=trail_stop,
            market=market,
            signal_orig=self,
        )
        for entry_point in self.entry_points.all():
            value = signal.get_not_fractional_price(entry_point.value)
            EntryPoint.objects.create(signal=signal, value=value)
        for take_profit in self.take_profits.all():
            value = signal.get_not_fractional_price(take_profit.value)
            TakeProfit.objects.create(signal=signal, value=value)
        return signal

    def make_signal_served(self, techannel_name: str, outer_signal_id: int):
        """
        Update signal
        """
        techannel, created = Techannel.objects.get_or_create(name=techannel_name)
        sm_obj = SignalOrig.objects.filter(outer_signal_id=outer_signal_id,
                                           techannel=techannel).update(is_served=True)
        if not sm_obj:
            return
        logger.debug(f"SignalOrig updated: '{sm_obj}'")
        return True

    def _get_main_coin(self, symbol) -> str:
        """
        Example:
        symbol = LTCBTC
        if BTC in [conf.all_accessible_main_coins]:
        main_coin = BTC
        """
        for main_coin in self.conf.all_accessible_main_coins:
            if symbol[-len(main_coin):] == main_coin:
                return main_coin
        raise MainCoinNotServicedError


class Signal(BaseSignal):
    _default_leverage = 1
    _default_margin_type = MarginType.ISOLATED.value
    conf = conf_obj

    signal_orig = models.ForeignKey(to=SignalOrig,
                                    related_name='market_signals',
                                    on_delete=models.DO_NOTHING)
    market = models.ForeignKey(to=Market,
                               related_name='signals',
                               on_delete=models.DO_NOTHING)
    techannel = models.ForeignKey(to=Techannel,
                                  related_name='signals',
                                  on_delete=models.DO_NOTHING)
    symbol = models.CharField(max_length=24)
    outer_signal_id = models.PositiveIntegerField()
    main_coin = models.CharField(max_length=16)
    stop_loss = models.FloatField()
    income = models.FloatField(help_text='Profit or Loss', default=0)
    amount = models.FloatField(help_text='Amount of Main Asset', default=0)
    _status = models.CharField(max_length=32,
                               choices=SignalStatus.choices(),
                               default=SignalStatus.NEW.value,
                               db_column='status')
    position = models.CharField(max_length=32,
                                choices=SignalPosition.choices(),
                                default=SignalPosition.LONG.value, )
    leverage = models.PositiveIntegerField(default=_default_leverage)
    margin_type = models.CharField(max_length=9,
                                   choices=MarginType.choices(),
                                   default=_default_margin_type)
    message_date = models.DateTimeField(default=timezone.now, blank=True)
    uninterrupted = models.BooleanField(
        help_text="Flag is unset if the Signal was spoiled by admin",
        default=True)
    trailing_stop_enabled = models.BooleanField(
        default=False,
        help_text="Trail SL if price has become above near EP (LONG) or lower (SHORT)")

    objects = models.Manager()

    entry_points: 'EntryPoint.objects'
    take_profits: 'TakeProfit.objects'
    buy_orders: 'BuyOrder.objects'
    sell_orders: 'SellOrder.objects'
    techannel: Techannel
    market: Market
    symbol: str
    stop_loss: float
    leverage: int
    margin_type: MarginType

    def __str__(self):
        return f"Signal:{self.pk}:{self.symbol}:{self.techannel.abbr}" \
               f":{self.outer_signal_id}:{self.position}:{self.market}"

    class Meta:
        unique_together = ['techannel', 'outer_signal_id', 'market']

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.main_coin = self._get_main_coin(self.symbol)
        super().save(*args, **kwargs)
        if self.pk is None:
            HistorySignal.write_in_history(self, self.status)

    @rounded_result
    def __get_calculated_amount_spot_or_long(self):
        completed_buy_orders = self.__get_completed_buy_orders()
        bought_amount = self.__get_bought_amount(completed_buy_orders)
        return bought_amount

    @rounded_result
    def __get_calculated_amount_short(self):
        completed_sell_orders = self.__get_completed_sell_orders()
        sold_amount = self.__get_sold_amount(completed_sell_orders)
        return sold_amount

    @rounded_result
    def __get_calculated_income_spot_or_long(self):
        completed_buy_orders = self.__get_completed_buy_orders()
        bought_amount = self.__get_bought_amount(completed_buy_orders)
        completed_sell_orders = self.__get_completed_sell_orders()
        sold_amount = self.__get_sold_amount(completed_sell_orders)
        sold_amount_subtracted_fee = subtract_fee(sold_amount, self.get_market_fee())
        res = sold_amount_subtracted_fee - bought_amount
        logger.debug(f"Income calculating for Signal '{self}': COMPLETED_BUY_ORDERS: {completed_buy_orders}; "
                     f"COMPLETED_SELL_ORDERS: {completed_sell_orders}; "
                     f"BOUGHT_amount={bought_amount}; SOLD_AMOUNT={sold_amount}; "
                     f"SOLD_AMOUNT_SUBTRACTED_FEE={sold_amount_subtracted_fee}; "
                     f"INCOME={rou(res)}")
        return res

    @rounded_result
    def __get_calculated_income_short(self):
        completed_sell_orders = self.__get_completed_sell_orders()
        completed_buy_orders = self.__get_completed_buy_orders()
        bought_amount = self.__get_bought_amount(completed_buy_orders)
        sold_amount = self.__get_sold_amount(completed_sell_orders)
        bought_amount_subtracted_fee = subtract_fee(bought_amount, self.get_market_fee())
        res = sold_amount - bought_amount_subtracted_fee
        logger.debug(f"[SHORT] Income calculating for Signal '{self}': COMPLETED_SELL_ORDERS: {completed_sell_orders}; "
                     f"COMPLETED_BUY_ORDERS: {completed_buy_orders}; "
                     f"SOLD_AMOUNT={sold_amount}; BOUGHT_AMOUNT={bought_amount}; "
                     f"BOUGHT_AMOUNT_SUBTRACTED_FEE={bought_amount_subtracted_fee}; "
                     f"INCOME={rou(res)}")
        return res

    def _update_income(self):
        if self.is_position_short():
            self.income = self.__get_calculated_income_short()
        else:
            self.income = self.__get_calculated_income_spot_or_long()
        self.save()

    def _update_amount(self):
        if self.is_position_short():
            self.amount = self.__get_calculated_amount_short()
        else:
            self.amount = self.__get_calculated_amount_spot_or_long()
        self.save()

    def _get_main_coin(self, symbol) -> str:
        """
        Example:
        symbol = LTCBTC
        if BTC in [conf.accessible_main_coins]:
        main_coin = BTC
        """
        for main_coin in self.conf.accessible_main_coins:
            if symbol[-len(main_coin):] == main_coin:
                return main_coin
        raise MainCoinNotServicedError

    def _is_market_type_futures(self) -> bool:
        return True if self.market.logic.type == MarketType.FUTURES.value else False

    def _is_market_type_spot(self) -> bool:
        return True if self.market.logic.type == MarketType.SPOT.value else False

    def __get_distribution_by_entry_points(self):
        return self.entry_points.count()

    def __get_distribution_by_take_profits(self):
        return self.take_profits.count()

    def _get_current_balance_of_main_coin(self, fake_balance: Optional[float] = None):
        if fake_balance is not None:
            logger.debug(f"FAKE BALANCE: '{fake_balance}'")
            return fake_balance
        return self.market_logic.get_current_balance(self.main_coin)

    def _get_current_price(self):
        return self.market_logic.get_current_price(self.symbol)

    def get_market_fee(self):
        return self.market_logic.market_fee

    def _get_pair(self):
        return Pair.get_pair(self.symbol, self.market)

    @debug_input_and_returned
    @rounded_result
    def __get_turnover_by_coin_pair(self, fake_balance: Optional[float] = None) -> float:
        """Turnover for one Signal.
        How much money we allocate for one Signal
        If free_balance 1000 usd, 10% - config parameter, so
         result will be 100 usd"""
        res = (self._get_current_balance_of_main_coin(fake_balance=fake_balance) *
               self.techannel.balance_to_signal_perc /
               self.conf.one_hundred_percent)
        return res
        # return res / n_distribution  # эквивалент 33 долларов

    @staticmethod
    @rounded_result
    def __find_not_fractional_by_step(value: float, step: float) -> float:
        """
        Round by Market rules
        Example:
        value = 0.123456
        pair.step_price = 0.001
        res = 0.123
        """
        # For python specific [1.9//0.1*0.1 = 1.8]
        # [1.90000001//0.1*0.1 = 1.90000001]
        # we want 1.9, but not 1.8
        one_satoshi = 0.00000001
        value += one_satoshi
        return (value // step) * step

    @debug_input_and_returned
    @rounded_result
    def get_not_fractional_price(self, price: float):
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(price, pair.step_price)

    @debug_input_and_returned
    @rounded_result
    def _get_distributed_toc_quantity_spot_or_long(self,
                                                   entry_point_price: float,
                                                   fake_balance: Optional[float] = None) -> float:
        """
        Calculate quantity for one coin
        Fraction by step
        """
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        toc = self.__get_turnover_by_coin_pair(fake_balance=fake_balance) * self.leverage
        logger.debug(f"TOC = {toc} (leverage = {self.leverage})")
        quantity = toc / self.__get_distribution_by_entry_points()
        coin_quantity = convert_to_coin_quantity(quantity, entry_point_price)
        return self.__find_not_fractional_by_step(coin_quantity, step_quantity)

    @debug_input_and_returned
    @rounded_result
    def _get_distributed_toc_quantity_short(self,
                                            entry_point_price: float,
                                            fake_balance: Optional[float] = None) -> float:
        """
        [SHORT]
        Calculate quantity for one coin
        Fraction by step
        """
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        toc = self.__get_turnover_by_coin_pair(fake_balance=fake_balance) * self.leverage
        logger.debug(f"TOC = {toc} (leverage = {self.leverage})")
        quantity = toc / self.__get_distribution_by_take_profits()
        coin_quantity = convert_to_coin_quantity(quantity, entry_point_price)
        return self.__find_not_fractional_by_step(coin_quantity, step_quantity)

    @rounded_result
    def _get_distributed_toc_quantity(self,
                                      entry_point_price: float,
                                      fake_balance: Optional[float] = None) -> float:
        """
        Calculate quantity for one coin
        Fraction by step
        """
        if self.is_position_short():
            return self._get_distributed_toc_quantity_short(
                entry_point_price=entry_point_price,
                fake_balance=fake_balance)
        else:
            # SPOT OR LONG
            return self._get_distributed_toc_quantity_spot_or_long(
                entry_point_price=entry_point_price,
                fake_balance=fake_balance)

    @rounded_result
    def _get_distributed_quantity_by_take_profits(self, all_quantity: float) -> float:
        """
        Get distributed sell quantity.
        Fraction by step
        """
        pair = self._get_pair()
        # TODO: Check, may be should change to step_quantity = pair.step_price
        step_quantity = pair.step_quantity
        quantity = all_quantity / self.__get_distribution_by_take_profits()
        return self.__find_not_fractional_by_step(quantity, step_quantity)

    @rounded_result
    def _get_distributed_quantity_by_entry_points(self, all_quantity: float) -> float:
        """
        [SHORT] Get distributed buy quantity.
        Fraction by step
        """
        pair = self._get_pair()
        # TODO: Check, may be should change to step_quantity = pair.step_price
        step_quantity = pair.step_quantity
        quantity = all_quantity / self.__get_distribution_by_entry_points()
        return self.__find_not_fractional_by_step(quantity, step_quantity)

    @debug_input_and_returned
    @rounded_result
    def _get_residual_quantity(self, ignore_fee: bool = False) -> float:
        """
        Get residual quantity.
        return: (bought_quantity - sold_quantity)
        Fraction by step
        """
        if self.is_position_short():
            return self._get_residual_quantity_short(ignore_fee=ignore_fee)
        else:
            return self._get_residual_quantity_long(ignore_fee=ignore_fee)

    @debug_input_and_returned
    @rounded_result
    def _get_residual_quantity_long(self, ignore_fee: bool = False) -> float:
        """
        Get residual quantity.
        return: (bought_quantity - sold_quantity)
        Fraction by step
        """
        completed_buy_orders = self.__get_completed_buy_orders()
        if not completed_buy_orders:
            return 0
        bought_quantity = self.__get_bought_quantity(worked_orders=completed_buy_orders, ignore_fee=ignore_fee)
        completed_sell_orders = self.__get_completed_sell_orders()
        sold_quantity = self.__get_sold_quantity(completed_sell_orders)
        residual_quantity = bought_quantity - sold_quantity if sold_quantity else bought_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        return self.__find_not_fractional_by_step(residual_quantity, step_quantity)

    @debug_input_and_returned
    @rounded_result
    def _get_residual_quantity_short(self, ignore_fee: bool = False) -> float:
        """
        Get residual quantity.
        return: (sold_quantity - bought_quantity)
        Fraction by step
        """
        completed_sell_orders = self.__get_completed_sell_orders()
        if not completed_sell_orders:
            return 0
        completed_buy_orders = self.__get_completed_buy_orders()
        sold_quantity = self.__get_sold_quantity(completed_sell_orders)
        bought_quantity = self.__get_bought_quantity(worked_orders=completed_buy_orders, ignore_fee=ignore_fee)
        residual_quantity = sold_quantity - bought_quantity if bought_quantity else sold_quantity
        pair = self._get_pair()
        step_quantity = pair.step_quantity
        return self.__find_not_fractional_by_step(residual_quantity, step_quantity)

    @debug_input_and_returned
    def __form_buy_order(self, distributed_toc: float,
                         entry_point: float, index: int,
                         trigger: Optional[float] = None,
                         custom_order_id: Optional[str] = None):
        from apps.order.models import BuyOrder
        order = BuyOrder.form_buy_limit_order(
            market=self.market,
            signal=self,
            quantity=distributed_toc,
            entry_point=entry_point,
            trigger=trigger,
            custom_order_id=custom_order_id,
            index=index)
        return order

    @debug_input_and_returned
    def __form_buy_tp_order(self, quantity: float, price: float, index: int,
                            custom_order_id: Optional[str] = None,
                            trigger_price: Optional[float] = None) -> 'BuyOrder':
        """
        Form BUY TP order for the signal [SHORT]
        """
        from apps.order.models import BuyOrder
        logger.debug(f"Form TP BUY ORDER for signal {self}")
        order = BuyOrder.form_buy_tp_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
            index=index,
            custom_order_id=custom_order_id,
            trigger_price=trigger_price,
        )
        return order

    @debug_input_and_returned
    def __form_buy_market_order(self, quantity: float, price: float) -> 'BuyOrder':
        """
        Form BUY MARKET order for the signal
        """
        from apps.order.models import BuyOrder
        logger.debug(f"Form MARKET BUY ORDER for signal {self}")
        order = BuyOrder.form_buy_market_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
        )
        return order

    @debug_input_and_returned
    def __form_oco_sell_order(self, distributed_quantity: float,
                              take_profit: float, index: int, stop_loss_trigger: Optional[float] = None,
                              custom_order_id: Optional[str] = None) -> 'SellOrder':
        """
        Form sell oco order for the signal
        """
        from apps.order.models import SellOrder
        msg = f"Form SELL ORDER for signal {self}"
        if stop_loss_trigger is not None:
            msg += f" with UPDATED STOP_LOSS: '{stop_loss_trigger}'"
        logger.debug(msg)
        order = SellOrder.form_sell_oco_order(
            market=self.market,
            signal=self,
            quantity=distributed_quantity,
            take_profit=take_profit,
            stop_loss_trigger=self.stop_loss if stop_loss_trigger is None else stop_loss_trigger,
            custom_order_id=custom_order_id,
            index=index
        )
        return order

    @debug_input_and_returned
    def __form_sell_market_order(self, quantity: float, price: float) -> 'SellOrder':
        """
        Form sell market order for the signal
        """
        from apps.order.models import SellOrder
        logger.debug(f"Form MARKET SELL ORDER for signal {self}")
        order = SellOrder.form_sell_market_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
        )
        return order

    @debug_input_and_returned
    def __form_sell_tp_order(self, quantity: float, price: float, index: int,
                             custom_order_id: Optional[str] = None,
                             trigger_price: Optional[float] = None) -> 'SellOrder':
        """
        Form sell limit order for the signal
        """
        from apps.order.models import SellOrder
        logger.debug(f"Form TP SELL ORDER for signal {self}")
        order = SellOrder.form_sell_tp_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
            index=index,
            custom_order_id=custom_order_id,
            trigger_price=trigger_price,
        )
        return order

    @debug_input_and_returned
    def __form_sell_limit_order(self, quantity: float, price: float, index: int,
                                custom_order_id: Optional[str] = None) -> 'SellOrder':
        """
        Form sell limit order for the signal
        """
        from apps.order.models import SellOrder
        logger.debug(f"Form SELL LIMIT ORDER for signal {self}")
        order = SellOrder.form_sell_limit_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
            index=index,
            custom_order_id=custom_order_id,
        )
        return order

    @debug_input_and_returned
    def __form_sell_gl_sl_order(self, quantity: float, price: float,
                                original_order_id: Optional[int] = None) -> 'SellOrder':
        """
        Form Global Sell Stop_loss order for the signal
        """
        from apps.order.models import SellOrder
        logger.debug(f"Form SELL GL SL ORDER for signal {self}")
        custom_order_id = None
        if original_order_id:
            original_order = SellOrder.objects.filter(id=original_order_id).first()
            custom_order_id = get_increased_leading_number(original_order.custom_order_id)
        order = SellOrder.form_sell_gl_sl_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
            custom_order_id=custom_order_id,
        )
        return order

    @debug_input_and_returned
    def __form_buy_gl_sl_order(self, quantity: float, price: float,
                               original_order_id: Optional[int] = None) -> 'BuyOrder':
        """
        Form Global BUY Stop_loss order for the signal
        """
        from apps.order.models import BuyOrder
        logger.debug(f"Form BUY GL SL ORDER for signal {self}")
        custom_order_id = None
        if original_order_id:
            original_order = BuyOrder.objects.filter(id=original_order_id).first()
            custom_order_id = get_increased_leading_number(original_order.custom_order_id)
        order = BuyOrder.form_buy_gl_sl_order(
            market=self.market,
            signal=self,
            quantity=quantity,
            price=price,
            custom_order_id=custom_order_id,
        )
        return order

    @debug_input_and_returned
    @rounded_result
    def __get_amount_quantity(self, fake_balance: Optional[float] = None) -> float:
        toc_quantity = self.__get_turnover_by_coin_pair(fake_balance=fake_balance)
        return toc_quantity / (self.__get_distribution_by_entry_points() * self.__get_distribution_by_take_profits())

    @debug_input_and_returned
    def _check_if_balance_enough_for_signal(self, fake_balance: Optional[float] = None) -> bool:
        """
        Enough for create buy orders and then (after one buy order has worked) - sell orders
        """
        # TODO check
        from tools.tools import convert_to_coin_quantity
        pair = self._get_pair()
        # get amount and subtract fee for buy orders
        amount_quantity = subtract_fee(self.__get_amount_quantity(fake_balance=fake_balance),
                                       self.get_market_fee() * self.__get_distribution_by_entry_points())
        logger.debug(f"'{self}':amount_quantity_subtracted_fee={amount_quantity}")
        if amount_quantity < pair.min_amount:
            logger.debug(f"Bad Check: amount_quantity < min_amount: {amount_quantity} < {pair.min_amount}!")
            return False
        entry_point_price = self.entry_points.last().value
        coin_quantity = convert_to_coin_quantity(amount_quantity, entry_point_price)
        logger.debug(f"'{self}':coin_quantity={coin_quantity}")
        if coin_quantity > pair.min_quantity:
            return True
        logger.debug(f"Bad Check: coin_quantity < min_quantity: {coin_quantity} < {pair.min_quantity}!")
        return False

    @debug_input_and_returned
    def _check_if_quantity_enough_for_sell(self, quantity: float, price: float) -> bool:
        """
        Check if quantity enough for Sell.
        For Futures always True
        """
        # TODO check
        if self._is_market_type_futures():
            # We always can close position in Futures
            return True
        from tools.tools import convert_to_amount
        pair = self._get_pair()
        amount_quantity = convert_to_amount(quantity, price)
        logger.debug(f"'{self}':amount_quantity={amount_quantity}")
        if amount_quantity < pair.min_amount:
            logger.debug(f"Bad Check: amount_quantity < min_amount: {amount_quantity} < {pair.min_amount}!")
            return False
        logger.debug(f"'{self}':coin_quantity={quantity}")
        if quantity > pair.min_quantity:
            return True
        logger.debug(f"Bad Check: coin_quantity < min_quantity: {quantity} < {pair.min_quantity}!")
        return False

    def __second_formation_sell_orders_futures(self, sell_quantity: float) -> None:
        """
        Function for creating Sell orders
        """
        distributed_quantity = self._get_distributed_quantity_by_take_profits(sell_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_sell_tp_order(
                quantity=distributed_quantity,
                price=take_profit.value, index=index)

    def __second_formation_sell_orders_spot(self, sell_quantity: float) -> None:
        """
        Function for creating Sell orders
        """
        distributed_quantity = self._get_distributed_quantity_by_take_profits(sell_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_oco_sell_order(
                distributed_quantity=distributed_quantity,
                take_profit=take_profit.value, index=index)

    def _second_formation_buy_orders_futures_short(self, buy_quantity: float) -> None:
        """
        [SHORT] Function for creating BUY orders
        """
        distributed_quantity = self._get_distributed_quantity_by_take_profits(buy_quantity)
        for index, take_profit in enumerate(self.take_profits.all()):
            self.__form_buy_tp_order(
                quantity=distributed_quantity,
                price=take_profit.value, index=index)

    def _second_formation_sell_orders(self, sell_quantity: float, futures: bool = False) -> None:
        """
        Function for creating Sell orders
        """
        if futures:
            self.__second_formation_sell_orders_futures(sell_quantity=sell_quantity)
        else:
            self.__second_formation_sell_orders_spot(sell_quantity=sell_quantity)

    @rounded_result
    def _get_new_stop_loss_long_or_spot(self, worked_sell_orders: QSSellO) -> float:
        """
        Business logic
        Fraction by step
        """
        last_worked_sell_order = worked_sell_orders.order_by('price').last()
        if last_worked_sell_order.index == 0:
            # if the first sell order has worked, new stop_loss is a max of entry_points
            res = self.entry_points.order_by('value').last().value
            # We increase SL price by slip delta, because
            # to get more profit after getting the first take_profit
            # (more than break even)
            res = self.get_real_stop_price(res, lower=False)
        else:
            # get price of previous order as a new stop_loss
            previous_order = self.sell_orders.filter(index=(last_worked_sell_order.index - 1)).last()
            res = previous_order.price
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_price)

    @rounded_result
    def _get_new_stop_loss_futures_short(self, worked_buy_orders: QSBuyO) -> float:
        """
        Business logic
        Fraction by step
        """
        first_worked_buy_order = worked_buy_orders.order_by('price').first()
        # TODO: CHECK !!!!! Maybe need to change first_formation order
        if first_worked_buy_order.index == 0:
            # if the last buy order has worked, new stop_loss is a min of entry_points
            res = self.entry_points.order_by('value').first().value
            # We decrease SL price by slip delta, because
            # to get more profit after getting the first take_profit
            # (more than break even)
            res = self.get_real_stop_price(res, lower=True)
        else:
            # get price of previous order as a new stop_loss
            # TODO: CHECK !!!! Maybe: .last() -> .first()
            previous_order = self.buy_orders.filter(index=(first_worked_buy_order.index - 1)).last()
            res = previous_order.price
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_price)

    @debug_input_and_returned
    def _formation_copied_buy_orders_futures_short(self,
                                                   original_orders_ids: List[int],
                                                   buy_quantity: Optional[float] = None) -> List['BuyOrder']:
        """
        Form copied Buy orders with new buy_quantity
        """
        res = list()
        original_orders_ids.sort()
        for order_id in original_orders_ids:
            res.append(self._formation_copied_buy_order_futures_short(
                original_order_id=order_id, buy_quantity=buy_quantity))
        return res

    @debug_input_and_returned
    def _formation_copied_sell_order_spot(self,
                                          original_order_id: int,
                                          sell_quantity: Optional[float] = None,
                                          new_stop_loss: Optional[float] = None):
        """
        Form one copied Sell order by original Sell order (with updated quantity or stop_loss)
        """
        from apps.order.models import SellOrder

        order = SellOrder.objects.filter(id=original_order_id).first()
        new_custom_order_id = get_increased_leading_number(order.custom_order_id)
        logger.debug(f"New copied SELL order custom_order_id = '{new_custom_order_id}'")
        new_sell_order = self.__form_oco_sell_order(
            distributed_quantity=sell_quantity if sell_quantity is not None else order.quantity,
            custom_order_id=new_custom_order_id,
            take_profit=order.price,
            index=order.index,
            stop_loss_trigger=order.sl_order.trigger if new_stop_loss is None else new_stop_loss)
        return new_sell_order

    @debug_input_and_returned
    def _formation_copied_sell_orders_spot(self,
                                           original_orders_ids: List[int],
                                           worked_sell_orders: QSSellO,
                                           sell_quantity: Optional[float] = None,
                                           new_stop_loss: Optional[float] = None) -> List['SellOrder']:
        """
        Form copied Sell orders with new stop_loss or new sell_quantity
        """
        if new_stop_loss is None and not sell_quantity:
            new_stop_loss = self._get_new_stop_loss_long_or_spot(worked_sell_orders)
        res = list()
        original_orders_ids.sort()
        for order_id in original_orders_ids:
            res.append(self._formation_copied_sell_order_spot(
                original_order_id=order_id, new_stop_loss=new_stop_loss, sell_quantity=sell_quantity))
        return res

    @debug_input_and_returned
    def _formation_copied_sell_order_futures_long(self,
                                                  original_order_id: int,
                                                  sell_quantity: Optional[float] = None):
        """
        Form one copied Sell order by original Sell order (with updated quantity)
        """
        from apps.order.models import SellOrder

        order = SellOrder.objects.filter(id=original_order_id).first()
        new_custom_order_id = get_increased_leading_number(order.custom_order_id)
        logger.debug(f"New copied SELL order custom_order_id = '{new_custom_order_id}'")
        new_sell_order = self.__form_sell_tp_order(
            custom_order_id=new_custom_order_id,
            quantity=sell_quantity if sell_quantity is not None else order.quantity,
            price=order.price,
            index=order.index,
            trigger_price=order.trigger)
        return new_sell_order

    @debug_input_and_returned
    def _formation_copied_buy_order_futures_short(self,
                                                  original_order_id: int,
                                                  buy_quantity: Optional[float] = None):
        """
        Form one copied Buy order by original Buy order (with updated quantity)
        """
        from apps.order.models import BuyOrder

        order = BuyOrder.objects.filter(id=original_order_id).first()
        new_custom_order_id = get_increased_leading_number(order.custom_order_id)
        logger.debug(f"[SHORT] New copied BUY order custom_order_id = '{new_custom_order_id}'")
        new_buy_order = self.__form_buy_tp_order(
            custom_order_id=new_custom_order_id,
            quantity=buy_quantity if buy_quantity is not None else order.quantity,
            price=order.price,
            index=order.index,
            trigger_price=order.trigger)
        return new_buy_order

    @debug_input_and_returned
    def _formation_copied_sell_orders_futures_long(self,
                                                   original_orders_ids: List[int],
                                                   sell_quantity: Optional[float] = None) -> List['SellOrder']:
        """
        Form copied Sell orders with new stop_loss or new sell_quantity
        """
        res = list()
        original_orders_ids.sort()
        for order_id in original_orders_ids:
            res.append(self._formation_copied_sell_order_futures_long(
                original_order_id=order_id, sell_quantity=sell_quantity))
        return res

    @debug_input_and_returned
    def _formation_copied_sell_orders(self,
                                      original_orders_ids: List[int],
                                      worked_sell_orders: QSSellO,
                                      sell_quantity: Optional[float] = None,
                                      new_stop_loss: Optional[float] = None,
                                      futures: bool = False) -> List['SellOrder']:
        if futures:
            return self._formation_copied_sell_orders_futures_long(
                original_orders_ids=original_orders_ids,
                sell_quantity=sell_quantity)
        else:
            return self._formation_copied_sell_orders_spot(
                original_orders_ids=original_orders_ids,
                worked_sell_orders=worked_sell_orders,
                sell_quantity=sell_quantity,
                new_stop_loss=new_stop_loss)

    def __get_not_handled_worked_buy_orders(self,
                                            excluded_indexes: Optional[List[int]] = None) -> QSBuyO:
        """
        Function to get not handled worked Buy orders
        """
        # TODO: maybe move to orders
        from apps.order.models import BuyOrder
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        params = {
            'signal': self,
            'handled_worked': False,
            'local_canceled': False,
            '_status__in': COMPLETED_ORDER_STATUSES,
        }
        qs = BuyOrder.objects.filter(**params)
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    def __get_not_handled_worked_sell_orders(self,
                                             sl_orders: bool = False,
                                             tp_orders: bool = False,
                                             excluded_indexes: Optional[List[int]] = None) -> QSSellO:
        """
        Function to get not handled worked Sell orders
        For FUTURES provide:
        sl_orders=True, tp_orders=True
        """
        # TODO: maybe move to orders
        from apps.order.models import SellOrder
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        params = {
            'signal': self,
            'handled_worked': False,
            'local_canceled': False,
            '_status__in': COMPLETED_ORDER_STATUSES,
        }
        qs = SellOrder.objects.filter(**params)
        qs = qs.exclude(sl_order=None) if not sl_orders else qs
        qs = qs.exclude(tp_order=None) if not tp_orders else qs
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    @debug_input_and_returned
    def __get_opened_buy_orders(self, statuses: Optional[List] = None,
                                excluded_indexes: Optional[List[int]] = None) -> QSBuyO:
        """
        Function to get sent Buy orders
        """
        # TODO: maybe move to orders
        from apps.order.utils import OPENED_ORDER_STATUSES
        from apps.order.models import BuyOrder
        statuses = OPENED_ORDER_STATUSES if not statuses else statuses
        params = {
            'signal': self,
            'local_canceled': False,
            '_status__in': statuses
        }
        qs = BuyOrder.objects.filter(**params)
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    @debug_input_and_returned
    def __get_opened_sell_orders(self,
                                 statuses: Optional[List] = None,
                                 excluded_indexes: Optional[List[int]] = None) -> QSSellO:
        """
        Function to get sent Sell orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [SENT, NOT_SENT]
        from apps.order.utils import OPENED_ORDER_STATUSES
        from apps.order.models import SellOrder
        statuses = OPENED_ORDER_STATUSES if not statuses else statuses
        params = {
            'signal': self,
            'local_canceled': False,
            'no_need_push': False,
            '_status__in': statuses
        }
        qs = SellOrder.objects.filter(**params)
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    def __get_gl_sl_sell_orders(self, statuses: Optional[List] = None) -> QSSellO:
        from apps.order.models import SellOrder
        params = {
            'signal': self,
            'local_canceled': False,
            'handled_worked': False,
            'index': SellOrder.GL_SM_INDEX,
        }
        if statuses:
            params.update({'_status__in': statuses})
        return SellOrder.objects.filter(**params)

    def __get_gl_sl_buy_orders(self, statuses: Optional[List] = None):
        from apps.order.models import BuyOrder
        params = {
            'signal': self,
            'local_canceled': False,
            'handled_worked': False,
            'index': BuyOrder.GL_SM_INDEX,
        }
        if statuses:
            params.update({'_status__in': statuses})
        return BuyOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_sell_orders_exclude_indexes(self, excluded_indexes: Optional[List[int]] = None):
        qs = self.sell_orders
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    @debug_input_and_returned
    def __get_buy_orders_exclude_indexes(self, excluded_indexes: Optional[List[int]] = None):
        qs = self.buy_orders
        if not excluded_indexes:
            return qs
        for index in excluded_indexes:
            qs = qs.exclude(index=index)
        return qs

    @debug_input_and_returned
    def __get_completed_sell_orders(self) -> QSSellO:
        """
        Function to get Completed Sell orders
        """
        # TODO: maybe move to orders
        from apps.order.models import SellOrder
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        params = {
            'signal': self,
            '_status__in': COMPLETED_ORDER_STATUSES,
        }
        return SellOrder.objects.filter(**params)

    @debug_input_and_returned
    def __get_completed_buy_orders(self) -> QSBuyO:
        """
        Function to get Completed Buy orders
        """
        # TODO: maybe move to orders
        # TODO: maybe _status__in: [COMPLETED, PARTIAL]
        from apps.order.models import BuyOrder
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        params = {
            'signal': self,
            # TODO: check these cases
            # 'local_canceled': False,
            '_status__in': COMPLETED_ORDER_STATUSES,
        }
        return BuyOrder.objects.filter(**params)

    @staticmethod
    def __update_flag_handled_worked_buy_orders(worked_orders: QSBuyO):
        """
        Set flag handled_worked
        """
        # TODO: move it
        from apps.order.models import BuyOrder
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders_ids = list(worked_orders.all().values_list('id', flat=True))
        for order_id in worked_orders_ids:
            order = BuyOrder.objects.filter(id=order_id).first()
            order.handled_worked = True
            order.save()

    @staticmethod
    def __update_flag_handled_worked_sell_orders(worked_orders: QSSellO):
        """
        Set flag handled_worked
        """
        # TODO: move it
        from apps.order.models import SellOrder
        logger.debug(f"Updating Worked orders by handled_worked flag")
        worked_orders_ids = list(worked_orders.all().values_list('id', flat=True))
        for order_id in worked_orders_ids:
            order = SellOrder.objects.filter(id=order_id).first()
            order.handled_worked = True
            order.save()

    @staticmethod
    @debug_input_and_returned
    def __cancel_sent_buy_orders(sent_orders: QSBuyO):
        """
        Set flag local_cancelled for orders.
        The orders are ready to cancel
        """
        # TODO: move it
        from apps.order.models import BuyOrder
        logger.debug(f"Updating Sent orders by local_canceled flag")
        logger.debug(f"LOCAL CANCEL ORDERS: '{sent_orders}'")
        sent_orders_ids = list(sent_orders.all().values_list('id', flat=True))
        now_ = timezone.now()
        for order_id in sent_orders_ids:
            order = BuyOrder.objects.filter(id=order_id).first()
            order.local_canceled = True
            order.local_canceled_time = now_
            order.save()

    @staticmethod
    @debug_input_and_returned
    def __cancel_sent_sell_orders(sent_orders: QSSellO):
        """
        Set flag local_cancelled for orders.
        The orders are ready to cancel
        """
        # TODO: move it
        from apps.order.models import SellOrder
        logger.debug(f"Updating Sent orders by local_canceled flag")
        logger.debug(f"LOCAL CANCEL ORDERS: '{sent_orders}'")
        sent_orders_ids = list(sent_orders.all().values_list('id', flat=True))
        now_ = timezone.now()
        for order_id in sent_orders_ids:
            order = SellOrder.objects.filter(id=order_id).first()
            order.local_canceled = True
            order.local_canceled_time = now_
            order.save()

    @debug_input_and_returned
    @rounded_result
    def __get_bought_quantity(self, worked_orders: QSBuyO, ignore_fee: bool = False) -> float:
        """
        Get Sum of bought_quantity of worked Buy orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('bought_quantity'))
        bought_quantity = res['bought_quantity__sum'] or 0
        res = subtract_fee(bought_quantity, self.get_market_fee()) if not ignore_fee else bought_quantity
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_quantity)

    @debug_input_and_returned
    @rounded_result
    def __get_bought_amount(self, worked_orders: QSBuyO) -> float:
        """
        """
        # TODO: move it
        qs = worked_orders.annotate(bought_amount=F('price') * F('bought_quantity'))
        return qs.aggregate(Sum('bought_amount'))['bought_amount__sum'] or 0

    @staticmethod
    @rounded_result
    def __get_sold_amount(worked_orders: QSSellO) -> float:
        """
        """
        # TODO: move it
        qs = worked_orders.annotate(sold_amount=F('price') * F('sold_quantity'))
        return qs.aggregate(Sum('sold_amount'))['sold_amount__sum'] or 0

    @staticmethod
    @rounded_result
    def __get_sold_quantity(worked_orders: QSSellO) -> float:
        """
        Get Sum of quantity of orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('sold_quantity'))
        return res['sold_quantity__sum'] or 0

    @staticmethod
    @debug_input_and_returned
    @rounded_result
    def __get_planned_executed_quantity(worked_orders: QSBaseO) -> float:
        """
        Get Sum of quantity of orders
        """
        # TODO: move it
        res = worked_orders.aggregate(Sum('quantity'))
        return res['quantity__sum']

    @debug_input_and_returned
    @rounded_result
    def __calculate_new_executed_quantity(self,
                                          sent_orders: QSBaseO,
                                          addition_quantity: float) -> float:
        """Calculate new bought_quantity by sent_sell_orders and addition_quantity
         (bought quantity of worked buy orders).
        Fraction by step
         """
        all_quantity = self.__get_planned_executed_quantity(sent_orders) + addition_quantity
        res = all_quantity / sent_orders.count()
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_quantity)

    @staticmethod
    def __exclude_sl_or_tp_orders(main_orders: QSSellO, worked_orders: QSSellO) -> QSSellO:
        """Exclude paired orders
        e.g.:
        main_orders = [order_1_tp, order_1_sl, order_2_tp]
        worked_orders = [order_2_sl]
        return: [order_1_tp, order_1_sl]
        """
        worked_sl_orders = worked_orders.exclude(sl_order=None).values('sl_order')
        worked_tp_orders = worked_orders.exclude(tp_order=None).values('tp_order')
        main_orders = main_orders.exclude(id__in=worked_sl_orders)
        main_orders = main_orders.exclude(id__in=worked_tp_orders)
        return main_orders

    def _cancel_opened_orders(self, buy: bool = False, sell: bool = False):
        if buy:
            opened_buy_orders = self.__get_opened_buy_orders()
            # Cancel all buy_orders
            if opened_buy_orders:
                self.__cancel_sent_buy_orders(opened_buy_orders)
        if sell:
            opened_sell_orders = self.__get_opened_sell_orders()
            if opened_sell_orders:
                # Cancel opened sell_orders and form sell_market order
                self.__cancel_sent_sell_orders(opened_sell_orders)

    @debug_input_and_returned
    def _check_is_ready_to_be_closed(self) -> bool:
        """
        Check Signal if it has no opened Buy orders and no opened Sell orders
        """
        from apps.order.utils import OrderStatus
        not_finished_orders_statuses = [
            OrderStatus.NOT_SENT.value,
            OrderStatus.SENT.value,
            OrderStatus.PARTIAL.value,
        ]
        not_finished_orders_params = {
            '_status__in': not_finished_orders_statuses,
        }
        if self.buy_orders.filter(**not_finished_orders_params).exists():
            return False
        logger.debug(f"1/2:Signal '{self}' has no Opened BUY orders")
        if self.sell_orders.filter(**not_finished_orders_params).exists():
            return False
        logger.debug(f"2/2:Signal '{self}' has no Opened SELL orders")
        return True

    @debug_input_and_returned
    def _close(self):
        """
        Function to close the Signal
        """
        logger.debug(f"Signal '{self}' will be closed")
        self.status = SignalStatus.CLOSED.value
        self.save()

    # POINT SPOIL

    @debug_input_and_returned
    # @transaction.atomic
    def _spoil(self, force: bool = False):
        ignore_fee = True if self._is_market_type_futures() else False
        self._cancel_opened_orders(buy=True, sell=True)
        residual_quantity = self._get_residual_quantity(ignore_fee=ignore_fee)
        price = self._get_current_price()
        if residual_quantity > 0 and\
                self._check_if_quantity_enough_for_sell(quantity=residual_quantity, price=price):
            if self.is_position_short():
                self.__form_buy_market_order(quantity=residual_quantity, price=price)
            else:
                self.__form_sell_market_order(quantity=residual_quantity, price=price)
        else:
            logger.debug(f"No RESIDUAL QUANTITY for Signal '{self}'")
        if force:
            # Set flag because admin decided to spoil the signal
            self.uninterrupted = False
        self.status = SignalStatus.CANCELING.value
        self.save()

    # POINT FIRST FORMATION

    def _first_formation_futures_long_orders(self, fake_balance: Optional[float] = None) -> bool:
        """
        FUTURES Market
        LONG Position
        """
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(
                entry_point_price=entry_point.value,
                fake_balance=fake_balance)
            if not coin_quantity:
                logger.debug(f"Not enough amount for Signal: '{self}'")
                return False
            # TODO: Form buy orders
            self.__form_buy_order(distributed_toc=coin_quantity, entry_point=entry_point.value, index=index)
        # self.__form_futures_sl_order()
        # Create Global Stop_loss Order
        planned_executed_quantity = self.__get_planned_executed_quantity(self.buy_orders.all())
        self.__form_sell_gl_sl_order(quantity=planned_executed_quantity, price=self.stop_loss)
        return True

    def _first_formation_futures_short_orders(self, fake_balance: Optional[float] = None) -> bool:
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(
                entry_point_price=entry_point.value,
                fake_balance=fake_balance)
            if not coin_quantity:
                logger.debug(f"Not enough amount for Signal: '{self}'")
                return False
            # TODO: Form TP sell orders
            self.__form_sell_limit_order(quantity=coin_quantity, price=entry_point.value, index=index)
        planned_executed_quantity = self.__get_planned_executed_quantity(self.sell_orders.all())
        self.__form_buy_gl_sl_order(quantity=planned_executed_quantity, price=self.stop_loss)
        return True

    def _first_formation_futures_orders(self, fake_balance: Optional[float] = None):
        """
        FUTURES Market
        """
        if not self._get_pair():
            logger.warning(f"Pair {self.symbol} does not exist in Futures")
            return
        if self.is_position_short():
            logger.debug(f"Form Futures SHORT: '{self}'")
            is_success = self._first_formation_futures_short_orders(fake_balance=fake_balance)
        else:
            logger.debug(f"Form Futures LONG: '{self}'")
            is_success = self._first_formation_futures_long_orders(fake_balance=fake_balance)
        if is_success:
            self.status = SignalStatus.FORMED.value
            self.save()
        return is_success

    def _first_formation_spot_orders(self, fake_balance: Optional[float] = None) -> bool:
        """
        SPOT Market
        """
        if not self._check_if_balance_enough_for_signal(fake_balance=fake_balance):
            # TODO: Add sent message to yourself telegram
            logger.debug(f"Not enough amount for Signal '{self}'")
            return False
        self.status = SignalStatus.FORMED.value
        for index, entry_point in enumerate(self.entry_points.all()):
            coin_quantity = self._get_distributed_toc_quantity(
                entry_point_price=entry_point.value,
                fake_balance=fake_balance)
            if not coin_quantity:
                logger.debug(f"Not enough amount for Signal '{self}'")
                return False
            self.__form_buy_order(distributed_toc=coin_quantity, entry_point=entry_point.value, index=index)
        self.save()
        return True

    # POINT PUSH JOB

    @debug_input_and_returned
    def _push_spot_orders(self):
        """
        SPOT Market
        Function for interaction with the Real Market
        1)Cancel NOT_SENT local_cancelled Buy orders
        2)Sent request for local_cancelled SENT Buy orders
        3)Cancel NOT_SENT local_cancelled Sell orders
        4)Sent request for local_cancelled SENT Sell orders
        5)Sent request to create real Sell orders (NOT_SENT -> SENT)
        6)Sent request to create real Buy orders (NOT_SENT -> SENT)
        7)Change Signal status (NEW -> PUSHED) if this is the first launch

        """
        from apps.order.utils import OrderStatus
        cancelled_params = {
            'local_canceled': True,
        }
        no_need_push_params = {
            'no_need_push': False,
        }
        not_sent_params = {
            '_status__in': [OrderStatus.NOT_SENT.value, ]
        }
        sent_params = {
            '_status__in': [OrderStatus.SENT.value,
                            OrderStatus.PARTIAL.value]
        }
        # cancel NOT_SENT local_cancelled BUY orders
        for local_cancelled_order in self.buy_orders.filter(
                **cancelled_params).filter(**not_sent_params):
            local_cancelled_order.cancel_not_sent_order()
        # cancel SENT local_cancelled BUY orders
        for local_cancelled_order in self.buy_orders.filter(
                **cancelled_params).filter(**sent_params).filter(**no_need_push_params):
            local_cancelled_order.cancel_into_market()
        # cancel NOT_SENT local_cancelled SELL orders
        for local_cancelled_order in self.sell_orders.filter(
                **cancelled_params).filter(**not_sent_params):
            local_cancelled_order.cancel_not_sent_order()
        # cancel SENT local_cancelled SELL orders
        for local_cancelled_order in self.sell_orders.filter(
                **cancelled_params).filter(**sent_params).filter(**no_need_push_params):
            local_cancelled_order.cancel_into_market()
        orders_params_for_pushing = {
            '_status': OrderStatus.NOT_SENT.value,
            'local_canceled': False,
            'no_need_push': False,
        }
        # push NOT_SENT SELL orders
        # TODO: Maybe move both try except into market.models
        from binance.exceptions import BinanceAPIException
        error_status_flag = False
        for sell_order in self.sell_orders.filter(**orders_params_for_pushing):
            try:
                sell_order.push_to_market()
            except BinanceAPIException as ex:
                error_status_flag = True
                logger.warning(f"Push order Error: Signal:'{self}' Order: '{sell_order}': Ex: '{ex}'")
        # push NOT_SENT BUY orders
        for buy_order in self.buy_orders.filter(**orders_params_for_pushing):
            try:
                buy_order.push_to_market()
            except BinanceAPIException as ex:
                error_status_flag = True
                logger.warning(f"Push order Error: Signal:'{self}' Order: '{buy_order}': Ex: '{ex}'")
            # set status if at least one order has created
            if not error_status_flag and self.status not in PUSHED_BOUGHT_SOLD__SIG_STATS:
                self.status = SignalStatus.PUSHED.value
                self.save()
        if error_status_flag and self.status not in ERROR__SIG_STATS:
            self.status = SignalStatus.ERROR.value
            self.save()

    @debug_input_and_returned
    def _push_futures_orders(self):
        self._push_spot_orders()

    # POINT BOUGHT WORKER

    @debug_input_and_returned
    # @transaction.atomic
    def _bought_worker_spot(self, futures: bool = False):
        """
        SPOT Market
        Worker for one signal.
        Run if at least one Buy order has worked.
        1)Create Sell orders if no one exists
        2)Recreate Sent Sell orders with updated quantity
        """
        from apps.order.models import SellOrder
        # TODO: maybe change name to bought_worker and remove method bought_worker_futures
        worked_orders = self.__get_not_handled_worked_buy_orders()
        if not worked_orders:
            return
        ignore_fee = True if futures else False
        bought_quantity = self.__get_bought_quantity(worked_orders=worked_orders, ignore_fee=ignore_fee)
        logger.debug(f"Calculate quantity for Sell order: Bought_quantity = {bought_quantity}")
        # TODO: Add logic recreating existing sell orders with updated quantity
        # Recreating opened sent sell orders with new quantity
        if futures:
            opened_sell_orders = self.__get_opened_sell_orders(excluded_indexes=[SellOrder.GL_SM_INDEX, ])
        else:
            opened_sell_orders = self.__get_opened_sell_orders()
        if opened_sell_orders:
            new_bought_quantity = self.__calculate_new_executed_quantity(opened_sell_orders, bought_quantity)
            copied_sent_sell_orders_ids = list(opened_sell_orders.all().values_list('id', flat=True))
            self.__cancel_sent_sell_orders(opened_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_orders,
                                               sell_quantity=new_bought_quantity,
                                               futures=futures)
        # Form sell orders if the signal doesn't have any
        elif not self.__get_sell_orders_exclude_indexes(excluded_indexes=[SellOrder.GL_SM_INDEX, ]).exists():
            self._second_formation_sell_orders(sell_quantity=bought_quantity, futures=futures)
        self.__update_flag_handled_worked_buy_orders(worked_orders)
        # Change status
        if self.status not in BOUGHT_SOLD__SIG_STATS:
            self.status = SignalStatus.BOUGHT.value
            self.save()

    @debug_input_and_returned
    def _bought_worker_futures(self):
        """
        FUTURES Market
        """
        if self.is_position_short():
            logger.debug(f"Form Futures SHORT: '{self}'")
            self._bought_worker_futures_short()
        else:
            logger.debug(f"Form Futures LONG: '{self}'")
            self._bought_worker_futures_long()

    @debug_input_and_returned
    # @transaction.atomic
    def _bought_worker_futures_long(self):
        """
        FUTURES Market
        """
        # TODO: CHECK LOGIC
        self._bought_worker_spot(futures=True)

    def _bought_worker_futures_short(self):
        """
        [SHORT] FUTURES Market
        Worker for one signal.
        Run if at least one BUY order has worked.
        1.GL SL (SELL) order has worked:
          1)Cancel all opened TP BUY orders
        2.At least one BUY order has worked
          1)Cancel BUY orders
          2)Recreating opened (sent) BUY GL SL order with updated price
          3)Cancel BUY GL SL order if there are no opened_buy_orders
        """
        from apps.order.models import BuyOrder
        from apps.order.utils import OPENED_ORDER_STATUSES
        # TODO: change this function (remove tp_orders, sl_orders). Make it is more universal
        self.__try_cancel_opened_orders_if_gl_sl_buy_order_has_been_worked()

        worked_tp_orders = self.__get_not_handled_worked_buy_orders(excluded_indexes=[BuyOrder.GL_SM_INDEX, ])
        if not worked_tp_orders:
            return
        # #################### check _sold_worker_spot  (sell=True or buy=True)
        self._cancel_opened_orders(sell=True)
        opened_buy_orders = self.__get_opened_buy_orders(excluded_indexes=[BuyOrder.GL_SM_INDEX, ])
        # Recreating opened sent buy orders with new stop_loss
        opened_gl_sl_orders = self.__get_gl_sl_buy_orders(statuses=OPENED_ORDER_STATUSES)
        if opened_gl_sl_orders.exists():
            opened_gl_sl_orders_id = opened_gl_sl_orders.first().id
            self.__cancel_sent_buy_orders(opened_gl_sl_orders)
            if opened_buy_orders.exists():
                new_stop_loss = self._get_new_stop_loss_futures_short(worked_tp_orders)
                residual_quantity = self._get_residual_quantity(ignore_fee=True)
                self.__form_buy_gl_sl_order(price=new_stop_loss, quantity=residual_quantity,
                                            original_order_id=opened_gl_sl_orders_id)
            else:
                logger.debug(f"[SHORT] There are no opened BUY orders for the signal '{self}'")
        # Change status
        if self.status not in BOUGHT__SIG_STATS:
            self.status = SignalStatus.BOUGHT.value
            self.save()
        self.__update_flag_handled_worked_buy_orders(worked_tp_orders)

    # POINT SOLD WORKER

    @debug_input_and_returned
    # @transaction.atomic
    def _worker_for_sold_orders_spot(self):
        """
        Worker for one signal.
        Run if at least one Sell order has worked.
        1)Cancel BUY orders
        2)Recreating opened (sent) SELL orders with updated stop_loss
        3)Calculate profit (stop_loss or take_profit)
        PS:
        If SL(oco) order has worked, corresponding TP order becomes expired automatically into Market
        If TP(oco) order has worked, corresponding SL order becomes expired automatically into Market
        """
        # TODO: Check
        worked_tp_orders = self.__get_not_handled_worked_sell_orders(tp_orders=True)
        if not worked_tp_orders:
            return
        self._cancel_opened_orders(buy=True)
        # Recreating opened sent sell orders with new stop_loss
        opened_sell_orders = self.__get_opened_sell_orders()
        opened_sell_orders = self.__exclude_sl_or_tp_orders(opened_sell_orders, worked_tp_orders)
        if opened_sell_orders:
            copied_sent_sell_orders_ids = list(opened_sell_orders.all().values_list('id', flat=True))
            self.__cancel_sent_sell_orders(opened_sell_orders)
            self._formation_copied_sell_orders(original_orders_ids=copied_sent_sell_orders_ids,
                                               worked_sell_orders=worked_tp_orders)
        # Change status
        if self.status not in SOLD__SIG_STATS:
            self.status = SignalStatus.SOLD.value
            self.save()
        self.__update_flag_handled_worked_sell_orders(worked_tp_orders)

    @debug_input_and_returned
    def _sold_worker_futures(self):
        """
        FUTURES Market
        """
        if self.is_position_short():
            logger.debug(f"Form Futures SHORT: '{self}'")
            self._sold_worker_futures_short()
        else:
            logger.debug(f"Form Futures LONG: '{self}'")
            self._sold_worker_futures_long()

    @debug_input_and_returned
    # @transaction.atomic
    def _sold_worker_futures_short(self):
        """
        Futures Market. SHORT
        Worker for one signal.
            Run if at least one Sell order has worked.
        1)Create Buy orders if no one exists
        2)Recreate Sent Buy orders with updated quantity
        """
        from apps.order.models import BuyOrder
        # TODO: maybe change name to bought_worker and remove method bought_worker_futures
        worked_orders = self.__get_not_handled_worked_sell_orders(sl_orders=True, tp_orders=True)
        if not worked_orders:
            return
        ignore_fee = True
        sold_quantity = self.__get_sold_quantity(worked_orders=worked_orders)
        logger.debug(f"[SHORT] Calculate quantity for Buy order: Sold_quantity = {sold_quantity}")
        # TODO: Add logic recreating existing sell orders with updated quantity
        # Recreating opened sent buy orders with new quantity
        opened_buy_orders = self.__get_opened_buy_orders(excluded_indexes=[BuyOrder.GL_SM_INDEX, ])
        if opened_buy_orders:
            new_sold_quantity = self.__calculate_new_executed_quantity(opened_buy_orders, sold_quantity)
            copied_sent_buy_orders_ids = list(opened_buy_orders.all().values_list('id', flat=True))
            self.__cancel_sent_buy_orders(opened_buy_orders)
            self._formation_copied_buy_orders_futures_short(original_orders_ids=copied_sent_buy_orders_ids,
                                                            buy_quantity=new_sold_quantity)
        # Form buy orders if the signal doesn't have any
        elif not self.__get_buy_orders_exclude_indexes(excluded_indexes=[BuyOrder.GL_SM_INDEX, ]).exists():
            self._second_formation_buy_orders_futures_short(buy_quantity=sold_quantity)
        self.__update_flag_handled_worked_sell_orders(worked_orders)
        # Change status
        if self.status not in BOUGHT_SOLD__SIG_STATS:
            self.status = SignalStatus.SOLD.value
            self.save()

    @debug_input_and_returned
    # @transaction.atomic
    def _sold_worker_futures_long(self):
        """
        Worker for one signal.
        Run if at least one Sell order has worked.
        1.GL SL order has worked:
          1)Cancel all opened tp sell orders and all opened buy orders
        2.At least one Sell order has worked
          1)Cancel BUY orders
          2)Recreating opened (sent) SELL GL SL order with updated price
          3)Cancel SELL GL SL order if there are no opened_sell_orders
        """
        from apps.order.models import SellOrder
        from apps.order.utils import OPENED_ORDER_STATUSES
        # TODO: change this function (remove tp_orders, sl_orders). Make it is more universal
        self.__try_cancel_opened_orders_if_gl_sl_sell_order_has_been_worked()

        worked_tp_orders = self.__get_not_handled_worked_sell_orders(
            tp_orders=True, sl_orders=True, excluded_indexes=[SellOrder.GL_SM_INDEX, ])
        if not worked_tp_orders:
            return
        self._cancel_opened_orders(buy=True)
        opened_sell_orders = self.__get_opened_sell_orders(excluded_indexes=[SellOrder.GL_SM_INDEX, ])
        # Recreating opened sent sell orders with new stop_loss
        opened_gl_sl_orders = self.__get_gl_sl_sell_orders(statuses=OPENED_ORDER_STATUSES)
        if opened_gl_sl_orders.exists():
            opened_gl_sl_orders_id = opened_gl_sl_orders.first().id
            self.__cancel_sent_sell_orders(opened_gl_sl_orders)
            if opened_sell_orders.exists():
                new_stop_loss = self._get_new_stop_loss_long_or_spot(worked_tp_orders)
                residual_quantity = self._get_residual_quantity(ignore_fee=True)
                self.__form_sell_gl_sl_order(price=new_stop_loss, quantity=residual_quantity,
                                             original_order_id=opened_gl_sl_orders_id)
            else:
                logger.debug(f"There are no opened SELL orders for the signal '{self}'")
        # Change status
        if self.status not in SOLD__SIG_STATS:
            self.status = SignalStatus.SOLD.value
            self.save()
        self.__update_flag_handled_worked_sell_orders(worked_tp_orders)

    # POINT CLOSE WORKER

    @debug_input_and_returned
    # @transaction.atomic
    def _try_to_close_spot(self):
        """
        Worker closes the Signal if it has no opened Buy orders and no opened Sell orders
        """
        if self._check_is_ready_to_be_closed():
            self._close()
            self._update_income()
            self._update_amount()

    def __try_cancel_opened_orders_if_gl_sl_sell_order_has_been_worked(self):
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        not_handled_completed_gl_sl_sell_orders = self.__get_gl_sl_sell_orders(
            statuses=COMPLETED_ORDER_STATUSES)
        if not_handled_completed_gl_sl_sell_orders:
            logger.debug(f"We have opened orders, but GL SL ORDER is completed. "
                         f"We will cancel all opened orders")
            self._cancel_opened_orders(buy=True, sell=True)
            self.__update_flag_handled_worked_sell_orders(not_handled_completed_gl_sl_sell_orders)

    def __try_cancel_opened_orders_if_gl_sl_buy_order_has_been_worked(self):
        from apps.order.utils import COMPLETED_ORDER_STATUSES
        not_handled_completed_gl_sl_buy_orders = self.__get_gl_sl_buy_orders(
            statuses=COMPLETED_ORDER_STATUSES)
        if not_handled_completed_gl_sl_buy_orders:
            logger.debug(f"[SHORT] We have opened orders, but GL SL BUY ORDER is completed. "
                         f"We will cancel all opened orders")
            self._cancel_opened_orders(buy=True, sell=True)
            self.__update_flag_handled_worked_buy_orders(not_handled_completed_gl_sl_buy_orders)

    @debug_input_and_returned
    def __close_futures_long(self):
        residual_quantity = self._get_residual_quantity(ignore_fee=True)
        if not residual_quantity:
            self._close()
            self._update_income()
            self._update_amount()
        elif get_or_create_crontask().sell_residual_quantity_enabled:
            logger.debug(f"We have residual quantity. We will sell it by Market. Signal: '{self}'")
            price = self._get_current_price()
            self.__form_sell_market_order(quantity=residual_quantity, price=price)
        else:
            logger.debug(f"[LONG] We have residual quantity. But sell_residual_quantity_enabled is False."
                         f" Signal: '{self}'")

    @debug_input_and_returned
    def __close_futures_short(self):
        residual_quantity = self._get_residual_quantity(ignore_fee=True)
        if not residual_quantity:
            self._close()
            self._update_income()
            self._update_amount()
        elif get_or_create_crontask().sell_residual_quantity_enabled:
            logger.debug(f"[SHORT] We have residual quantity. We will buy it by Market. Signal: '{self}'")
            price = self._get_current_price()
            self.__form_buy_market_order(quantity=residual_quantity, price=price)
        else:
            logger.debug(f"[SHORT] We have residual quantity. But sell_residual_quantity_enabled is False."
                         f" Signal: '{self}'")

    @debug_input_and_returned
    def __trail_stop_futures_short(self, fake_price: Optional[float] = None) -> bool:
        """

        FUTURES Market
        SHORT Position
        If the current price has crossed the threshold,
         the Stop loss order is moved to the specific value:
          it's a half value subtracted the current price and zero value.
          The zero value is a value of the nearest Entry Point
        """
        from apps.order.utils import OPENED_ORDER_STATUSES

        opened_gl_sl_orders = self.__get_gl_sl_buy_orders(statuses=OPENED_ORDER_STATUSES)
        gl_sl_order = opened_gl_sl_orders.first()
        sl_value = gl_sl_order.price
        zero_value = EntryPoint.get_min_value(self)
        if fake_price:
            current_price = fake_price
            logger.debug(f"Fake price for Trailing stop: '{fake_price}'")
        else:
            current_price = self._get_current_price()

        # Check
        if not self.__check_if_needs_to_move_sl_as_trailing_stop_short(
                zero_value=zero_value, sl_value=sl_value, current_price=current_price):
            return False

        # Check if new_stop_loss price < current_stop_loss
        opened_gl_sl_order = opened_gl_sl_orders.last()
        new_stop_loss = self.__get_new_sl_value_for_trailing_stop(
            zero_value=zero_value, current_price=current_price)
        if new_stop_loss >= opened_gl_sl_order.price:
            logger.debug(f"[SHORT] Calculated new_stop_loss of trailing_stop"
                         f" more then or equal to current GL_SL price!!!: "
                         f"{new_stop_loss} >= {opened_gl_sl_order.price}: '{self}'")
            return False

        # Check if quantity exists
        residual_quantity = self._get_residual_quantity(ignore_fee=True)
        if residual_quantity <= 0:
            logger.warning(f"Wrong Residual Quantity '{residual_quantity}' for trailing_stop: '{self}'")
            return False
        # Recreate GL_SL_ORDER
        # Cancel opened Buy orders if exist
        self._cancel_opened_orders(sell=True)
        self.__cancel_sent_buy_orders(opened_gl_sl_orders)
        self.__form_buy_gl_sl_order(price=new_stop_loss, quantity=residual_quantity,
                                    original_order_id=opened_gl_sl_order.id)
        return True

    @debug_input_and_returned
    def __check_if_needs_to_move_sl_as_trailing_stop_short(self,
                                                           zero_value: float,
                                                           sl_value: float,
                                                           current_price: float) -> bool:
        """
        FUTURES Market
        SHORT Position
        Check:
        if the current price has crossed a specific value (threshold)
        Threshold is a discreteness value by delta from Config (CronTask for now)
        since a zero value
        A zero value is a value of the nearest Entry point value
        """
        delta_from_zero_value = (zero_value * get_or_create_crontask().slip_delta_sl_perc
                                 ) / self.conf.one_hundred_percent
        # For the next crossing
        old_value_of_price = 2 * sl_value - zero_value
        # For the first crossing of the threshold
        old_value_of_price = zero_value - delta_from_zero_value if \
            old_value_of_price > zero_value else old_value_of_price
        threshold = old_value_of_price - delta_from_zero_value
        msg = f"[SHORT] Check trailing_stop '{self}':" \
              f" if: current_price < threshold: {current_price} < {threshold}?"
        if current_price < threshold:
            logger.debug(msg + ': Yes')
            return True
        else:
            logger.debug(msg + ': No')
            return False

    @debug_input_and_returned
    def __check_if_needs_to_move_sl_as_trailing_stop_long(self,
                                                          zero_value: float,
                                                          sl_value: float,
                                                          current_price: float) -> bool:
        """
        FUTURES Market
        LONG Position
        Check:
        if the current price has crossed a specific value (threshold)
        Threshold is a discreteness value by delta from Config (CronTask for now)
        since a zero value
        A zero value is a value of the nearest Entry point value
        """
        delta_from_zero_value = (zero_value * get_or_create_crontask().slip_delta_sl_perc
                                 ) / self.conf.one_hundred_percent
        # For the next crossing
        old_value_of_price = 2 * sl_value - zero_value
        # For the first crossing of the threshold
        old_value_of_price = zero_value + delta_from_zero_value if\
            old_value_of_price < zero_value else old_value_of_price
        threshold = old_value_of_price + delta_from_zero_value
        msg = f"Check trailing_stop '{self}':" \
              f" if: current_price > threshold: {current_price} > {threshold}?"
        if current_price > threshold:
            logger.debug(msg + ': Yes')
            return True
        else:
            logger.debug(msg + ': No')
            return False

    @debug_input_and_returned
    @rounded_result
    def __get_new_sl_value_for_trailing_stop(self, zero_value: float, current_price: float):
        res = (zero_value + current_price) / 2
        pair = self._get_pair()
        return self.__find_not_fractional_by_step(res, pair.step_price)

    @debug_input_and_returned
    def __trail_stop_futures_long(self, fake_price: Optional[float] = None) -> bool:
        """
        FUTURES Market
        LONG Position
        If the current price has crossed the threshold,
         the Stop loss order is moved to the specific value:
          it's a half value subtracted the current price and zero value.
          The zero value is a value of the nearest Entry Point
        """
        from apps.order.utils import OPENED_ORDER_STATUSES

        opened_gl_sl_orders = self.__get_gl_sl_sell_orders(statuses=OPENED_ORDER_STATUSES)
        gl_sl_order = opened_gl_sl_orders.last()
        sl_value = gl_sl_order.price
        zero_value = EntryPoint.get_max_value(self)
        if fake_price:
            current_price = fake_price
            logger.debug(f"Fake price for Trailing stop: '{fake_price}'")
        else:
            current_price = self._get_current_price()

        # Check
        if not self.__check_if_needs_to_move_sl_as_trailing_stop_long(
                zero_value=zero_value, sl_value=sl_value, current_price=current_price):
            return False

        # Check if new_stop_loss price > current_stop_loss
        opened_gl_sl_order = opened_gl_sl_orders.first()
        new_stop_loss = self.__get_new_sl_value_for_trailing_stop(
            zero_value=zero_value, current_price=current_price)
        if new_stop_loss <= opened_gl_sl_order.price:
            logger.debug(f"Calculated new_stop_loss of trailing_stop less then or equal to current GL_SL price!!!: "
                         f"{new_stop_loss} <= {opened_gl_sl_order.price}: '{self}'")
            return False

        # Check if quantity exists
        residual_quantity = self._get_residual_quantity(ignore_fee=True)
        if residual_quantity <= 0:
            logger.warning(f"Wrong Residual Quantity '{residual_quantity}' for trailing_stop: '{self}'")
            return False
        # Recreate GL_SL_ORDER
        # Cancel opened Buy orders if exist
        self._cancel_opened_orders(buy=True)
        self.__cancel_sent_sell_orders(opened_gl_sl_orders)
        self.__form_sell_gl_sl_order(price=new_stop_loss, quantity=residual_quantity,
                                     original_order_id=opened_gl_sl_order.id)
        return True

    @debug_input_and_returned
    # @transaction.atomic
    def _try_to_close_futures(self):
        """
        Worker closes the Signal if it has no opened Buy orders and no opened Sell orders
        """
        if self._check_is_ready_to_be_closed():
            if self.is_position_short():
                self.__close_futures_short()
            else:
                self.__close_futures_long()

    @debug_input_and_returned
    # @transaction.atomic
    def _trail_stop_futures(self, fake_price: Optional[float] = None) -> bool:
        """
        """
        if self.is_position_short():
            return self.__trail_stop_futures_short(fake_price=fake_price)
        else:
            return self.__trail_stop_futures_long(fake_price=fake_price)

    @debug_input_and_returned
    # @transaction.atomic
    def _trail_stop_spot(self):
        """
        """
        pass

    # POINT OTHERS

    @rounded_result
    def get_real_stop_price(self, price: float, lower: bool = True) -> float:
        """
        Calculate stop price with slip_delta_stop_loss_percentage parameter.
        Fraction by step
        """
        pair = self._get_pair()
        if get_or_create_crontask().slip_delta_sl_perc:
            delta_value = price * get_or_create_crontask().slip_delta_sl_perc / self.conf.one_hundred_percent
            if lower:
                real_stop_price = price - delta_value
            else:
                real_stop_price = price + delta_value

        else:
            real_stop_price = price
        return self.__find_not_fractional_by_step(real_stop_price, pair.step_price)

    # POINT MAIN FOR ONE SIGNAL

    # @transaction.atomic
    def first_formation_orders(self, fake_balance: Optional[float] = None) -> bool:
        """
        Function for first formation orders for NEW signal
        """
        if self._status != SignalStatus.NEW.value:
            logger.warning(f"Not valid Signal status for formation BUY order: "
                           f"{self._status} : {SignalStatus.NEW.value}")
            return False
        logger.debug(f"FIRST FORMATION for Signal '{self}': INITIAL DATA: balance_to_signal_perc="
                     f"'{get_or_create_crontask().balance_to_signal_perc}',"
                     f" slip_delta_sl_perc='{get_or_create_crontask().slip_delta_sl_perc}'")
        if self._is_market_type_futures():
            return self._first_formation_futures_orders(fake_balance=fake_balance)
        else:
            return self._first_formation_spot_orders(fake_balance=fake_balance)

    @debug_input_and_returned
    def push_orders(self):
        if self._is_market_type_futures():
            return self._push_futures_orders()
        else:
            return self._push_spot_orders()

    def update_info_by_api(self):
        """
        Get info for all Signals (except NEW) from Real Market by SENT orders
        """
        from apps.order.utils import SENT_ORDER_STATUSES
        if self._status not in PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS:
            return

        params = {
            '_status__in': SENT_ORDER_STATUSES,
        }
        for buy_order in self.buy_orders.filter(**params):
            buy_order.update_buy_order_info_by_api()
        for sell_order in self.sell_orders.filter(**params):
            sell_order.update_sell_order_info_by_api()

    @debug_input_and_returned
    # @transaction.atomic
    def worker_for_bought_orders(self):
        """
        Worker for one signal.
        Run if at least one Buy order has worked.
        1)Create Sell orders if no one exists
        2)Recreate Sent Sell orders with updated quantity
        """
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        if self._status not in PUSHED_BOUGHT_SOLD__SIG_STATS:
            return
        if self._is_market_type_futures():
            return self._bought_worker_futures()
        else:
            return self._bought_worker_spot()

    @debug_input_and_returned
    # @transaction.atomic
    def worker_for_sold_orders(self):
        """
        Worker for one signal.
        Run if at least one Sell order has worked.
        1)Cancel BUY orders
        2)Recreating opened (sent) SELL orders with updated stop_loss
        3)Calculate profit (stop_loss or take_profit)
        """
        # TODO: Maybe add select_for_update - to avoid setting the flag by another process
        #  or add another flag now_being_processed
        # TODO: Check
        if self._status not in PUSHED_BOUGHT_SOLD__SIG_STATS:
            return
        if self._is_market_type_futures():
            return self._sold_worker_futures()
        else:
            return self._worker_for_sold_orders_spot()

    @debug_input_and_returned
    def _check_is_ready_to_spoil_spot_or_long(self) -> bool:
        current_price = self._get_current_price()
        min_profit_price = TakeProfit.get_min_value(self)
        msg = f"Check try_to_spoil '{self}':" \
              f" if: current_price >= min_profit_price: {current_price} >= {min_profit_price}?"
        if current_price >= min_profit_price:
            logger.debug(msg + ': Yes')
            return True
        else:
            logger.debug(msg + ': No')
            return False

    @debug_input_and_returned
    def _check_is_ready_to_spoil_futures_short(self) -> bool:
        current_price = self._get_current_price()
        max_profit_price = TakeProfit.get_max_value(self)
        msg = f"Check try_to_spoil '{self}':" \
              f" if: current_price <= min_profit_price: {current_price} <= {max_profit_price}?"
        if current_price <= max_profit_price:
            logger.debug(msg + ': Yes')
            return True
        else:
            logger.debug(msg + ': No')
            return False

    def _check_is_ready_to_spoil(self) -> bool:
        if self.is_position_short():
            return self._check_is_ready_to_spoil_futures_short()
        else:
            return self._check_is_ready_to_spoil_spot_or_long()

    @debug_input_and_returned
    # @transaction.atomic
    def try_to_spoil(self, force: bool = False):
        """
        Worker spoils the Signal if a current price reaches any of take_profits
        and there are no worked Buy orders
        """
        if force:
            self._spoil(force=True)
            return
        if self._status not in FORMED_PUSHED__SIG_STATS:
            return
        if self._check_is_ready_to_spoil():
            self._spoil()

    @debug_input_and_returned
    # @transaction.atomic
    def try_to_close(self):
        """
        Worker closes the Signal if it has no opened Buy orders and no opened Sell orders
        """
        if self._status not in FORMED_PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS:
            return False
        if self._is_market_type_futures():
            return self._try_to_close_futures()
        else:
            return self._try_to_close_spot()

    @debug_input_and_returned
    # @transaction.atomic
    def trail_stop(self, fake_price: Optional[float] = None):
        """
        """
        if self._status not in BOUGHT_SOLD__SIG_STATS:
            return False
        if self._is_market_type_futures():
            return self._trail_stop_futures(fake_price=fake_price)
        else:
            return self._trail_stop_spot()


    # POINT MAIN FOR ALL SIGNALS

    @classmethod
    def handle_new_signals(cls,
                           outer_signal_id: Optional[int] = None,
                           techannel_abbr: Optional[str] = None,
                           fake_balance: Optional[float] = None):
        """Handle all NEW signals: Step 2"""
        params = {'_status': SignalStatus.NEW.value}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        new_signals = Signal.objects.filter(**params)
        for signal in new_signals:
            signal.first_formation_orders(fake_balance=fake_balance)

    @classmethod
    def push_signals(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all FORMED signals: Step 3"""
        params = {'_status__in': FORMED_PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        ready_for_push_signals = Signal.objects.filter(**params)
        for signal in ready_for_push_signals:
            signal.push_orders()

    @classmethod
    def update_signals_info_by_api(cls,
                                   outer_signal_id: Optional[int] = None,
                                   techannel_abbr: Optional[str] = None):
        """
        Get info for one Signal from Real Market by SENT orders
        """
        params = {'_status__in': PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.update_info_by_api()

    @classmethod
    def bought_orders_worker(cls,
                             outer_signal_id: Optional[int] = None,
                             techannel_abbr: Optional[str] = None):
        """Handle all PUSHED signals. Buy orders worker"""
        params = {'_status__in': PUSHED_BOUGHT_SOLD__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.worker_for_bought_orders()

    @classmethod
    def sold_orders_worker(cls,
                           outer_signal_id: Optional[int] = None,
                           techannel_abbr: Optional[str] = None):
        """Handle all BOUGHT signals. Sell orders worker"""
        params = {'_status__in': PUSHED_BOUGHT_SOLD__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.worker_for_sold_orders()

    @classmethod
    def spoil_worker(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all signals. Try_to_spoil worker"""
        params = {'_status__in': FORMED_PUSHED__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        formed_signals = Signal.objects.filter(**params)
        for signal in formed_signals:
            signal.try_to_spoil()

    @classmethod
    def close_worker(cls,
                     outer_signal_id: Optional[int] = None,
                     techannel_abbr: Optional[str] = None):
        """Handle all signals. Try_to_close worker"""
        params = {'_status__in': FORMED_PUSHED_BOUGHT_SOLD_CANCELING__SIG_STATS}
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        signals = Signal.objects.filter(**params)
        for signal in signals:
            signal.try_to_close()

    @classmethod
    def trailing_stop_worker(cls,
                             outer_signal_id: Optional[int] = None,
                             techannel_abbr: Optional[str] = None,
                             fake_price: Optional[float] = None):
        """Handle all signals. Trailing stop feature"""
        params = {
            '_status__in': BOUGHT_SOLD__SIG_STATS,
            'trailing_stop_enabled': True,
        }
        if outer_signal_id:
            params.update({'outer_signal_id': outer_signal_id,
                           'techannel__abbr': techannel_abbr})
        signals = Signal.objects.filter(**params)
        for signal in signals:
            signal.trail_stop(fake_price=fake_price)


class EntryPointOrig(BasePointOrig):
    signal = models.ForeignKey(to=SignalOrig,
                               related_name='entry_points',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'SignalOrig.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class EntryPoint(BaseEntryPoint):
    signal = models.ForeignKey(to=Signal,
                               related_name='entry_points',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'Signal.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class TakeProfitOrig(BasePointOrig):
    signal = models.ForeignKey(to=SignalOrig,
                               related_name='take_profits',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'SignalOrig.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class TakeProfit(BaseTakeProfit):
    signal = models.ForeignKey(to=Signal,
                               related_name='take_profits',
                               on_delete=models.CASCADE)
    value = models.FloatField()

    objects = models.Manager()

    signal: 'Signal.objects'

    class Meta:
        unique_together = ['signal', 'value']

    def __str__(self):
        return f"{self.signal.symbol}:{self.value}"


class HistorySignal(BaseHistorySignal):
    status = models.CharField(max_length=32,
                              choices=SignalStatus.choices(),
                              default=SignalStatus.NEW.value)
    main_signal = models.ForeignKey(to=Signal,
                                    related_name='signal_history',
                                    on_delete=models.CASCADE)
    current_price = models.FloatField(null=True)

    objects = models.Manager()

    def __str__(self):
        return f"HS_{self.pk}:Main_signal:{self.main_signal}"

    @classmethod
    def write_in_history(cls,
                         signal: Signal,
                         status: str):
        current_price = None
        try:
            current_price = signal.market_logic.get_current_price(signal.symbol)
        except Exception as ex:
            logger.warning(f"Current price for HistorySignal failed to get. Signal '{signal}'"
                           f": Exception:'{ex}'")
        cls.objects.create(main_signal=signal, status=status, current_price=current_price)
        logger.debug(f"Add HistorySignal Record for Signal '{signal}' status = '{status}'")
