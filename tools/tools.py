import logging
import uuid

from binance.exceptions import BinanceAPIException

from functools import partial, wraps
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def rou(value: float):
    """
    Round float numbers.
    Use for calculating quantity or rates
    :param value:
    :return:
    """
    digits = 8
    return round(value, digits)


def gen_short_uuid(length: int = 8) -> str:
    return str(uuid.uuid4())[:length]


def countdown(t):
    import time
    while t:
        mins, secs = divmod(t, 60)
        timeformat = '{:02d}:{:02d}'.format(mins, secs)
        # print(timeformat, )
        logger.debug(f'Wait for a message: {timeformat} \r')
        time.sleep(1)
        t -= 1
    print('Countdown finished\n\n\n')


def rounded_result(func: Optional[Callable] = None, *, digits: int = 8):
    """
    Decorator to round the result
    @rounded_result
    @rounded_result(digits=3)
    """
    if func is None:
        return partial(rounded_result, digits=digits)

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return round(result, digits)
    return wrapper

# def rounded_quantity_by_rule(func: Optional[Callable] = None, *, digits: int = 8):
#     """
#     """
#     if func is None:
#         return partial(rounded_quantity_by_rule, digits=digits)
#
#     @wraps(func)
#     def wrapper(*args, **kwargs):
#         market = kwargs['market']
#         result = func(*args, **kwargs)
#         return round(result, digits)
#     return wrapper


def floated_result(func: Optional[Callable] = None):
    """
    Decorator to float the result
    @floated_result
    @floated_result()
    """
    if func is None:
        return partial(floated_result)

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return float(result)
    return wrapper


def api_logging(func: Optional[Callable] = None, *, text: str = ""):
    """
    Decorator to log API requests and responses
    @api_logging
    @api_logging(text="Creating order")
    """
    if func is None:
        return partial(api_logging, text=text)

    @wraps(func)
    def wrapper(*args, **kwargs):
        short_uuid = gen_short_uuid().upper()
        logger.debug(f"API.....Request..{short_uuid}:{func.__name__.upper()}:"
                     f" ...{text}... Args: {args},{kwargs}")
        result = func(*args, **kwargs)
        logger.debug(f"API-----Response--{short_uuid}:{func.__name__.upper()}: {result}")
        return result
    return wrapper


def debug_input_and_returned(func):
    """Decorator for logging signature and returned value"""
    @wraps(func)
    def wrapper_debug(*args, **kwargs):
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"Calling {func.__name__}({signature})")
        value = func(*args, **kwargs)
        logger.debug(f"{func.__name__!r} returned {value!r}")
        return value
    return wrapper_debug


def catch_exception(f=None, *, code: int, alternative: dict):
    if f is None:
        return partial(catch_exception, code=code, alternative=alternative)

    @wraps(f)
    def func(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code == code:
                return alternative
    return func


@rounded_result
def convert_to_coin_quantity(quantity, value):
    return quantity / value


@rounded_result
def convert_to_amount(quantity, value):
    return quantity * value


@rounded_result
def get_percent(value: float, percentage) -> float:
    return (value * percentage) / 100


@rounded_result
def subtract_fee(quantity: float, fee: float, reverse: bool = False) -> float:
    if not reverse:
        return quantity - get_percent(quantity, fee)
    else:
        return quantity + get_percent(quantity, fee)


def price_to_str(price: float) -> str:
    precision = 8
    return '{:0.0{}f}'.format(price, precision)
